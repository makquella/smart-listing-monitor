from pathlib import Path

import pytest

from app.core.config import Settings
from app.models.source import Source
from app.parsers.webscraper_ecommerce import WebScraperEcommerceAdapter
from app.services.types import ParsedItem

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "webscraper"


class FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.encoding = "utf-8"

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, responses: dict[str, str]):
        self.responses = responses
        self.headers: dict[str, str] = {}

    def get(self, url: str, timeout: int) -> FakeResponse:
        if url not in self.responses:
            raise AssertionError(f"Unexpected catalog URL requested in parser test: {url}")
        return FakeResponse(self.responses[url])


def _load_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def _make_source(
    start_url: str = "https://webscraper.io/test-sites/e-commerce/static/phones",
) -> Source:
    return Source(
        id=2,
        name="Web Scraper Phones",
        slug="webscraper-phones",
        parser_key="webscraper_static_ecommerce",
        base_url="https://webscraper.io/",
        start_url=start_url,
        schedule_enabled=True,
        schedule_interval_minutes=60,
        is_active=True,
        health_status="healthy",
        consecutive_failures=0,
        created_at=None,
        updated_at=None,
    )


def _catalog_responses() -> dict[str, str]:
    return {
        "https://webscraper.io/test-sites/e-commerce/static/phones": _load_fixture(
            "phones_root.html"
        ),
        "https://webscraper.io/test-sites/e-commerce/static/phones/touch": _load_fixture(
            "phones_touch_page_1.html"
        ),
        "https://webscraper.io/test-sites/e-commerce/static/phones/touch?page=2": _load_fixture(
            "phones_touch_page_2.html"
        ),
    }


def _detail_get_factory(responses: dict[str, str]):
    def _get(url: str, timeout: int, headers=None) -> FakeResponse:
        if url not in responses:
            raise AssertionError(f"Unexpected detail URL requested in parser test: {url}")
        return FakeResponse(responses[url])

    return _get


@pytest.fixture
def adapter() -> WebScraperEcommerceAdapter:
    return WebScraperEcommerceAdapter(Settings(_env_file=None, PARSER_DETAIL_FETCH_WORKERS=1))


def test_webscraper_adapter_parses_section_and_pagination_offline(monkeypatch, adapter) -> None:
    monkeypatch.setattr(
        "app.parsers.webscraper_ecommerce.requests.Session",
        lambda: FakeSession(_catalog_responses()),
    )

    result = adapter.parse(_make_source())

    assert result.pages_fetched == 3
    assert result.warnings == []
    assert [item.title for item in result.items] == [
        "Nokia 123",
        "LG Optimus",
        "Samsung Galaxy",
        "Sony Xperia",
    ]
    assert result.items[0].currency == "USD"
    assert result.items[0].availability_status == "in_stock"
    assert result.items[0].attributes["category"] == "Phones"
    assert result.items[1].attributes["category"] == "Touch"
    assert result.items[1].attributes["top_level_category"] == "Phones"
    assert result.items[1].attributes["review_count"] == 11
    assert result.items[1].rating == "2"


def test_webscraper_adapter_enriches_detail_metadata_offline(monkeypatch, adapter) -> None:
    detail_html = _load_fixture("product_detail.html")
    monkeypatch.setattr(
        "app.parsers.webscraper_ecommerce.requests.get",
        _detail_get_factory(
            {
                "https://webscraper.io/test-sites/e-commerce/static/product/1": detail_html,
                "https://webscraper.io/test-sites/e-commerce/static/product/2": detail_html,
            }
        ),
    )

    items = [
        ParsedItem(
            canonical_url="https://webscraper.io/test-sites/e-commerce/static/product/1",
            title="Nokia 123",
            price_amount=24.99,
            currency="USD",
            availability_status="in_stock",
            rating="3",
            attributes={"category": "Phones"},
        ),
        ParsedItem(
            canonical_url="https://webscraper.io/test-sites/e-commerce/static/product/2",
            title="LG Optimus",
            price_amount=57.99,
            currency="USD",
            availability_status="in_stock",
            rating="2",
            attributes={"category": "Touch"},
        ),
    ]

    enriched = adapter.enrich_items(_make_source(), items)

    assert enriched[0].attributes["option_kind"] == "select"
    assert enriched[0].attributes["option_count"] == 3
    assert enriched[1].attributes["option_kind"] == "select"
    assert enriched[1].attributes["option_count"] == 3


def test_webscraper_adapter_handles_missing_fields_fixture(monkeypatch, adapter) -> None:
    monkeypatch.setattr(
        "app.parsers.webscraper_ecommerce.requests.Session",
        lambda: FakeSession(
            {
                "https://webscraper.io/test-sites/e-commerce/static/phones": _load_fixture(
                    "catalog_missing_fields.html"
                )
            }
        ),
    )

    result = adapter.parse(_make_source())

    assert result.pages_fetched == 1
    assert len(result.items) == 1
    assert result.items[0].title == "Budget Phone"
    assert result.items[0].price_amount is None
    assert result.items[0].rating is None
    assert result.items[0].attributes["category"] == "Phones"


def test_webscraper_adapter_warns_when_catalog_markup_changes(monkeypatch, adapter) -> None:
    monkeypatch.setattr(
        "app.parsers.webscraper_ecommerce.requests.Session",
        lambda: FakeSession(
            {
                "https://webscraper.io/test-sites/e-commerce/static/phones": _load_fixture(
                    "catalog_changed_markup.html"
                )
            }
        ),
    )

    result = adapter.parse(_make_source())

    assert result.pages_fetched == 1
    assert result.items == []
    assert result.warnings == [
        "No product cards found on https://webscraper.io/test-sites/e-commerce/static/phones"
    ]


def test_webscraper_adapter_returns_empty_detail_metadata_on_changed_markup(
    monkeypatch, adapter
) -> None:
    monkeypatch.setattr(
        "app.parsers.webscraper_ecommerce.requests.get",
        _detail_get_factory(
            {
                "https://webscraper.io/test-sites/e-commerce/static/product/1": _load_fixture(
                    "product_detail_changed_markup.html"
                )
            }
        ),
    )

    item = ParsedItem(
        canonical_url="https://webscraper.io/test-sites/e-commerce/static/product/1",
        title="Nokia 123",
        price_amount=24.99,
        currency="USD",
        availability_status="in_stock",
        rating="3",
        attributes={"category": "Phones"},
    )

    enriched = adapter.enrich_items(_make_source(), [item])

    assert enriched[0].attributes == {"category": "Phones"}
