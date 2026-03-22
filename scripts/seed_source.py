from app.core.config import get_settings
from app.core.db import SessionLocal, init_db
from app.repositories.sources import SourceRepository


def main() -> None:
    settings = get_settings()
    init_db()
    with SessionLocal() as session:
        source = SourceRepository(session).ensure_seed_source(settings)
        print(f"Seeded source #{source.id}: {source.name} ({source.slug})")


if __name__ == "__main__":
    main()
