import logging
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.core.config import Settings
from app.core.http import build_request_headers, request_with_retry
from app.models.source import Source
from app.parsers.base import BaseSourceAdapter
from app.services.types import ParsedItem, ParseResult

logger = logging.getLogger(__name__)


class BooksToScrapeAdapter(BaseSourceAdapter):
    parser_key = "books_toscrape"
    CATEGORIES = [
        "Travel",
        "Mystery",
        "Historical Fiction",
        "Sequential Art",
        "Classics",
        "Philosophy",
        "Romance",
        "Womens Fiction",
        "Fiction",
        "Childrens",
        "Religion",
        "Nonfiction",
        "Music",
        "Default",
        "Science Fiction",
        "Sports and Games",
        "Add a comment",
        "Fantasy",
        "New Adult",
        "Young Adult",
        "Science",
        "Poetry",
        "Paranormal",
        "Art",
        "Psychology",
        "Autobiography",
        "Parenting",
        "Adult Fiction",
        "Humor",
        "Horror",
        "History",
        "Food and Drink",
        "Christian Fiction",
        "Business",
        "Biography",
        "Thriller",
        "Contemporary",
        "Spirituality",
        "Academic",
        "Self Help",
        "Historical",
        "Christian",
        "Suspense",
        "Short Stories",
        "Novels",
        "Health",
        "Politics",
        "Cultural",
        "Erotica",
        "Crime",
    ]

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def display_name(self) -> str:
        return "Books to Scrape"

    def supported_categories(self) -> list[str]:
        return list(self.CATEGORIES)

    def parse(self, source: Source) -> ParseResult:
        session = requests.Session()
        session.headers.update(build_request_headers(self.settings))

        items: list[ParsedItem] = []
        pages_fetched = 0
        warnings: list[str] = []
        next_url = source.start_url

        while next_url:
            response = request_with_retry(
                request_callable=session.get,
                logger=logger,
                service_name=self.parser_key,
                method="GET",
                url=next_url,
                timeout=self.settings.request_timeout_seconds,
                retry_attempts=self.settings.http_retry_attempts,
                retry_base_seconds=self.settings.http_retry_base_seconds,
            )
            response.raise_for_status()
            response.encoding = response.encoding or "utf-8"
            pages_fetched += 1

            soup = BeautifulSoup(response.text, "html.parser")
            product_cards = soup.select("article.product_pod")
            if not product_cards:
                warnings.append(f"No product cards found on {next_url}")

            for card in product_cards:
                anchor = card.select_one("h3 a")
                if anchor is None:
                    continue
                relative_url = anchor.get("href", "").strip()
                canonical_url = urljoin(next_url, relative_url)
                title = anchor.get("title", "").strip() or anchor.text.strip()

                price_element = card.select_one(".price_color")
                price_raw = price_element.get_text(strip=True) if price_element else ""
                price_clean = re.sub(r"[^0-9.]", "", price_raw)
                price_amount = float(price_clean) if price_clean else None

                availability_element = card.select_one(".instock.availability")
                availability_text = (
                    availability_element.get_text(" ", strip=True) if availability_element else ""
                )
                availability_status = (
                    "in_stock" if "In stock" in availability_text else "out_of_stock"
                )

                rating_element = card.select_one("p.star-rating")
                rating = None
                if rating_element:
                    rating_classes = rating_element.get("class", [])
                    rating = next(
                        (value for value in rating_classes if value != "star-rating"), None
                    )

                items.append(
                    ParsedItem(
                        canonical_url=canonical_url,
                        title=title,
                        price_amount=price_amount,
                        currency="GBP",
                        availability_status=availability_status,
                        rating=rating,
                        attributes={},
                    )
                )

            next_link = soup.select_one("li.next a")
            next_url = urljoin(next_url, next_link.get("href")) if next_link else ""

        return ParseResult(items=items, pages_fetched=pages_fetched, warnings=warnings)

    def enrich_items(self, source: Source, items: list[ParsedItem]) -> list[ParsedItem]:
        pending = [item for item in items if not item.attributes.get("category")]
        if not pending:
            return items

        max_workers = max(1, min(self.settings.parser_detail_fetch_workers, len(pending)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            categories = list(
                executor.map(self._fetch_category, [item.canonical_url for item in pending])
            )

        for item, category in zip(pending, categories, strict=False):
            if category:
                item.attributes["category"] = category
        return items

    def _fetch_category(self, canonical_url: str) -> str | None:
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
        breadcrumbs = [
            crumb.get_text(" ", strip=True) for crumb in soup.select("ul.breadcrumb li a")
        ]
        return breadcrumbs[-1] if breadcrumbs else None
