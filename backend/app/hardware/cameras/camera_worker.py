from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from threading import Condition, Event, Lock, Thread, current_thread
from typing import Any

from app.core.config import CameraConfig
from app.core.exceptions import CameraError
from app.hardware.cameras.camera_identifier import open_opencv_capture
from app.hardware.cameras.camera_types import CameraFrame
from app.hardware.cameras.highlight_exposure_controller import (
    CameraHighlightExposureController,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CameraWorkerState:
    connected: bool
    error: str | None
    backend: str | None
    sequence: int
    actual_fps: float
    exposure_value: float | None
    metering_region: tuple[float, float, float, float] | None
    overexposed_regions: tuple[tuple[float, float, float, float], ...]


class CameraWorker:
    """Own one persistent VideoCapture and publish its newest encoded frame."""

    _OPEN_RETRY_SECONDS = 1.0
    _MAX_OPEN_RETRY_SECONDS = 30.0
    _READ_FAILURE_LIMIT = 3
    _FRAME_WAIT_SECONDS = 3.0
    _CLOSE_TIMEOUT_SECONDS = 2.0
    _FPS_SMOOTHING_FACTOR = 0.25

    def __init__(
        self,
        camera_id: str,
        config: CameraConfig,
        cv2_module: Any,
    ) -> None:
        self.camera_id = camera_id
        self.config = config.model_copy(deep=True)
        self.cv2 = cv2_module
        self.signature = self._config_signature(self.config)
        self._exposure_controller = CameraHighlightExposureController(
            camera_id,
            cv2_module,
        )

        self._condition = Condition(Lock())
        self._capture_lock = Lock()
        self._capture: Any | None = None
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._frame: CameraFrame | None = None
        self._frame_monotonic = 0.0
        self._previous_frame_monotonic = 0.0
        self._actual_fps = 0.0
        self._sequence = time.monotonic_ns()
        self._connected = False
        self._last_error: str | None = "正在連線相機。"
        self._backend: str | None = None

    @staticmethod
    def _config_signature(config: CameraConfig) -> tuple[Any, ...]:
        return (
            config.enabled,
            config.device_index,
            config.width,
            config.height,
            config.capture_fps,
            config.jpeg_quality,
        )

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(
            target=self._run,
            name=f"camera-{self.camera_id}",
            daemon=True,
        )
        self._thread.start()

    def is_running(self) -> bool:
        thread = self._thread
        return bool(
            thread is not None
            and thread.is_alive()
            and not self._stop_event.is_set()
        )

    def close(self) -> bool:
        self._stop_event.set()
        with self._condition:
            self._condition.notify_all()
        thread = self._thread
        if thread is not None and thread is not current_thread():
            # VideoCapture.read() and release() are intentionally owned by the
            # reader thread.  Releasing from this thread while read() blocks
            # can deadlock some Windows camera drivers.
            thread.join(timeout=self._CLOSE_TIMEOUT_SECONDS)
            if thread.is_alive():
                logger.warning(
                    "Camera reader did not stop within timeout: %s",
                    self.camera_id,
                )
        stopped = thread is None or not thread.is_alive()
        if stopped:
            self._thread = None
        self._set_disconnected("相機連線已關閉。")
        return stopped

    def state(self) -> CameraWorkerState:
        exposure = self._exposure_controller.status()
        with self._condition:
            actual_fps = self._actual_fps if self._frame_is_current() else 0.0
            return CameraWorkerState(
                connected=self._connected,
                error=self._last_error,
                backend=self._backend,
                sequence=self._sequence,
                actual_fps=round(actual_fps, 2),
                exposure_value=exposure.exposure_value,
                metering_region=exposure.metering_region,
                overexposed_regions=exposure.overexposed_regions,
            )

    def set_metering_region(self, metering_region: Any | None) -> None:
        self._exposure_controller.set_metering_region(metering_region)

    def wait_for_frame(
        self,
        *,
        after_sequence: int | None = None,
        timeout: float = _FRAME_WAIT_SECONDS,
    ) -> tuple[CameraFrame, int]:
        deadline = time.monotonic() + max(0.0, timeout)
        with self._condition:
            while not self._stop_event.is_set():
                is_new = (
                    self._frame is not None
                    and (after_sequence is None or self._sequence > after_sequence)
                )
                if is_new and self._frame_is_current():
                    return self._frame, self._sequence

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(remaining)

            detail = self._last_error or "暫時沒有可用影格。"
        raise CameraError(f"相機 {self.camera_id} 無法取得影像：{detail}")

    def _frame_is_current(self) -> bool:
        if self._frame is None or not self._connected:
            return False
        maximum_age = max(1.0, 3.0 / max(1, self.config.capture_fps))
        return time.monotonic() - self._frame_monotonic <= maximum_age

    def _run(self) -> None:
        open_retry_seconds = self._OPEN_RETRY_SECONDS
        while not self._stop_event.is_set():
            try:
                capture, backend, error = open_opencv_capture(
                    self.config.device_index,
                    cv2_module=self.cv2,
                )
            except Exception:
                detail = "相機開啟發生未預期錯誤，正在重新連線。"
                if self._set_disconnected(detail):
                    logger.exception(
                        "相機 %s 開啟時發生未預期錯誤。",
                        self.camera_id,
                    )
                self._stop_event.wait(open_retry_seconds)
                open_retry_seconds = min(
                    self._MAX_OPEN_RETRY_SECONDS,
                    open_retry_seconds * 2,
                )
                continue
            if capture is None:
                detail = error or "相機裝置無法開啟。"
                if self._set_disconnected(detail):
                    logger.warning(
                        "相機 %s 連線失敗：%s",
                        self.camera_id,
                        detail,
                    )
                self._stop_event.wait(open_retry_seconds)
                open_retry_seconds = min(
                    self._MAX_OPEN_RETRY_SECONDS,
                    open_retry_seconds * 2,
                )
                continue

            published_frame = False

            with self._capture_lock:
                if self._stop_event.is_set():
                    try:
                        capture.release()
                    except Exception:
                        logger.debug("Failed to release stopped camera", exc_info=True)
                    return
                self._capture = capture

            try:
                self._configure_capture(capture, backend)
                if self._stop_event.is_set():
                    continue
                with self._condition:
                    self._backend = backend

                read_failures = 0
                while not self._stop_event.is_set():
                    started_at = time.monotonic()
                    try:
                        ok, image = capture.read()
                    except Exception:
                        ok, image = False, None
                        logger.debug(
                            "OpenCV read raised for camera %s",
                            self.camera_id,
                            exc_info=True,
                        )

                    if not ok or image is None:
                        read_failures += 1
                        detail = "相機讀取影像失敗，正在重新連線。"
                        if self._set_disconnected(detail):
                            logger.warning(
                                "相機 %s 讀取失敗，正在重新連線。",
                                self.camera_id,
                            )
                        if read_failures >= self._READ_FAILURE_LIMIT:
                            break
                        self._stop_event.wait(0.1)
                        continue

                    if self._stop_event.is_set():
                        break

                    self._exposure_controller.observe(
                        image,
                        started_at,
                    )

                    if not self._exposure_controller.should_publish(
                        image,
                        started_at,
                    ):
                        continue

                    try:
                        encoded_ok, encoded = self.cv2.imencode(
                            ".jpg",
                            image,
                            [
                                int(self.cv2.IMWRITE_JPEG_QUALITY),
                                self.config.jpeg_quality,
                            ],
                        )
                    except Exception:
                        encoded_ok, encoded = False, None
                        logger.debug(
                            "OpenCV encoding raised for camera %s",
                            self.camera_id,
                            exc_info=True,
                        )
                    if not encoded_ok or encoded is None:
                        read_failures += 1
                        detail = "相機影像編碼失敗，正在重新連線。"
                        if self._set_disconnected(detail):
                            logger.warning(
                                "相機 %s 影像編碼失敗，正在重新連線。",
                                self.camera_id,
                            )
                        if read_failures >= self._READ_FAILURE_LIMIT:
                            break
                        continue

                    if self._stop_event.is_set():
                        break

                    read_failures = 0
                    frame = CameraFrame(
                        camera_id=self.camera_id,
                        data=encoded.tobytes(),
                        raw_image=image,
                    )
                    with self._condition:
                        if self._stop_event.is_set():
                            break
                        recovery_detail = self._last_error
                        self._frame = frame
                        published_at = time.monotonic()
                        self._update_actual_fps(published_at)
                        self._frame_monotonic = published_at
                        self._sequence += 1
                        self._connected = True
                        self._last_error = None
                        self._condition.notify_all()
                    published_frame = True
                    open_retry_seconds = self._OPEN_RETRY_SECONDS
                    if recovery_detail not in (None, "正在連線相機。"):
                        logger.info(
                            "相機 %s 已恢復影像串流。",
                            self.camera_id,
                        )

                    frame_interval = 1.0 / max(1, self.config.capture_fps)
                    remaining = frame_interval - (time.monotonic() - started_at)
                    if remaining > 0:
                        self._stop_event.wait(remaining)
            except Exception:
                detail = "相機設定套用失敗，正在重新連線。"
                if self._set_disconnected(detail):
                    logger.exception(
                        "相機 %s 設定套用失敗，正在重新連線。",
                        self.camera_id,
                    )
            finally:
                self._release_capture(capture)

            if not self._stop_event.is_set():
                self._stop_event.wait(open_retry_seconds)
                if not published_frame:
                    open_retry_seconds = min(
                        self._MAX_OPEN_RETRY_SECONDS,
                        open_retry_seconds * 2,
                    )

    def _configure_capture(
        self,
        capture: Any,
        backend: str | None,
    ) -> None:
        properties: list[tuple[Any, Any]] = []
        fourcc_property = getattr(self.cv2, "CAP_PROP_FOURCC", None)
        fourcc_factory = getattr(self.cv2, "VideoWriter_fourcc", None)
        if fourcc_property is not None and fourcc_factory is not None:
            properties.append((fourcc_property, fourcc_factory(*"MJPG")))
        properties.extend((
            (getattr(self.cv2, "CAP_PROP_BUFFERSIZE", None), 1),
            (getattr(self.cv2, "CAP_PROP_FRAME_WIDTH", None), self.config.width),
            (getattr(self.cv2, "CAP_PROP_FRAME_HEIGHT", None), self.config.height),
            (getattr(self.cv2, "CAP_PROP_FPS", None), self.config.capture_fps),
        ))
        for prop, value in properties:
            if prop is None:
                continue
            try:
                capture.set(prop, value)
            except Exception:
                logger.debug(
                    "Camera property is unsupported: %s (%s)",
                    self.camera_id,
                    prop,
                    exc_info=True,
                )
        self._exposure_controller.configure(
            capture,
            backend,
            self.config.metering_region,
        )

    def _set_disconnected(self, error: str) -> bool:
        with self._condition:
            changed = self._connected or self._last_error != error
            self._connected = False
            self._last_error = error
            self._previous_frame_monotonic = 0.0
            self._actual_fps = 0.0
            self._condition.notify_all()
        return changed

    def _update_actual_fps(self, published_at: float) -> None:
        previous = self._previous_frame_monotonic
        self._previous_frame_monotonic = published_at

        if previous <= 0 or published_at <= previous:
            self._actual_fps = 0.0
            return

        measured_fps = 1.0 / (published_at - previous)
        if self._actual_fps <= 0:
            self._actual_fps = measured_fps
            return

        factor = self._FPS_SMOOTHING_FACTOR
        self._actual_fps = (
            self._actual_fps * (1.0 - factor)
            + measured_fps * factor
        )

    def _release_capture(self, expected: Any | None = None) -> None:
        with self._capture_lock:
            if expected is not None and self._capture is not expected:
                return
            capture = self._capture
            self._capture = None
        if capture is None:
            return
        try:
            capture.release()
        except Exception:
            logger.warning(
                "Failed to release OpenCV camera: %s",
                self.camera_id,
                exc_info=True,
            )
