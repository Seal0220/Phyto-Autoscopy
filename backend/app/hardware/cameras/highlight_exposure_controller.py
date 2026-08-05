from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ExposureMetrics:
    median: float
    high: float
    peak: float
    clipped_ratio: float


@dataclass(frozen=True)
class _PendingExposure:
    previous: float
    requested: float
    direction: int
    high_before: float


class CameraHighlightExposureController:
    """Continuously protect highlights without chasing individual frames."""

    _LOWER_HALF_METERING_CAMERAS = frozenset({"side", "rotating"})
    _MEASUREMENT_WINDOW_SECONDS = 1.0
    _EMA_ALPHA = 0.25
    _SAMPLE_STRIDE = 8
    _CLIPPED_LEVEL = 250.0

    _BRIGHT_CONFIRMATION_WINDOWS = 3
    _SEVERE_CONFIRMATION_WINDOWS = 2
    _DARK_CONFIRMATION_WINDOWS = 6
    _MINIMUM_WRITE_INTERVAL_SECONDS = 3.0
    _REVERSAL_COOLDOWN_SECONDS = 10.0
    _SETTLING_SECONDS = 1.5
    _NATIVE_AUTO_SETTLING_SECONDS = 1.0

    _EXPOSURE_STEP = 1.0
    _PROPERTY_TOLERANCE = 0.25
    _MINIMUM_VISIBLE_RESPONSE = 6.0
    _MAXIMUM_FAILED_COMMANDS = 2

    def __init__(
        self,
        camera_id: str,
        cv2_module: Any,
    ) -> None:
        self.camera_id = camera_id
        self.cv2 = cv2_module
        self._capture: Any | None = None
        self._backend: str | None = None
        self._exposure_property: Any | None = None
        self._current_exposure: float | None = None
        self._custom_control_available = True
        self._manual_exposure = False
        self._control_verified = False
        self._blocked_direction = 0

        self._window_started_at: float | None = None
        self._window_metrics: list[_ExposureMetrics] = []
        self._smoothed_metrics: _ExposureMetrics | None = None
        self._bright_windows = 0
        self._severe_windows = 0
        self._dark_windows = 0

        self._last_write_at = float("-inf")
        self._last_direction = 0
        self._settling_until = 0.0
        self._pending_exposure: _PendingExposure | None = None
        self._failed_commands = 0

    def configure(
        self,
        capture: Any,
        backend: str | None,
    ) -> None:
        self._capture = capture
        self._backend = backend
        self._exposure_property = getattr(
            self.cv2,
            "CAP_PROP_EXPOSURE",
            None,
        )
        self._custom_control_available = self._exposure_property is not None
        self._manual_exposure = False
        self._control_verified = False
        self._blocked_direction = 0
        self._pending_exposure = None
        self._failed_commands = 0
        self._last_write_at = float("-inf")
        self._last_direction = 0
        self._settling_until = 0.0
        self._current_exposure = None
        self._reset_meter()

        if self._exposure_property is None:
            logger.warning(
                "相機 %s 未提供硬體曝光控制，保留原生自動曝光。",
                self.camera_id,
            )
            return

        initial_exposure = self._read_exposure()
        if initial_exposure is None:
            self._custom_control_available = False
            logger.warning(
                "相機 %s 無法讀取硬體曝光值，保留原生自動曝光。",
                self.camera_id,
            )
            return

        self._current_exposure = initial_exposure

    def should_publish(
        self,
        image: Any,
        measured_at: float,
    ) -> bool:
        if measured_at < self._settling_until:
            return False

        pending = self._pending_exposure
        if pending is None:
            return True

        if str(self._backend or "").upper() == "MSMF":
            # MSMF 的 CAP_PROP_EXPOSURE 讀值是驅動預設值，不是目前值；
            # set() 成功後以最後下達的值繼續逐級調整，避免每次都重寫同一級。
            self._pending_exposure = None
            self._current_exposure = pending.requested
            self._control_verified = True
            self._blocked_direction = 0
            self._failed_commands = 0
            self._reset_meter()
            return True

        metrics = self._measure_frame(image)
        self._pending_exposure = None
        if metrics is not None and self._exposure_change_applied(
            pending,
            metrics,
        ):
            applied = self._read_exposure()
            self._current_exposure = (
                applied
                if applied is not None
                else pending.requested
            )
            self._control_verified = True
            self._blocked_direction = 0
            self._failed_commands = 0
            self._reset_meter()
            return True

        if self._control_verified:
            # A controller that has already moved successfully has reached a
            # driver/hardware boundary in this direction.  Keep manual mode
            # and allow movement in the opposite direction later.
            self._blocked_direction = pending.direction
            self._current_exposure = self._read_exposure()
            self._reset_meter()
            return True

        self._failed_commands += 1
        self._restore_native_auto_exposure()
        self._reset_meter()
        self._settling_until = (
            measured_at
            + self._NATIVE_AUTO_SETTLING_SECONDS
        )
        if self._failed_commands >= self._MAXIMUM_FAILED_COMMANDS:
            self._custom_control_available = False
            logger.warning(
                "相機 %s 的驅動未套用曝光命令，已停止自訂控制並保留原生自動曝光。",
                self.camera_id,
            )
        return False

    def observe(
        self,
        image: Any,
        measured_at: float,
    ) -> None:
        if not self._custom_control_available:
            return

        metrics = self._measure_frame(image)
        if metrics is None:
            return

        if self._window_started_at is None:
            self._window_started_at = measured_at
        self._window_metrics.append(metrics)
        if (
            measured_at - self._window_started_at
            < self._MEASUREMENT_WINDOW_SECONDS
        ):
            return

        window_metrics = self._average_metrics(self._window_metrics)
        self._window_metrics.clear()
        self._window_started_at = measured_at
        self._smoothed_metrics = self._smooth_metrics(
            self._smoothed_metrics,
            window_metrics,
        )
        direction = self._next_direction(self._smoothed_metrics)
        if direction == 0 or not self._can_write(direction, measured_at):
            return

        self._apply_exposure_step(
            direction,
            self._smoothed_metrics,
            measured_at,
        )

    def _next_direction(
        self,
        metrics: _ExposureMetrics,
    ) -> int:
        severe = (
            metrics.high > 235.0
            or metrics.clipped_ratio > 0.10
        )
        bright = (
            metrics.high > 220.0
            or (
                metrics.peak > 248.0
                and metrics.clipped_ratio > 0.02
            )
        )

        if metrics.high < 180.0 and metrics.clipped_ratio < 0.02:
            bright = False
            severe = False
        if metrics.median < 25.0 and metrics.clipped_ratio <= 0.10:
            bright = False
            severe = False

        dark = (
            not bright
            and metrics.high < 170.0
            and metrics.peak < 225.0
            and metrics.clipped_ratio < 0.001
        )

        self._severe_windows = self._severe_windows + 1 if severe else 0
        self._bright_windows = self._bright_windows + 1 if bright else 0
        self._dark_windows = self._dark_windows + 1 if dark else 0

        if (
            self._severe_windows >= self._SEVERE_CONFIRMATION_WINDOWS
            or self._bright_windows >= self._BRIGHT_CONFIRMATION_WINDOWS
        ):
            self._reset_confirmation_windows()
            return -1
        if self._dark_windows >= self._DARK_CONFIRMATION_WINDOWS:
            self._reset_confirmation_windows()
            return 1
        return 0

    def _can_write(
        self,
        direction: int,
        measured_at: float,
    ) -> bool:
        elapsed = measured_at - self._last_write_at
        if direction == self._blocked_direction:
            return False
        if elapsed < self._MINIMUM_WRITE_INTERVAL_SECONDS:
            return False
        return not (
            self._last_direction not in (0, direction)
            and elapsed < self._REVERSAL_COOLDOWN_SECONDS
        )

    def _apply_exposure_step(
        self,
        direction: int,
        metrics: _ExposureMetrics,
        measured_at: float,
    ) -> None:
        current = self._current_exposure
        if current is None:
            current = self._read_exposure()
        if current is None:
            self._register_command_failure(
                measured_at,
                direction,
            )
            return

        requested = (
            current
            + direction * self._EXPOSURE_STEP
        )
        if math.isclose(
            requested,
            current,
            abs_tol=self._PROPERTY_TOLERANCE,
        ):
            return

        backend = str(self._backend or "").upper()
        if backend != "MSMF" and not self._enable_manual_exposure():
            self._register_command_failure(
                measured_at,
                direction,
            )
            return
        if not self._set_property(
            self._exposure_property,
            requested,
        ):
            self._register_command_failure(
                measured_at,
                direction,
            )
            return

        # MSMF 的曝光 setter 本身會以 Manual flag 寫入硬體。
        self._manual_exposure = True
        self._current_exposure = requested
        self._blocked_direction = 0
        self._failed_commands = 0
        self._pending_exposure = _PendingExposure(
            previous=current,
            requested=requested,
            direction=direction,
            high_before=metrics.high,
        )
        self._last_write_at = measured_at
        self._last_direction = direction
        self._settling_until = measured_at + self._SETTLING_SECONDS

    def _exposure_change_applied(
        self,
        pending: _PendingExposure,
        metrics: _ExposureMetrics,
    ) -> bool:
        applied = self._read_exposure()
        property_changed = (
            applied is not None
            and not math.isclose(
                applied,
                pending.previous,
                abs_tol=self._PROPERTY_TOLERANCE,
            )
        )
        visible_change = (
            pending.high_before - metrics.high
            if pending.direction < 0
            else metrics.high - pending.high_before
        )
        return property_changed or visible_change >= self._MINIMUM_VISIBLE_RESPONSE

    def _register_command_failure(
        self,
        measured_at: float,
        direction: int,
    ) -> None:
        self._failed_commands += 1
        self._last_write_at = measured_at
        self._reset_meter()

        if self._control_verified:
            # 只有 driver 明確拒絕寫入時才視為到達該方向的硬體邊界；
            # 保留目前手動曝光，之後仍可往反方向調整。
            self._blocked_direction = direction
            return

        self._restore_native_auto_exposure()
        self._settling_until = (
            measured_at
            + self._NATIVE_AUTO_SETTLING_SECONDS
        )
        if self._failed_commands >= self._MAXIMUM_FAILED_COMMANDS:
            self._custom_control_available = False
            logger.warning(
                "相機 %s 無法安全控制硬體曝光，已改用原生自動曝光。",
                self.camera_id,
            )

    def _enable_manual_exposure(self) -> bool:
        if self._manual_exposure:
            return True
        if self._capture is None:
            return False

        auto_property = getattr(
            self.cv2,
            "CAP_PROP_AUTO_EXPOSURE",
            None,
        )
        if auto_property is None:
            return False

        backend = str(self._backend or "").upper()
        values = (
            (0.0, 0.25)
            if backend == "MSMF"
            else (0.25, 0.0)
        )
        for value in values:
            if self._set_property(auto_property, value):
                self._manual_exposure = True
                return True
        return False

    def _restore_native_auto_exposure(self) -> None:
        if self._capture is None:
            return

        auto_property = getattr(
            self.cv2,
            "CAP_PROP_AUTO_EXPOSURE",
            None,
        )
        if auto_property is None:
            return

        backend = str(self._backend or "").upper()
        values = (
            (1.0, 0.75)
            if backend == "MSMF"
            else (0.75, 1.0)
        )
        for value in values:
            if self._set_property(auto_property, value):
                self._manual_exposure = False
                return

    def _set_property(
        self,
        property_id: Any,
        value: float,
    ) -> bool:
        if self._capture is None or property_id is None:
            return False
        try:
            return bool(self._capture.set(property_id, value))
        except Exception:
            return False

    def _read_exposure(self) -> float | None:
        if self._capture is None or self._exposure_property is None:
            return None
        try:
            value = float(self._capture.get(self._exposure_property))
        except Exception:
            return None
        return value if math.isfinite(value) else None

    def _measure_frame(
        self,
        image: Any,
    ) -> _ExposureMetrics | None:
        shape = getattr(image, "shape", None)
        if shape is None or len(shape) < 2:
            return None

        metering_image = image
        if self.camera_id in self._LOWER_HALF_METERING_CAMERAS:
            image_height = int(shape[0])
            metering_image = image[image_height // 2 :, :]

        try:
            sampled = np.asarray(
                metering_image[
                    ::self._SAMPLE_STRIDE,
                    ::self._SAMPLE_STRIDE,
                ],
                dtype=np.float32,
            )
        except Exception:
            return None
        if sampled.size == 0:
            return None

        if sampled.ndim >= 3 and sampled.shape[2] >= 3:
            luminance = (
                sampled[..., 0] * 0.114
                + sampled[..., 1] * 0.587
                + sampled[..., 2] * 0.299
            )
        else:
            luminance = sampled

        return _ExposureMetrics(
            median=float(np.percentile(luminance, 50.0)),
            high=float(np.percentile(luminance, 90.0)),
            peak=float(np.percentile(luminance, 99.0)),
            clipped_ratio=float(
                np.mean(luminance >= self._CLIPPED_LEVEL)
            ),
        )

    @staticmethod
    def _average_metrics(
        metrics: list[_ExposureMetrics],
    ) -> _ExposureMetrics:
        count = max(1, len(metrics))
        return _ExposureMetrics(
            median=sum(item.median for item in metrics) / count,
            high=sum(item.high for item in metrics) / count,
            peak=sum(item.peak for item in metrics) / count,
            clipped_ratio=(
                sum(item.clipped_ratio for item in metrics) / count
            ),
        )

    @classmethod
    def _smooth_metrics(
        cls,
        previous: _ExposureMetrics | None,
        current: _ExposureMetrics,
    ) -> _ExposureMetrics:
        if previous is None:
            return current

        alpha = cls._EMA_ALPHA
        retained = 1.0 - alpha
        return _ExposureMetrics(
            median=previous.median * retained + current.median * alpha,
            high=previous.high * retained + current.high * alpha,
            peak=previous.peak * retained + current.peak * alpha,
            clipped_ratio=(
                previous.clipped_ratio * retained
                + current.clipped_ratio * alpha
            ),
        )

    def _reset_meter(self) -> None:
        self._window_started_at = None
        self._window_metrics.clear()
        self._smoothed_metrics = None
        self._reset_confirmation_windows()

    def _reset_confirmation_windows(self) -> None:
        self._bright_windows = 0
        self._severe_windows = 0
        self._dark_windows = 0
