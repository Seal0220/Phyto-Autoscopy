from __future__ import annotations

from pydantic import BaseModel


class SessionSummary(BaseModel):
    session_id: str
    created_at: str
    status: str
    session_path: str
    ended_at: str | None = None


class SessionDetail(SessionSummary):
    session_json: dict
