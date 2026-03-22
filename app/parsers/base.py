from abc import ABC, abstractmethod

from app.models.source import Source
from app.services.types import ParseResult, ParsedItem


class BaseSourceAdapter(ABC):
    parser_key: str

    @property
    def display_name(self) -> str:
        return self.parser_key.replace("_", " ").title()

    def supported_categories(self) -> list[str]:
        return []

    def enrich_items(self, source: Source, items: list[ParsedItem]) -> list[ParsedItem]:
        return items

    @abstractmethod
    def parse(self, source: Source) -> ParseResult:
        raise NotImplementedError
