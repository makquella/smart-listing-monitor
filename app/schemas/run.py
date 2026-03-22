from datetime import datetime

from pydantic import BaseModel


class RunRead(BaseModel):
    id: int
    source_id: int
    status: str
    trigger_type: str
    started_at: datetime
    finished_at: datetime | None = None
    items_parsed: int
    events_count: int
    alerts_sent_count: int
