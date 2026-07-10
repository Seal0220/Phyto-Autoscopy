from __future__ import annotations

from threading import Lock

from app.hardware.cameras.camera_types import CameraFrame


class FrameBuffer:
    def __init__(self) -> None:
        self._lock = Lock()
        self._frame: CameraFrame | None = None

    def set(self, frame: CameraFrame) -> None:
        with self._lock:
            self._frame = frame

    def get(self) -> CameraFrame | None:
        with self._lock:
            return self._frame
