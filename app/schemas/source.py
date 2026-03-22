from datetime import datetime

from pydantic import BaseModel


class SourceRead(BaseModel):
    id: int
    name: str
    slug: str
    parser_key: str
    health_status: str
    schedule_enabled: bool
    schedule_interval_minutes: int
    is_active: bool
    last_successful_run_at: datetime | None = None
