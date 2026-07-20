from __future__ import annotations

from pydantic import BaseModel


class DiskStatus(BaseModel):
    path: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    error: str | None = None


class SystemStatus(BaseModel):
    project_name: str
    project_name_zh: str
    device_name: str
    device_version: str
    mock_mode: bool
    active: bool
    started_at: str
    schedule_status: str
    active_record_id: str | None = None
    disk: DiskStatus
    recent_errors: list[str]
