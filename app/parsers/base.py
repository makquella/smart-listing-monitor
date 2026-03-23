from abc import ABC, abstractmethod

from app.models.source import Source
from app.services.types import ParsedItem, ParseResult


class BaseSourceAdapter(ABC):
    parser_key: str

    @property
    def display_name(self) -> str:
        return self.parser_key.replace("_", " ").title()

    def supported_categories(self) -> list[str]:
        return []

    def requires_enrichment(
        self, item: ParsedItem, existing_attributes: dict | None = None
    ) -> bool:
        return not item.attributes.get("category")

    def enrich_items(self, source: Source, items: list[ParsedItem]) -> list[ParsedItem]:
        return items

    @abstractmethod
    def parse(self, source: Source) -> ParseResult:
        raise NotImplementedError
