from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from threading import Lock
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ExposureMetrics:
    median: float
    high: float
    peak: float
    highlight_ratio: float
    clipped_ratio: float


@dataclass(frozen=True)
class _PendingExposure:
    previous: float
    requested: float
    direction: int
    median_before: float
    high_before: float
    peak_before: float
    highlight_before: float
    clipped_before: float
    severe: bool


@dataclass(frozen=True)
class _ExposureControllerStatus:
    exposure_value: float | None
    metering_region: tuple[float, float, float, float] | None
    overexposed_regions: tuple[tuple[float, float, float, float], ...]


class CameraHighlightExposureController:
    _LOWER_HALF_METERING_CAMERAS = frozenset({"side", "rotating"})

    _MEASUREMENT_WINDOW_SECONDS = 1.0
    _EMA_ALPHA = 0.25
    _FUZZY_STATE_ALPHA = 0.25
    _SAMPLE_STRIDE = 8

    _HIGHLIGHT_LEVEL = 248.0
    _CLIPPED_LEVEL = 250.0
    _METERING_HORIZONTAL_INSET_RATIO = 0.08

    _ACCEPTABLE_HIGHLIGHT_RATIO = 0.30
    _HIGHLIGHT_WARNING_FULL_RATIO = 0.45
    _SEVERE_HIGHLIGHT_RATIO = 0.50
    _SEVERE_CLIPPED_RATIO = 0.40

    _HIGHLIGHT_DETECTION_INTERVAL_SECONDS = 0.5
    _HIGHLIGHT_SAMPLE_STRIDE = 4
    _MINIMUM_HIGHLIGHT_AREA_RATIO = 0.001
    _MAXIMUM_HIGHLIGHT_REGIONS = 8

    _FUZZY_DARK_MEDIAN_FULL = 65.0
    _FUZZY_DARK_MEDIAN_NONE = 95.0
    _FUZZY_DARK_HIGH_FULL = 125.0
    _FUZZY_DARK_HIGH_NONE = 175.0
    _FUZZY_DARK_PEAK_FULL = 185.0
    _FUZZY_DARK_PEAK_NONE = 225.0

    _FUZZY_BRIGHT_MEDIAN_NONE = 135.0
    _FUZZY_BRIGHT_MEDIAN_FULL = 175.0
    _FUZZY_BRIGHT_HIGH_NONE = 205.0
    _FUZZY_BRIGHT_HIGH_FULL = 240.0
    _FUZZY_BRIGHT_PEAK_NONE = 240.0
    _FUZZY_BRIGHT_PEAK_FULL = 253.0
    
    _FUZZY_BRIGHTEN_THRESHOLD = 0.55
    _FUZZY_DARKEN_THRESHOLD = -0.4

    _MINIMUM_WRITE_INTERVAL_SECONDS = 3.0
    _SEVERE_WRITE_INTERVAL_SECONDS = 0.75
    _SETTLING_SECONDS = 1.5
    _SEVERE_SETTLING_SECONDS = 0.75
    _NATIVE_AUTO_SETTLING_SECONDS = 1.0

    _EXPOSURE_STEP = 1.0
    _ADAPTIVE_EXPOSURE_THRESHOLD = 16.0

    _DARKEN_RATIO = 0.08
    _MINIMUM_DARKEN_STEP = 2.0
    _SEVERE_DARKEN_RATIO = 0.18
    _MINIMUM_SEVERE_DARKEN_STEP = 5.0
    _BRIGHTEN_RATIO = 0.05
    _MINIMUM_BRIGHTEN_STEP = 2.0

    _PROPERTY_TOLERANCE = 0.25
    _MINIMUM_VISIBLE_RESPONSE = 4.0
    _MINIMUM_RATIO_RESPONSE = 0.015

    _MAXIMUM_FAILED_COMMANDS = 2
    _MAXIMUM_MSMF_UNVERIFIED_COMMANDS = 8
    _BLOCKED_DIRECTION_RETRY_SECONDS = 15.0

    def __init__(self, camera_id: str, cv2_module: Any) -> None:
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
        self._blocked_until = 0.0

        self._window_started_at: float | None = None
        self._window_metrics: list[_ExposureMetrics] = []
        self._smoothed_metrics: _ExposureMetrics | None = None
        self._fuzzy_control_state = 0.0

        self._last_write_at = float("-inf")
        self._settling_until = 0.0
        self._pending_exposure: _PendingExposure | None = None
        self._failed_commands = 0

        self._status_lock = Lock()
        self._reported_exposure: float | None = None
        self._custom_metering_region: tuple[float, float, float, float] | None = None
        self._metering_region: tuple[float, float, float, float] | None = None
        self._overexposed_regions: tuple[tuple[float, float, float, float], ...] = ()
        self._last_highlight_detection_at = float("-inf")

    def configure(
        self,
        capture: Any,
        backend: str | None,
        metering_region: Any | None = None,
    ) -> None:
        self._capture = capture
        self._backend = backend
        self._exposure_property = getattr(self.cv2, "CAP_PROP_EXPOSURE", None)
        self._custom_control_available = self._exposure_property is not None
        self._manual_exposure = False
        self._control_verified = False
        self._blocked_direction = 0
        self._blocked_until = 0.0
        self._pending_exposure = None
        self._failed_commands = 0
        self._last_write_at = float("-inf")
        self._settling_until = 0.0
        self._current_exposure = None
        self._last_highlight_detection_at = float("-inf")
        self._set_reported_exposure(None)

        self._custom_metering_region = self._normalize_metering_region(metering_region)
        self._set_visualization_status(self._custom_metering_region, ())
        self._reset_meter(clear_control_state=True)

        if self._exposure_property is None:
            logger.warning("相機 %s 未提供硬體曝光控制，保留原生自動曝光。", self.camera_id)
            return

        initial_exposure = self._read_exposure()
        if initial_exposure is None:
            self._custom_control_available = False
            logger.warning("相機 %s 無法讀取硬體曝光值，保留原生自動曝光。", self.camera_id)
            return

        self._current_exposure = initial_exposure
        self._set_reported_exposure(initial_exposure)

    def set_metering_region(self, metering_region: Any | None) -> None:
        normalized = self._normalize_metering_region(metering_region)
        self._custom_metering_region = normalized
        self._set_visualization_status(normalized, ())
        self._reset_meter(clear_control_state=True)

    def status(self) -> _ExposureControllerStatus:
        with self._status_lock:
            return _ExposureControllerStatus(
                exposure_value=self._reported_exposure,
                metering_region=self._metering_region,
                overexposed_regions=self._overexposed_regions,
            )

    def should_publish(self, image: Any, measured_at: float) -> bool:
        if measured_at < self._settling_until:
            return True

        pending = self._pending_exposure
        if pending is None:
            return True

        metrics = self._measure_frame(image)
        self._pending_exposure = None
        backend = str(self._backend or "").upper()

        if metrics is not None and self._exposure_change_applied(
            pending,
            metrics,
            trust_property=backend != "MSMF",
        ):
            applied = None if backend == "MSMF" else self._read_exposure()
            self._current_exposure = applied if applied is not None else pending.requested
            self._set_reported_exposure(self._current_exposure)
            self._control_verified = True
            self._blocked_direction = 0
            self._blocked_until = 0.0
            self._failed_commands = 0
            self._reset_meter(clear_control_state=pending.severe)
            return True

        if backend == "MSMF":
            self._failed_commands += 1

            if self._failed_commands < self._MAXIMUM_MSMF_UNVERIFIED_COMMANDS:
                self._current_exposure = pending.requested
                self._set_reported_exposure(pending.requested)
                self._reset_meter(clear_control_state=pending.severe)
                return True

            self._current_exposure = pending.requested
            self._set_reported_exposure(pending.requested)
            self._block_direction(
                pending.direction,
                measured_at,
            )
            self._failed_commands = 0
            self._reset_meter(clear_control_state=True)

            logger.warning(
                "相機 %s 的 MSMF 曝光命令連續未產生可觀察影像變化，已暫停同方向調整並持續測光。",
                self.camera_id,
            )
            return True

        if self._control_verified:
            current = self._read_exposure()

            if current is not None:
                self._current_exposure = current
                self._set_reported_exposure(current)

            self._block_direction(
                pending.direction,
                measured_at,
            )
            self._failed_commands = 0
            self._reset_meter(clear_control_state=pending.severe)
            return True

        current = self._read_exposure()
        self._current_exposure = (
            current
            if current is not None
            else pending.requested
        )
        self._set_reported_exposure(self._current_exposure)
        self._block_direction(
            pending.direction,
            measured_at,
        )
        self._failed_commands = 0
        self._reset_meter(clear_control_state=pending.severe)
        logger.warning(
            "相機 %s 無法從目前影像確認曝光變化，已暫停同方向調整並持續測光。",
            self.camera_id,
        )
        return True

    def observe(self, image: Any, measured_at: float) -> None:
        if (
            measured_at - self._last_highlight_detection_at
            >= self._HIGHLIGHT_DETECTION_INTERVAL_SECONDS
        ):
            self._last_highlight_detection_at = measured_at
            self._set_visualization_status(
                self._normalized_metering_region(image),
                self._detect_overexposed_regions(image),
            )

        if not self._custom_control_available:
            return

        metrics = self._measure_frame(image)
        if metrics is None:
            return

        severe_overexposure = self._is_severely_overexposed(metrics)

        if severe_overexposure:
            if (
                self._pending_exposure is None
                and measured_at >= self._settling_until
                and self._can_write(-1, measured_at, severe=True)
            ):
                self._apply_exposure_step(
                    -1,
                    metrics,
                    measured_at,
                    severe=True,
                )
            return

        if self._window_started_at is None:
            self._window_started_at = measured_at

        self._window_metrics.append(metrics)

        if measured_at - self._window_started_at < self._MEASUREMENT_WINDOW_SECONDS:
            return

        window_metrics = self._average_metrics(self._window_metrics)
        self._window_metrics.clear()
        self._window_started_at = measured_at

        self._smoothed_metrics = self._smooth_metrics(
            self._smoothed_metrics,
            window_metrics,
        )

        raw_control = self._fuzzy_control_value(self._smoothed_metrics)
        self._fuzzy_control_state = self._smooth_control_state(
            self._fuzzy_control_state,
            raw_control,
        )

        if self._pending_exposure is not None or measured_at < self._settling_until:
            return

        direction = self._next_direction(self._fuzzy_control_state)

        if direction == 0 or not self._can_write(direction, measured_at, severe=False):
            return

        self._apply_exposure_step(
            direction,
            self._smoothed_metrics,
            measured_at,
            severe=False,
        )

    def _is_severely_overexposed(self, metrics: _ExposureMetrics) -> bool:
        return (
            metrics.highlight_ratio >= self._SEVERE_HIGHLIGHT_RATIO
            or metrics.clipped_ratio >= self._SEVERE_CLIPPED_RATIO
        )

    def _next_direction(self, control: float) -> int:
        if control <= self._FUZZY_DARKEN_THRESHOLD:
            return -1

        if control >= self._FUZZY_BRIGHTEN_THRESHOLD:
            return 1

        return 0

    def _fuzzy_control_value(self, metrics: _ExposureMetrics) -> float:
        dark_membership = self._falling_membership(
            metrics.median,
            self._FUZZY_DARK_MEDIAN_FULL,
            self._FUZZY_DARK_MEDIAN_NONE,
        )

        bright_membership = self._rising_membership(
            metrics.median,
            self._FUZZY_BRIGHT_MEDIAN_NONE,
            self._FUZZY_BRIGHT_MEDIAN_FULL,
        )

        if metrics.highlight_ratio > self._ACCEPTABLE_HIGHLIGHT_RATIO:
            highlight_membership = self._rising_membership(
                metrics.highlight_ratio,
                self._ACCEPTABLE_HIGHLIGHT_RATIO,
                self._HIGHLIGHT_WARNING_FULL_RATIO,
            )

            bright_high = self._rising_membership(
                metrics.high,
                self._FUZZY_BRIGHT_HIGH_NONE,
                self._FUZZY_BRIGHT_HIGH_FULL,
            )

            bright_peak = self._rising_membership(
                metrics.peak,
                self._FUZZY_BRIGHT_PEAK_NONE,
                self._FUZZY_BRIGHT_PEAK_FULL,
            )

            highlight_brightness = bright_high * 0.7 + bright_peak * 0.3

            bright_membership = max(
                bright_membership,
                highlight_membership * highlight_brightness,
            )

        return max(
            -1.0,
            min(1.0, dark_membership - bright_membership),
        )
        
    @staticmethod
    def _rising_membership(
        value: float,
        starts_at: float,
        full_at: float,
    ) -> float:
        if value <= starts_at:
            return 0.0

        if value >= full_at or full_at <= starts_at:
            return 1.0

        return (value - starts_at) / (full_at - starts_at)

    @classmethod
    def _falling_membership(
        cls,
        value: float,
        full_until: float,
        ends_at: float,
    ) -> float:
        return 1.0 - cls._rising_membership(value, full_until, ends_at)

    @classmethod
    def _smooth_control_state(cls, previous: float, current: float) -> float:
        alpha = cls._FUZZY_STATE_ALPHA
        return max(-1.0, min(1.0, previous * (1.0 - alpha) + current * alpha))

    def _can_write(
        self,
        direction: int,
        measured_at: float,
        *,
        severe: bool,
    ) -> bool:
        if direction == self._blocked_direction:
            if measured_at < self._blocked_until:
                return False

            self._blocked_direction = 0
            self._blocked_until = 0.0

        interval = (
            self._SEVERE_WRITE_INTERVAL_SECONDS
            if severe
            else self._MINIMUM_WRITE_INTERVAL_SECONDS
        )

        return measured_at - self._last_write_at >= interval

    def _apply_exposure_step(
        self,
        direction: int,
        metrics: _ExposureMetrics,
        measured_at: float,
        *,
        severe: bool,
    ) -> None:
        current = self._current_exposure

        if current is None:
            current = self._read_exposure()

        if current is None:
            self._register_command_failure(measured_at, direction)
            return

        requested = self._requested_exposure(current, direction, severe=severe)

        if math.isclose(requested, current, abs_tol=self._PROPERTY_TOLERANCE):
            return

        backend = str(self._backend or "").upper()
        manual_enabled = self._enable_manual_exposure()

        if not manual_enabled and backend != "MSMF":
            self._register_command_failure(measured_at, direction)
            return

        if not self._set_property(self._exposure_property, requested):
            self._register_command_failure(measured_at, direction)
            return

        self._manual_exposure = True
        self._current_exposure = requested
        self._set_reported_exposure(requested)
        self._blocked_direction = 0
        self._blocked_until = 0.0

        self._pending_exposure = _PendingExposure(
            previous=current,
            requested=requested,
            direction=direction,
            median_before=metrics.median,
            high_before=metrics.high,
            peak_before=metrics.peak,
            highlight_before=metrics.highlight_ratio,
            clipped_before=metrics.clipped_ratio,
            severe=severe,
        )

        self._last_write_at = measured_at
        self._settling_until = measured_at + (
            self._SEVERE_SETTLING_SECONDS if severe else self._SETTLING_SECONDS
        )

    def _requested_exposure(
        self,
        current: float,
        direction: int,
        *,
        severe: bool,
    ) -> float:
        if current > self._ADAPTIVE_EXPOSURE_THRESHOLD:
            if direction < 0:
                if severe:
                    step = max(
                        self._MINIMUM_SEVERE_DARKEN_STEP,
                        current * self._SEVERE_DARKEN_RATIO,
                    )
                else:
                    step = max(
                        self._MINIMUM_DARKEN_STEP,
                        current * self._DARKEN_RATIO,
                    )

                requested = max(1.0, current - step)
            else:
                step = max(
                    self._MINIMUM_BRIGHTEN_STEP,
                    current * self._BRIGHTEN_RATIO,
                )
                requested = current + step

            return float(round(requested))

        return current + direction * self._EXPOSURE_STEP

    def _exposure_change_applied(
        self,
        pending: _PendingExposure,
        metrics: _ExposureMetrics,
        *,
        trust_property: bool,
    ) -> bool:
        property_changed = False

        if trust_property:
            applied = self._read_exposure()
            property_changed = (
                applied is not None
                and not math.isclose(
                    applied,
                    pending.previous,
                    abs_tol=self._PROPERTY_TOLERANCE,
                )
            )

        if pending.direction < 0:
            median_change = pending.median_before - metrics.median
            high_change = pending.high_before - metrics.high
            peak_change = pending.peak_before - metrics.peak
            highlight_change = pending.highlight_before - metrics.highlight_ratio
            clipped_change = pending.clipped_before - metrics.clipped_ratio
        else:
            median_change = metrics.median - pending.median_before
            high_change = metrics.high - pending.high_before
            peak_change = metrics.peak - pending.peak_before
            highlight_change = metrics.highlight_ratio - pending.highlight_before
            clipped_change = metrics.clipped_ratio - pending.clipped_before

        visible_change = (
            median_change >= self._MINIMUM_VISIBLE_RESPONSE
            or high_change >= self._MINIMUM_VISIBLE_RESPONSE
            or peak_change >= self._MINIMUM_VISIBLE_RESPONSE
            or highlight_change >= self._MINIMUM_RATIO_RESPONSE
            or clipped_change >= self._MINIMUM_RATIO_RESPONSE
        )

        return property_changed or visible_change

    def _register_command_failure(
        self,
        measured_at: float,
        direction: int,
    ) -> None:
        self._failed_commands += 1
        self._last_write_at = measured_at
        self._reset_meter()

        if self._control_verified:
            self._block_direction(
                direction,
                measured_at,
            )
            return

        self._restore_native_auto_exposure()
        self._settling_until = measured_at + self._NATIVE_AUTO_SETTLING_SECONDS

        if self._failed_commands >= self._MAXIMUM_FAILED_COMMANDS:
            self._custom_control_available = False
            logger.warning(
                "相機 %s 無法安全控制硬體曝光，已改用原生自動曝光。",
                self.camera_id,
            )

    def _block_direction(
        self,
        direction: int,
        measured_at: float,
    ) -> None:
        self._blocked_direction = direction
        self._blocked_until = (
            measured_at
            + self._BLOCKED_DIRECTION_RETRY_SECONDS
        )

    def _enable_manual_exposure(self) -> bool:
        if self._manual_exposure:
            return True

        if self._capture is None:
            return False

        auto_property = getattr(self.cv2, "CAP_PROP_AUTO_EXPOSURE", None)
        if auto_property is None:
            return False

        backend = str(self._backend or "").upper()
        values = (0.0, 0.25) if backend == "MSMF" else (0.25, 0.0)

        for value in values:
            if self._set_property(auto_property, value):
                self._manual_exposure = True
                return True

        return False

    def _restore_native_auto_exposure(self) -> None:
        if self._capture is None:
            return

        auto_property = getattr(self.cv2, "CAP_PROP_AUTO_EXPOSURE", None)
        if auto_property is None:
            return

        backend = str(self._backend or "").upper()
        values = (1.0, 0.75) if backend == "MSMF" else (0.75, 1.0)

        for value in values:
            if self._set_property(auto_property, value):
                self._manual_exposure = False
                self._current_exposure = None
                self._set_reported_exposure(None)
                return

    def _set_property(self, property_id: Any, value: float) -> bool:
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

    def _measure_frame(self, image: Any) -> _ExposureMetrics | None:
        metering_image = self._metering_image(image)

        if metering_image is None:
            return None

        try:
            sampled = np.asarray(
                metering_image[::self._SAMPLE_STRIDE, ::self._SAMPLE_STRIDE],
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
            highlight_ratio=float(np.mean(luminance >= self._HIGHLIGHT_LEVEL)),
            clipped_ratio=float(np.mean(luminance >= self._CLIPPED_LEVEL)),
        )

    def _metering_image(self, image: Any) -> Any | None:
        bounds = self._metering_bounds(image)

        if bounds is None:
            return None

        left, top, right, bottom = bounds
        return image[top:bottom, left:right]

    def _metering_bounds(
        self,
        image: Any,
    ) -> tuple[int, int, int, int] | None:
        shape = getattr(image, "shape", None)

        if shape is None or len(shape) < 2:
            return None

        image_height = int(shape[0])
        image_width = int(shape[1])

        if image_height <= 0 or image_width <= 0:
            return None

        custom = self._custom_metering_region

        if custom is not None:
            x, y, width, height = custom

            left = min(image_width - 1, max(0, int(round(x * image_width))))
            top = min(image_height - 1, max(0, int(round(y * image_height))))
            right = min(
                image_width,
                max(left + 1, int(round((x + width) * image_width))),
            )
            bottom = min(
                image_height,
                max(top + 1, int(round((y + height) * image_height))),
            )

            return left, top, right, bottom

        horizontal_inset = int(
            round(image_width * self._METERING_HORIZONTAL_INSET_RATIO)
        )
        horizontal_inset = min(
            max(0, horizontal_inset),
            max(0, image_width // 2 - 1),
        )

        top = (
            image_height // 2
            if self.camera_id in self._LOWER_HALF_METERING_CAMERAS
            else 0
        )

        return horizontal_inset, top, image_width - horizontal_inset, image_height

    @staticmethod
    def _normalize_metering_region(
        region: Any | None,
    ) -> tuple[float, float, float, float] | None:
        if region is None:
            return None

        if hasattr(region, "model_dump"):
            region = region.model_dump(mode="python")

        if isinstance(region, dict):
            values = (
                region.get("x"),
                region.get("y"),
                region.get("width"),
                region.get("height"),
            )
        else:
            try:
                values = tuple(region)
            except TypeError:
                return None

        if len(values) != 4:
            return None

        try:
            x, y, width, height = (float(value) for value in values)
        except (TypeError, ValueError):
            return None

        if not all(math.isfinite(value) for value in (x, y, width, height)):
            return None

        if (
            x < 0.0
            or y < 0.0
            or width < 0.05
            or height < 0.05
            or x + width > 1.0 + 1e-6
            or y + height > 1.0 + 1e-6
        ):
            return None

        return x, y, width, height

    def _detect_overexposed_regions(
        self,
        image: Any,
    ) -> tuple[tuple[float, float, float, float], ...]:
        bounds = self._metering_bounds(image)
        shape = getattr(image, "shape", None)

        if bounds is None or shape is None:
            return ()

        left, top, right, bottom = bounds
        image_height = int(shape[0])
        image_width = int(shape[1])
        metering_image = image[top:bottom, left:right]
        stride = self._HIGHLIGHT_SAMPLE_STRIDE

        try:
            sampled = np.asarray(
                metering_image[::stride, ::stride],
                dtype=np.float32,
            )
        except Exception:
            return ()

        if sampled.size == 0:
            return ()

        if sampled.ndim >= 3 and sampled.shape[2] >= 3:
            luminance = (
                sampled[..., 0] * 0.114
                + sampled[..., 1] * 0.587
                + sampled[..., 2] * 0.299
            )
        else:
            luminance = sampled

        mask = np.asarray(
            luminance >= self._HIGHLIGHT_LEVEL,
            dtype=np.uint8,
        )

        if not np.any(mask):
            return ()

        try:
            kernel = np.ones((3, 3), dtype=np.uint8)
            mask = self.cv2.morphologyEx(
                mask,
                self.cv2.MORPH_CLOSE,
                kernel,
                iterations=2,
            )
            component_count, _labels, stats, _centroids = (
                self.cv2.connectedComponentsWithStats(mask, connectivity=8)
            )
        except Exception:
            return ()

        minimum_area = max(
            4,
            int(round(mask.size * self._MINIMUM_HIGHLIGHT_AREA_RATIO)),
        )

        components: list[tuple[int, int, int, int, int]] = []

        for component_index in range(1, int(component_count)):
            component_left = int(stats[component_index, 0])
            component_top = int(stats[component_index, 1])
            component_width = int(stats[component_index, 2])
            component_height = int(stats[component_index, 3])
            component_area = int(stats[component_index, 4])

            if component_area < minimum_area:
                continue

            components.append(
                (
                    component_area,
                    component_left,
                    component_top,
                    component_width,
                    component_height,
                )
            )

        components.sort(reverse=True)
        regions: list[tuple[float, float, float, float]] = []

        for (
            _area,
            component_left,
            component_top,
            component_width,
            component_height,
        ) in components[:self._MAXIMUM_HIGHLIGHT_REGIONS]:
            region_left = max(left, left + (component_left - 1) * stride)
            region_top = max(top, top + (component_top - 1) * stride)
            region_right = min(
                right,
                left + (component_left + component_width + 1) * stride,
            )
            region_bottom = min(
                bottom,
                top + (component_top + component_height + 1) * stride,
            )

            regions.append(
                (
                    round(region_left / image_width, 6),
                    round(region_top / image_height, 6),
                    round((region_right - region_left) / image_width, 6),
                    round((region_bottom - region_top) / image_height, 6),
                )
            )

        return tuple(regions)

    def _normalized_metering_region(
        self,
        image: Any,
    ) -> tuple[float, float, float, float] | None:
        bounds = self._metering_bounds(image)
        shape = getattr(image, "shape", None)

        if bounds is None or shape is None:
            return None

        left, top, right, bottom = bounds
        image_height = int(shape[0])
        image_width = int(shape[1])

        return (
            round(left / image_width, 6),
            round(top / image_height, 6),
            round((right - left) / image_width, 6),
            round((bottom - top) / image_height, 6),
        )

    def _set_reported_exposure(self, value: float | None) -> None:
        with self._status_lock:
            self._reported_exposure = value

    def _set_visualization_status(
        self,
        metering_region: tuple[float, float, float, float] | None,
        regions: tuple[tuple[float, float, float, float], ...],
    ) -> None:
        with self._status_lock:
            self._metering_region = metering_region
            self._overexposed_regions = regions

    @staticmethod
    def _average_metrics(metrics: list[_ExposureMetrics]) -> _ExposureMetrics:
        count = max(1, len(metrics))

        return _ExposureMetrics(
            median=sum(item.median for item in metrics) / count,
            high=sum(item.high for item in metrics) / count,
            peak=sum(item.peak for item in metrics) / count,
            highlight_ratio=sum(item.highlight_ratio for item in metrics) / count,
            clipped_ratio=sum(item.clipped_ratio for item in metrics) / count,
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
            highlight_ratio=(
                previous.highlight_ratio * retained
                + current.highlight_ratio * alpha
            ),
            clipped_ratio=(
                previous.clipped_ratio * retained
                + current.clipped_ratio * alpha
            ),
        )

    def _reset_meter(self, *, clear_control_state: bool = False) -> None:
        self._window_started_at = None
        self._window_metrics.clear()
        self._smoothed_metrics = None

        if clear_control_state:
            self._fuzzy_control_state = 0.0
