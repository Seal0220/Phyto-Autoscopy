from __future__ import annotations

import logging
from datetime import datetime, timezone
from threading import RLock
from typing import Protocol

from app.core.config import AppSettings
from app.core.exceptions import CameraError, public_error_detail
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

    def reconnect_all(self) -> list[CameraStatus]: ...

    def close_all(self) -> None: ...


class OpenCVCameraManager:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.registry = CameraRegistry(settings)
        self._lock = RLock()
        self._connected: dict[str, bool] = {}
        self._last_error: dict[str, str | None] = {}

    def start(self) -> None:
        self.scan()

    def scan(self) -> list[dict]:
        with self._lock:
            scan_results = scan_opencv_indices(
                self.settings.hardware.camera_scan_max_index
            )
            connected_indices = {
                item.device_index for item in scan_results if item.connected
            }
            for camera_id, config in self.registry.all().items():
                self._connected[camera_id] = (
                    config.enabled
                    and config.device_index in connected_indices
                )
                if self._connected[camera_id]:
                    self._last_error[camera_id] = None
                elif not config.enabled:
                    self._last_error[camera_id] = "相機未啟用。"
                else:
                    self._last_error[camera_id] = "相機未連線。"
            return [item.__dict__ for item in scan_results]

    def get_status(self, camera_id: str) -> CameraStatus:
        with self._lock:
            config = self.registry.get(camera_id)
            return CameraStatus(
                camera_id=camera_id,
                camera_name=config.device_name,
                device_index=config.device_index,
                enabled=config.enabled,
                connected=self._connected.get(camera_id, False),
                width=config.width,
                height=config.height,
                preview_fps=config.preview_fps,
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
            self._last_error[camera_id] = "尚未安裝 OpenCV 相機驅動程式。"
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
                self._last_error[camera_id] = public_error_detail(exc)
                logger.warning("Camera capture failed: %s", exc)
                raise
            except Exception as exc:
                self._connected[camera_id] = False
                self._last_error[camera_id] = "相機擷取發生未預期錯誤。"
                logger.exception("Unexpected OpenCV camera failure: %s", camera_id)
                raise CameraError("相機擷取發生未預期錯誤。") from exc
            finally:
                if capture:
                    try:
                        capture.release()
                    except Exception:
                        logger.warning(
                            "Failed to release OpenCV camera: %s",
                            camera_id,
                            exc_info=True,
                        )

    def reconnect(self, camera_id: str) -> CameraStatus:
        self.scan()
        return self.get_status(camera_id)

    def reconnect_all(self) -> list[CameraStatus]:
        self.scan()
        return self.get_statuses()

    def close_all(self) -> None:
        with self._lock:
            self._connected = {
                camera_id: False for camera_id in self.registry.roles()
            }
