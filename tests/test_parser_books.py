from pathlib import Path

import pytest

from app.core.config import Settings
from app.models.source import Source
from app.parsers.books_toscrape import BooksToScrapeAdapter
from app.services.types import ParsedItem

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "books"


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


def _make_source(start_url: str = "https://books.toscrape.com/catalogue/page-1.html") -> Source:
    return Source(
        id=1,
        name="Books",
        slug="books",
        parser_key="books_toscrape",
        base_url="https://books.toscrape.com/",
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
        "https://books.toscrape.com/catalogue/page-1.html": _load_fixture("catalog_page_1.html"),
        "https://books.toscrape.com/catalogue/page-2.html": _load_fixture("catalog_page_2.html"),
    }


def _detail_get_factory(responses: dict[str, str]):
    def _get(url: str, timeout: int, headers=None) -> FakeResponse:
        if url not in responses:
            raise AssertionError(f"Unexpected detail URL requested in parser test: {url}")
        return FakeResponse(responses[url])

    return _get


@pytest.fixture
def adapter() -> BooksToScrapeAdapter:
    return BooksToScrapeAdapter(Settings(PARSER_DETAIL_FETCH_WORKERS=1))


def test_books_adapter_parses_paginated_catalog_offline(monkeypatch, adapter) -> None:
    monkeypatch.setattr(
        "app.parsers.books_toscrape.requests.Session",
        lambda: FakeSession(_catalog_responses()),
    )

    result = adapter.parse(_make_source())

    assert result.pages_fetched == 2
    assert result.warnings == []
    assert [item.title for item in result.items] == [
        "A Light in the Attic",
        "Tipping the Velvet",
        "Soumission",
    ]
    assert result.items[0].canonical_url == (
        "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
    )
    assert result.items[0].price_amount == 51.77
    assert result.items[0].availability_status == "in_stock"
    assert result.items[0].rating == "Three"
    assert result.items[2].availability_status == "out_of_stock"
    assert result.items[2].rating == "Five"


def test_books_adapter_enriches_categories_from_detail_fixture_offline(
    monkeypatch, adapter
) -> None:
    detail_html = _load_fixture("product_detail.html")
    monkeypatch.setattr(
        "app.parsers.books_toscrape.requests.get",
        _detail_get_factory(
            {
                "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html": detail_html,
                "https://books.toscrape.com/catalogue/tipping-the-velvet_999/index.html": detail_html,
            }
        ),
    )

    items = [
        ParsedItem(
            canonical_url="https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
            title="A Light in the Attic",
            price_amount=51.77,
            currency="GBP",
            availability_status="in_stock",
            rating="Three",
            attributes={},
        ),
        ParsedItem(
            canonical_url="https://books.toscrape.com/catalogue/tipping-the-velvet_999/index.html",
            title="Tipping the Velvet",
            price_amount=53.74,
            currency="GBP",
            availability_status="in_stock",
            rating="One",
            attributes={},
        ),
    ]

    enriched_items = adapter.enrich_items(_make_source(), items)

    assert enriched_items[0].attributes["category"] == "Travel"
    assert enriched_items[1].attributes["category"] == "Travel"


def test_books_adapter_handles_missing_fields_fixture(monkeypatch, adapter) -> None:
    monkeypatch.setattr(
        "app.parsers.books_toscrape.requests.Session",
        lambda: FakeSession(
            {
                "https://books.toscrape.com/catalogue/page-1.html": _load_fixture(
                    "catalog_missing_fields.html"
                )
            }
        ),
    )

    result = adapter.parse(_make_source())

    assert result.pages_fetched == 1
    assert len(result.items) == 1
    assert result.items[0].title == "Mystery Without Metadata"
    assert result.items[0].price_amount is None
    assert result.items[0].rating is None
    assert result.items[0].availability_status == "out_of_stock"


def test_books_adapter_warns_when_catalog_markup_changes(monkeypatch, adapter) -> None:
    monkeypatch.setattr(
        "app.parsers.books_toscrape.requests.Session",
        lambda: FakeSession(
            {
                "https://books.toscrape.com/catalogue/page-1.html": _load_fixture(
                    "catalog_changed_markup.html"
                )
            }
        ),
    )

    result = adapter.parse(_make_source())

    assert result.pages_fetched == 1
    assert result.items == []
    assert result.warnings == [
        "No product cards found on https://books.toscrape.com/catalogue/page-1.html"
    ]


def test_books_adapter_returns_none_category_on_changed_detail_markup(monkeypatch, adapter) -> None:
    monkeypatch.setattr(
        "app.parsers.books_toscrape.requests.get",
        _detail_get_factory(
            {
                "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html": _load_fixture(
                    "product_detail_changed_markup.html"
                )
            }
        ),
    )

    item = ParsedItem(
        canonical_url="https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
        title="A Light in the Attic",
        price_amount=51.77,
        currency="GBP",
        availability_status="in_stock",
        rating="Three",
        attributes={},
    )

    enriched_items = adapter.enrich_items(_make_source(), [item])

    assert enriched_items[0].attributes == {}
