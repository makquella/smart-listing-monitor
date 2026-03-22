import hashlib
import json
from urllib.parse import urljoin, urlparse

from app.models.source import Source
from app.services.types import NormalizedItem, ParsedItem


class NormalizationService:
    def build_source_item_key(self, source: Source, canonical_url: str) -> str:
        canonical_url = urljoin(source.base_url, canonical_url)
        parsed = urlparse(canonical_url)
        return parsed.path.lstrip("/")

    def canonicalize_url(self, source: Source, canonical_url: str) -> str:
        return urljoin(source.base_url, canonical_url)

    def normalize(self, source: Source, item: ParsedItem) -> NormalizedItem:
        canonical_url = self.canonicalize_url(source, item.canonical_url)
        source_item_key = self.build_source_item_key(source, item.canonical_url)

        comparison_payload = {
            "title": item.title.strip(),
            "price_amount": item.price_amount,
            "currency": item.currency,
            "availability_status": item.availability_status,
            "rating": item.rating,
            "attributes": item.attributes,
        }
        comparison_hash = hashlib.sha256(
            json.dumps(comparison_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

        return NormalizedItem(
            source_item_key=source_item_key,
            canonical_url=canonical_url,
            title=item.title.strip(),
            price_amount=item.price_amount,
            currency=item.currency,
            availability_status=item.availability_status,
            rating=item.rating,
            external_id=item.external_id,
            attributes=item.attributes,
            comparison_hash=comparison_hash,
        )
