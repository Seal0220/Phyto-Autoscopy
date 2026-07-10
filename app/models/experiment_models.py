from __future__ import annotations

from pydantic import BaseModel, Field


class ExperimentStatus(BaseModel):
    status: str
    session_id: str | None = None
    cycle_count: int = 0
    last_error: str | None = None


class ExperimentStartRequest(BaseModel):
    capture_interval_seconds: int | None = Field(default=None, gt=0)
    duration_minutes: int | None = Field(default=None, gt=0)
    rotation_start_deg: float | None = None
    rotation_end_deg: float | None = None
    rotation_step_deg: float | None = Field(default=None, gt=0)
