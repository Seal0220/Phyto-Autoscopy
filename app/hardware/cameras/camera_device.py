from __future__ import annotations

from typing import Protocol

from app.hardware.cameras.camera_types import CameraFrame
from app.models.camera_models import CameraStatus


class CameraInterface(Protocol):
    camera_id: str

    def open(self) -> None: ...

    def close(self) -> None: ...

    def status(self) -> CameraStatus: ...

    def capture(self) -> CameraFrame: ...
