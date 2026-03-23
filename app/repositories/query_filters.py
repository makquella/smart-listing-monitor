from collections.abc import Iterable

from sqlalchemy import String, cast, func, or_


def text_search_clause(query: str, columns: Iterable):
    normalized = query.strip().lower()
    if not normalized:
        raise ValueError("Search query must be non-empty")
    pattern = f"%{normalized}%"
    return or_(
        *[func.lower(func.coalesce(cast(column, String), "")).like(pattern) for column in columns]
    )
