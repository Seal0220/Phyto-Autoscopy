from __future__ import annotations

import time
from threading import Condition, Lock

from app.core.config import AppSettings
from app.core.exceptions import CameraError
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
        self._condition = Condition(Lock())
        self._frames: dict[str, CameraFrame] = {}
        self._frame_monotonic: dict[str, float] = {}
        self._actual_fps: dict[str, float] = {}
        self._sequences: dict[str, int] = {}
        self._generating: set[str] = set()
        self._preview_clients: dict[str, int] = {}
        self._last_error: dict[str, str | None] = {
            camera_id: None for camera_id in self.registry.roles()
        }

    def start(self) -> None:
        return None

    def reconfigure(self) -> None:
        with self._condition:
            self._frames.clear()
            self._frame_monotonic.clear()
            self._actual_fps.clear()
            for camera_id in self.registry.roles():
                self._last_error[camera_id] = None
            self._condition.notify_all()

    def scan(self) -> list[dict]:
        return [
            {
                "camera_id": camera_id,
                "camera_name": config.device_name,
                "device_index": config.device_index,
                "connected": config.enabled,
                "error": None if config.enabled else "相機未啟用。",
                "in_use": config.enabled,
                "backend": "MOCK",
                "mock": True,
            }
            for camera_id, config in self.registry.all().items()
        ]

    def get_status(self, camera_id: str) -> CameraStatus:
        config = self.registry.get(camera_id)
        with self._condition:
            previewing = self._preview_clients.get(camera_id, 0) > 0
            last_error = self._last_error.get(camera_id)
            latest_frame_at = self._frame_monotonic.get(camera_id, 0.0)
            maximum_age = max(1.0, 3.0 / max(1, config.capture_fps))
            actual_fps = self._actual_fps.get(camera_id, 0.0)
            if time.monotonic() - latest_frame_at > maximum_age:
                actual_fps = 0.0
        return CameraStatus(
            camera_id=camera_id,
            camera_name=config.device_name,
            device_index=config.device_index,
            enabled=config.enabled,
            connected=config.enabled,
            previewing=previewing,
            width=config.width,
            height=config.height,
            preview_fps=config.preview_fps,
            actual_fps=round(actual_fps, 2),
            last_error=last_error,
        )

    def get_statuses(self) -> list[CameraStatus]:
        return [self.get_status(camera_id) for camera_id in self.registry.roles()]

    def capture(self, camera_id: str) -> CameraFrame:
        config = self.registry.get(camera_id)
        if not config.enabled:
            with self._condition:
                self._last_error[camera_id] = "相機未啟用。"
            raise CameraError(f"相機 {camera_id} 尚未啟用。")
        with self._condition:
            sequence = self._sequences.get(camera_id, 0)
        frame, _sequence = self.wait_for_frame(
            camera_id,
            after_sequence=sequence,
        )
        return frame

    def wait_for_frame(
        self,
        camera_id: str,
        after_sequence: int | None = None,
        timeout: float = 3.0,
    ) -> tuple[CameraFrame, int]:
        config = self.registry.get(camera_id)
        if not config.enabled:
            raise CameraError(f"相機 {camera_id} 尚未啟用。")

        deadline = time.monotonic() + max(0.0, timeout)

        while True:
            with self._condition:
                frame = self._frames.get(camera_id)
                sequence = self._sequences.get(camera_id, 0)
                if frame is not None and (
                    after_sequence is None
                    or sequence > after_sequence
                ):
                    return frame, sequence

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    detail = self._last_error.get(camera_id) or "暫時沒有可用影格。"
                    raise CameraError(f"相機 {camera_id} 無法取得影像：{detail}")

                frame_interval = 1.0 / max(1, config.capture_fps)
                ready_at = self._frame_monotonic.get(camera_id, 0.0) + frame_interval
                wait_for = max(0.0, ready_at - time.monotonic())
                if camera_id in self._generating or wait_for > 0:
                    self._condition.wait(min(remaining, max(0.001, wait_for)))
                    continue

                self._generating.add(camera_id)
                next_sequence = sequence + 1

            try:
                next_frame = CameraFrame(
                    camera_id=camera_id,
                    data=make_mock_jpeg(camera_id, next_sequence),
                )
            except Exception as exc:
                with self._condition:
                    self._generating.discard(camera_id)
                    self._last_error[camera_id] = "模擬相機擷取失敗。"
                    self._condition.notify_all()
                raise CameraError("模擬相機擷取失敗。") from exc

            with self._condition:
                published_at = time.monotonic()
                previous_frame_at = self._frame_monotonic.get(camera_id, 0.0)
                previous_fps = self._actual_fps.get(camera_id, 0.0)
                if previous_frame_at > 0 and published_at > previous_frame_at:
                    measured_fps = 1.0 / (published_at - previous_frame_at)
                    self._actual_fps[camera_id] = (
                        measured_fps
                        if previous_fps <= 0
                        else previous_fps * 0.75 + measured_fps * 0.25
                    )
                else:
                    self._actual_fps[camera_id] = 0.0
                self._frames[camera_id] = next_frame
                self._frame_monotonic[camera_id] = published_at
                self._sequences[camera_id] = next_sequence
                self._generating.discard(camera_id)
                self._last_error[camera_id] = None
                self._condition.notify_all()
                return next_frame, next_sequence

    def begin_preview(self, camera_id: str) -> None:
        self.registry.get(camera_id)
        with self._condition:
            self._preview_clients[camera_id] = (
                self._preview_clients.get(camera_id, 0) + 1
            )

    def end_preview(self, camera_id: str) -> None:
        with self._condition:
            remaining = max(0, self._preview_clients.get(camera_id, 0) - 1)
            if remaining:
                self._preview_clients[camera_id] = remaining
            else:
                self._preview_clients.pop(camera_id, None)

    def reconnect(self, camera_id: str) -> CameraStatus:
        self.registry.get(camera_id)
        with self._condition:
            self._frames.pop(camera_id, None)
            self._frame_monotonic.pop(camera_id, None)
            self._actual_fps.pop(camera_id, None)
            self._last_error[camera_id] = None
            self._condition.notify_all()
        return self.get_status(camera_id)

    def reconnect_all(self) -> list[CameraStatus]:
        with self._condition:
            self._frames.clear()
            self._frame_monotonic.clear()
            self._actual_fps.clear()
            for camera_id in self.registry.roles():
                self._last_error[camera_id] = None
            self._condition.notify_all()
        return self.get_statuses()

    def close_all(self) -> None:
        with self._condition:
            self._frames.clear()
            self._frame_monotonic.clear()
            self._actual_fps.clear()
            self._sequences.clear()
            self._generating.clear()
            self._preview_clients.clear()
            self._condition.notify_all()
