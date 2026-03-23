from pathlib import Path

from app.core.config import Settings
from app.models.source import Source
from app.parsers.books_toscrape import BooksToScrapeAdapter


class FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.encoding = "utf-8"

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, listing_html: str, detail_html: str):
        self.listing_html = listing_html
        self.detail_html = detail_html
        self.headers = {}

    def get(self, url: str, timeout: int) -> FakeResponse:
        return FakeResponse(self.listing_html)


def fake_detail_get(detail_html: str):
    def _get(url: str, timeout: int, headers=None) -> FakeResponse:
        return FakeResponse(detail_html)

    return _get


def test_books_adapter_parses_listing_cards(monkeypatch) -> None:
    html = Path("tests/fixtures/books_page.html").read_text(encoding="utf-8")
    detail_html = """
    <html>
      <body>
        <ul class="breadcrumb">
          <li><a href="/">Home</a></li>
          <li><a href="/books">Books</a></li>
          <li><a href="/travel">Travel</a></li>
        </ul>
      </body>
    </html>
    """
    monkeypatch.setattr(
        "app.parsers.books_toscrape.requests.Session", lambda: FakeSession(html, detail_html)
    )
    monkeypatch.setattr("app.parsers.books_toscrape.requests.get", fake_detail_get(detail_html))

    adapter = BooksToScrapeAdapter(Settings())
    source = Source(
        id=1,
        name="Books",
        slug="books",
        parser_key="books_toscrape",
        base_url="https://books.toscrape.com/",
        start_url="https://books.toscrape.com/",
        schedule_enabled=True,
        schedule_interval_minutes=60,
        is_active=True,
        health_status="healthy",
        consecutive_failures=0,
        created_at=None,
        updated_at=None,
    )

    result = adapter.parse(source)
    adapter.enrich_items(source, result.items)

    assert result.pages_fetched == 1
    assert len(result.items) == 2
    assert result.items[0].title == "A Light in the Attic"
    assert result.items[0].price_amount == 51.77
    assert result.items[0].availability_status == "in_stock"
    assert result.items[0].rating == "Three"
    assert result.items[0].attributes["category"] == "Travel"
