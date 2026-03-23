import logging
import re
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from app.core.config import Settings
from app.core.http import build_request_headers, request_with_retry
from app.models.source import Source
from app.parsers.base import BaseSourceAdapter
from app.services.types import ParsedItem, ParseResult

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class SectionContext:
    category: str | None
    subcategory: str | None


class WebScraperEcommerceAdapter(BaseSourceAdapter):
    parser_key = "webscraper_static_ecommerce"
    CATEGORIES = ["Phones", "Touch"]

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def display_name(self) -> str:
        return "Web Scraper Static E-Commerce"

    def supported_categories(self) -> list[str]:
        return list(self.CATEGORIES)

    def requires_enrichment(
        self, item: ParsedItem, existing_attributes: dict | None = None
    ) -> bool:
        attributes = existing_attributes or item.attributes
        return "option_count" not in attributes

    def parse(self, source: Source) -> ParseResult:
        session = requests.Session()
        session.headers.update(build_request_headers(self.settings))

        pages_fetched = 0
        warnings: list[str] = []
        page_queue = deque([source.start_url])
        seen_pages: set[str] = set()
        items_by_url: dict[str, ParsedItem] = {}

        while page_queue:
            current_url = page_queue.popleft()
            if current_url in seen_pages:
                continue

            response = request_with_retry(
                request_callable=session.get,
                logger=logger,
                service_name=self.parser_key,
                method="GET",
                url=current_url,
                timeout=self.settings.request_timeout_seconds,
                retry_attempts=self.settings.http_retry_attempts,
                retry_base_seconds=self.settings.http_retry_base_seconds,
            )
            response.raise_for_status()
            response.encoding = response.encoding or "utf-8"
            pages_fetched += 1
            seen_pages.add(current_url)

            soup = BeautifulSoup(response.text, "html.parser")
            context = self._extract_section_context(soup)
            product_cards = soup.select("div.card.thumbnail")
            if not product_cards:
                warnings.append(f"No product cards found on {current_url}")

            for card in product_cards:
                parsed = self._parse_card(card=card, current_url=current_url, context=context)
                if parsed is None:
                    continue
                existing = items_by_url.get(parsed.canonical_url)
                if existing is None:
                    items_by_url[parsed.canonical_url] = parsed
                else:
                    self._merge_item(existing, parsed)

            for section_url in self._extract_section_links(soup, current_url):
                if section_url not in seen_pages and section_url not in page_queue:
                    page_queue.append(section_url)

            next_url = self._extract_next_url(soup, current_url)
            if next_url and next_url not in seen_pages and next_url not in page_queue:
                page_queue.append(next_url)

        return ParseResult(
            items=list(items_by_url.values()), pages_fetched=pages_fetched, warnings=warnings
        )

    def enrich_items(self, source: Source, items: list[ParsedItem]) -> list[ParsedItem]:
        pending = [item for item in items if "option_count" not in item.attributes]
        if not pending:
            return items

        max_workers = max(1, min(self.settings.parser_detail_fetch_workers, len(pending)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            metadata = list(
                executor.map(
                    self._fetch_detail_metadata,
                    [item.canonical_url for item in pending],
                )
            )

        for item, detail in zip(pending, metadata, strict=False):
            for key, value in detail.items():
                if value is not None:
                    item.attributes[key] = value
        return items

    def _parse_card(
        self, *, card: Tag, current_url: str, context: SectionContext
    ) -> ParsedItem | None:
        anchor = card.select_one("a.title")
        if anchor is None:
            return None

        href = anchor.get("href", "").strip()
        canonical_url = urljoin(current_url, href)
        title = anchor.get("title", "").strip() or anchor.get_text(" ", strip=True)

        price_element = card.select_one("[itemprop='price']")
        price_raw = price_element.get_text(strip=True) if price_element else ""
        price_clean = re.sub(r"[^0-9.]", "", price_raw)
        price_amount = float(price_clean) if price_clean else None

        currency = "USD"
        currency_element = card.select_one("meta[itemprop='priceCurrency']")
        if currency_element and currency_element.get("content"):
            currency = currency_element["content"].strip()

        review_count = self._safe_int(card.select_one("[itemprop='reviewCount']"))
        description = self._safe_text(card.select_one(".description"))
        rating_count = len(card.select(".ratings .ws-icon-star"))

        category_value = context.subcategory or context.category
        attributes: dict[str, object] = {}
        if category_value:
            attributes["category"] = category_value
        if context.category and context.subcategory:
            attributes["top_level_category"] = context.category
            attributes["subcategory"] = context.subcategory
        if description:
            attributes["description"] = description
        if review_count is not None:
            attributes["review_count"] = review_count

        return ParsedItem(
            canonical_url=canonical_url,
            title=title,
            price_amount=price_amount,
            currency=currency,
            availability_status="in_stock",
            rating=str(rating_count) if rating_count else None,
            attributes=attributes,
        )

    def _fetch_detail_metadata(self, canonical_url: str) -> dict[str, object]:
        response = request_with_retry(
            request_callable=requests.get,
            logger=logger,
            service_name=f"{self.parser_key}.detail",
            method="GET",
            url=canonical_url,
            timeout=self.settings.request_timeout_seconds,
            retry_attempts=self.settings.http_retry_attempts,
            retry_base_seconds=self.settings.http_retry_base_seconds,
            headers=build_request_headers(self.settings),
        )
        response.raise_for_status()
        response.encoding = response.encoding or "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")

        swatches = [
            button.get_text(" ", strip=True)
            for button in soup.select("button.swatch")
            if not button.has_attr("disabled")
        ]
        if swatches:
            return {"option_kind": "swatch", "option_count": len(swatches)}

        select_options = [
            option.get_text(" ", strip=True)
            for option in soup.select("select option")
            if option.get("value", "").strip()
        ]
        if select_options:
            return {"option_kind": "select", "option_count": len(select_options)}

        return {}

    def _extract_section_context(self, soup: BeautifulSoup) -> SectionContext:
        category = self._safe_text(soup.select_one("a.category-link.active [itemprop='name']"))
        subcategory = self._safe_text(
            soup.select_one("a.subcategory-link.active [itemprop='name']")
        )
        return SectionContext(category=category, subcategory=subcategory)

    def _extract_section_links(self, soup: BeautifulSoup, current_url: str) -> list[str]:
        links: list[str] = []
        for anchor in soup.select("a.subcategory-link"):
            href = anchor.get("href", "").strip()
            if not href:
                continue
            links.append(urljoin(current_url, href))
        return links

    def _extract_next_url(self, soup: BeautifulSoup, current_url: str) -> str | None:
        next_link = soup.select_one("a.page-link.next")
        if next_link is None:
            return None
        href = next_link.get("href", "").strip()
        if not href:
            return None
        return urljoin(current_url, href)

    def _merge_item(self, existing: ParsedItem, incoming: ParsedItem) -> None:
        existing_category = existing.attributes.get("category")
        incoming_category = incoming.attributes.get("category")
        if (
            existing_category == "Phones"
            and incoming_category
            and incoming_category != existing_category
        ):
            existing.attributes.update(incoming.attributes)
            existing.rating = incoming.rating or existing.rating
        existing.price_amount = incoming.price_amount or existing.price_amount

    @staticmethod
    def _safe_text(node: Tag | None) -> str | None:
        if node is None:
            return None
        text = node.get_text(" ", strip=True)
        return text or None

    @staticmethod
    def _safe_int(node: Tag | None) -> int | None:
        text = WebScraperEcommerceAdapter._safe_text(node)
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None
