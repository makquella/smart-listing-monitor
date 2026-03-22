from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.ai_summary import AISummary


class AISummaryRepository:
    def __init__(self, session: Session):
        self.session = session

    def save(self, summary: AISummary) -> AISummary:
        self.session.add(summary)
        self.session.flush()
        return summary

    def latest_for_source(self, source_id: int) -> AISummary | None:
        statement = (
            select(AISummary)
            .where(AISummary.source_id == source_id)
            .order_by(desc(AISummary.created_at))
            .limit(1)
        )
        return self.session.scalar(statement)

    def by_run(self, run_id: int) -> AISummary | None:
        statement = select(AISummary).where(AISummary.run_id == run_id).limit(1)
        return self.session.scalar(statement)
