from datetime import datetime

from pydantic import BaseModel


class EventRead(BaseModel):
    id: int
    source_id: int
    item_id: int | None
    event_type: str
    severity: str
    summary_text: str
    is_suppressed: bool
    created_at: datetime
