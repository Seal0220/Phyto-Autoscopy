from __future__ import annotations

from pydantic import BaseModel, Field


class CameraStatus(BaseModel):
    camera_id: str
    camera_name: str
    device_index: int | None = None
    enabled: bool = True
    connected: bool = False
    previewing: bool = False
    width: int | None = None
    height: int | None = None
    preview_fps: int | None = None
    actual_fps: float = Field(default=0.0, ge=0)
    last_error: str | None = None


class CaptureRequest(BaseModel):
    record_id: str | None = None
    cycle_id: int | None = None
    angle_deg: float | None = None


class CaptureResult(BaseModel):
    record_id: str
    cycle_id: int | None = None
    camera_id: str
    camera_name: str
    timestamp: str
    angle_deg: float | None = None
    motor_position_deg: float | None = None
    file_path: str
    status: str
    error_message: str | None = None


class SnapshotResult(BaseModel):
    camera_id: str
    camera_name: str
    timestamp: str
    file_path: str
    status: str = "success"


class CameraSettingsUpdate(BaseModel):
    device_index: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    preview_fps: int | None = Field(default=None, ge=1, le=60)
    capture_fps: int | None = Field(default=None, ge=1, le=60)
    jpeg_quality: int | None = Field(default=None, ge=1, le=100)
    enabled: bool | None = None
