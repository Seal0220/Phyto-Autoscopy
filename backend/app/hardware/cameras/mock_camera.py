from __future__ import annotations

from datetime import datetime, timezone
from itertools import count

from app.core.config import AppSettings
from app.hardware.cameras.camera_registry import CameraRegistry
from app.hardware.cameras.camera_types import CameraFrame
from app.models.camera_models import CameraStatus


def make_mock_jpeg(camera_id: str, sequence: int) -> bytes:
    import cv2  # type: ignore
    import numpy as np

    image = np.zeros((360, 480, 3), dtype=np.uint8)
    image[:, :] = (36, 55, 44)
    cv2.rectangle(image, (24, 24), (456, 336), (210, 230, 214), 2)
    cv2.circle(image, (240, 180), 72, (80, 170, 110), -1)
    cv2.circle(image, (240, 180), 34, (245, 245, 238), -1)
    cv2.putText(
        image,
        "CHLOROCULUS",
        (42, 78),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (245, 245, 238),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        image,
        f"{camera_id} #{sequence}",
        (42, 308),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (245, 245, 238),
        2,
        cv2.LINE_AA,
    )
    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    if not ok:
        raise RuntimeError("模擬相機影像編碼失敗。")
    return encoded.tobytes()


class MockCameraManager:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.registry = CameraRegistry(settings)
        self._counter = count(1)
        self._last_error: dict[str, str | None] = {
            camera_id: None for camera_id in self.registry.roles()
        }

    def start(self) -> None:
        return None

    def scan(self) -> list[dict]:
        return [
            {
                "camera_id": camera_id,
                "device_index": config.device_index,
                "connected": config.enabled,
                "mock": True,
            }
            for camera_id, config in self.registry.all().items()
        ]

    def get_status(self, camera_id: str) -> CameraStatus:
        config = self.registry.get(camera_id)
        return CameraStatus(
            camera_id=camera_id,
            camera_name=config.device_name,
            device_index=config.device_index,
            enabled=config.enabled,
            connected=config.enabled,
            previewing=True,
            width=config.width,
            height=config.height,
            fps=config.preview_fps,
            last_error=self._last_error.get(camera_id),
        )

    def get_statuses(self) -> list[CameraStatus]:
        return [self.get_status(camera_id) for camera_id in self.registry.roles()]

    def capture(self, camera_id: str) -> CameraFrame:
        self.registry.get(camera_id)
        sequence = next(self._counter)
        return CameraFrame(
            camera_id=camera_id,
            data=make_mock_jpeg(camera_id, sequence),
            timestamp=datetime.now(timezone.utc),
        )

    def reconnect(self, camera_id: str) -> CameraStatus:
        return self.get_status(camera_id)

    def close_all(self) -> None:
        return None
