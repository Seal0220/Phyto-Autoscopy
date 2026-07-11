from __future__ import annotations

from pydantic import BaseModel


class MetadataRecord(BaseModel):
    project_name: str
    project_name_zh: str
    device_name: str
    session_id: str
    cycle_id: int | None
    camera_id: str
    camera_name: str
    timestamp: str
    angle_deg: float | None
    motor_position_deg: float | None
    file_path: str
    status: str
    error_message: str | None = None
