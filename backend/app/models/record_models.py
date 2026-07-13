from __future__ import annotations

from pydantic import BaseModel


class RecordSummary(BaseModel):
    record_id: str
    created_at: str
    status: str
    record_path: str
    ended_at: str | None = None


class RecordDetail(RecordSummary):
    record_json: dict
