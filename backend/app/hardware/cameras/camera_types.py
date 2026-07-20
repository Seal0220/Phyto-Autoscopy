from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class CameraFrame:
    camera_id: str
    data: bytes
    content_type: str = "image/jpeg"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class CameraScanResult:
    camera_id: str | None
    device_index: int
    connected: bool
    error: str | None = None
    camera_name: str | None = None
    device_name: str | None = None
    in_use: bool = False
    backend: str | None = None
