from __future__ import annotations

import logging
from datetime import datetime, timezone
from threading import Lock
from typing import Protocol

from app.core.config import AppSettings
from app.core.exceptions import CameraError
from app.hardware.cameras.camera_identifier import scan_opencv_indices
from app.hardware.cameras.camera_registry import CameraRegistry
from app.hardware.cameras.camera_types import CameraFrame
from app.models.camera_models import CameraStatus

logger = logging.getLogger(__name__)


class CameraManagerInterface(Protocol):
    def start(self) -> None: ...

    def scan(self) -> list[dict]: ...

    def get_status(self, camera_id: str) -> CameraStatus: ...

    def get_statuses(self) -> list[CameraStatus]: ...

    def capture(self, camera_id: str) -> CameraFrame: ...

    def reconnect(self, camera_id: str) -> CameraStatus: ...

    def close_all(self) -> None: ...


class OpenCVCameraManager:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.registry = CameraRegistry(settings)
        self._lock = Lock()
        self._connected: dict[str, bool] = {}
        self._last_error: dict[str, str | None] = {}

    def start(self) -> None:
        self.scan()

    def scan(self) -> list[dict]:
        scan_results = scan_opencv_indices(self.settings.hardware.camera_scan_max_index)
        connected_indices = {item.device_index for item in scan_results if item.connected}
        for camera_id, config in self.registry.all().items():
            self._connected[camera_id] = config.enabled and config.device_index in connected_indices
            self._last_error[camera_id] = None if self._connected[camera_id] else "Camera not connected"
        return [item.__dict__ for item in scan_results]

    def get_status(self, camera_id: str) -> CameraStatus:
        config = self.registry.get(camera_id)
        return CameraStatus(
            camera_id=camera_id,
            camera_name=config.device_name,
            device_index=config.device_index,
            enabled=config.enabled,
            connected=self._connected.get(camera_id, False),
            width=config.width,
            height=config.height,
            fps=config.preview_fps,
            last_error=self._last_error.get(camera_id),
        )

    def get_statuses(self) -> list[CameraStatus]:
        return [self.get_status(camera_id) for camera_id in self.registry.roles()]

    def capture(self, camera_id: str) -> CameraFrame:
        config = self.registry.get(camera_id)
        if not config.enabled:
            raise CameraError(f"相機 {camera_id} 尚未啟用。")

        try:
            import cv2  # type: ignore
        except ImportError as exc:
            self._last_error[camera_id] = str(exc)
            raise CameraError("尚未安裝 OpenCV 相機驅動程式。") from exc

        with self._lock:
            capture = cv2.VideoCapture(config.device_index, cv2.CAP_DSHOW)
            try:
                if not capture or not capture.isOpened():
                    self._connected[camera_id] = False
                    raise CameraError(f"相機 {camera_id} 未連線。")

                capture.set(cv2.CAP_PROP_FRAME_WIDTH, config.width)
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT, config.height)
                capture.set(cv2.CAP_PROP_FPS, config.capture_fps)

                ok, frame = capture.read()
                if not ok:
                    raise CameraError(f"相機 {camera_id} 讀取影像失敗。")

                ok, encoded = cv2.imencode(
                    ".jpg",
                    frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), config.jpeg_quality],
                )
                if not ok:
                    raise CameraError(f"相機 {camera_id} 影像編碼失敗。")

                self._connected[camera_id] = True
                self._last_error[camera_id] = None
                return CameraFrame(
                    camera_id=camera_id,
                    data=encoded.tobytes(),
                    timestamp=datetime.now(timezone.utc),
                )
            except CameraError as exc:
                self._last_error[camera_id] = str(exc)
                logger.warning("Camera capture failed: %s", exc)
                raise
            finally:
                if capture:
                    capture.release()

    def reconnect(self, camera_id: str) -> CameraStatus:
        self.scan()
        return self.get_status(camera_id)

    def close_all(self) -> None:
        self._connected = {camera_id: False for camera_id in self.registry.roles()}
