from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np

from app.core.config import CameraConfig

logger = logging.getLogger(__name__)


class CameraExposureController:
    """Control hardware exposure from a center-region luminance sample."""

    _BRIGHTNESS_HYSTERESIS = 8.0
    _HIGHLIGHT_LEVEL = 245.0
    _HIGHLIGHT_LIMIT = 0.005
    _PERCENTILE_LIMIT = 235.0
    _EXPOSURE_STEP = 1.0

    def __init__(
        self,
        camera_id: str,
        config: CameraConfig,
        cv2_module: Any,
    ) -> None:
        self.camera_id = camera_id
        self.config = config
        self.cv2 = cv2_module
        self._supported = False
        self._current_exposure = config.exposure_value
        self._next_adjustment_at = 0.0

    def configure(
        self,
        capture: Any,
        backend: str | None,
    ) -> None:
        self._supported = False
        self._current_exposure = self.config.exposure_value
        self._next_adjustment_at = 0.0

        exposure_property = getattr(self.cv2, "CAP_PROP_EXPOSURE", None)
        if exposure_property is None:
            logger.warning(
                "Camera %s does not expose CAP_PROP_EXPOSURE.",
                self.camera_id,
            )
            return

        self._disable_camera_auto_exposure(capture, backend)

        if not self._set_property(
            capture,
            exposure_property,
            self.config.exposure_value,
        ):
            logger.warning(
                "Camera %s driver rejected hardware exposure control.",
                self.camera_id,
            )
            return

        self._current_exposure = self._read_exposure(
            capture,
            exposure_property,
            fallback=self.config.exposure_value,
        )
        self._supported = True

    def adjust(
        self,
        capture: Any,
        image: Any,
        measured_at: float,
    ) -> None:
        if (
            not self._supported
            or not self.config.center_weighted_exposure
        ):
            return

        if self._next_adjustment_at == 0.0:
            self._next_adjustment_at = (
                measured_at
                + self.config.exposure_adjustment_interval_seconds
            )
            return
        if measured_at < self._next_adjustment_at:
            return

        self._next_adjustment_at = (
            measured_at
            + self.config.exposure_adjustment_interval_seconds
        )
        measurement = self._measure_center(image)
        if measurement is None:
            return

        mean_brightness, highlight_ratio, percentile_95 = measurement
        target = float(self.config.exposure_target)
        direction = 0.0

        if (
            highlight_ratio > self._HIGHLIGHT_LIMIT
            or percentile_95 > self._PERCENTILE_LIMIT
            or mean_brightness > target + self._BRIGHTNESS_HYSTERESIS
        ):
            direction = -1.0
        elif (
            mean_brightness < target - self._BRIGHTNESS_HYSTERESIS
            and percentile_95 < self._PERCENTILE_LIMIT
        ):
            direction = 1.0

        if direction == 0.0:
            return

        requested_exposure = min(
            self.config.exposure_max,
            max(
                self.config.exposure_min,
                self._current_exposure + direction * self._EXPOSURE_STEP,
            ),
        )
        if math.isclose(requested_exposure, self._current_exposure):
            return

        exposure_property = getattr(self.cv2, "CAP_PROP_EXPOSURE", None)
        if exposure_property is None:
            self._supported = False
            return

        if not self._set_property(
            capture,
            exposure_property,
            requested_exposure,
        ):
            logger.warning(
                "Camera %s stopped accepting exposure updates.",
                self.camera_id,
            )
            self._supported = False
            return

        self._current_exposure = self._read_exposure(
            capture,
            exposure_property,
            fallback=requested_exposure,
        )

    def _disable_camera_auto_exposure(
        self,
        capture: Any,
        backend: str | None,
    ) -> None:
        auto_property = getattr(self.cv2, "CAP_PROP_AUTO_EXPOSURE", None)
        if auto_property is None:
            return

        backend_name = str(backend or "").upper()
        manual_values = (
            (0.25, 0.0)
            if backend_name in {"DSHOW", "MSMF"}
            else (0.0, 0.25)
        )
        for value in manual_values:
            if self._set_property(capture, auto_property, value):
                return

        logger.warning(
            "Camera %s driver did not confirm disabling auto exposure.",
            self.camera_id,
        )

    def _measure_center(
        self,
        image: Any,
    ) -> tuple[float, float, float] | None:
        shape = getattr(image, "shape", None)
        if shape is None or len(shape) < 2:
            return None

        height, width = int(shape[0]), int(shape[1])
        if height <= 0 or width <= 0:
            return None

        ratio = self.config.metering_region_percent / 100.0
        region_height = max(1, round(height * ratio))
        region_width = max(1, round(width * ratio))
        top = max(0, (height - region_height) // 2)
        left = max(0, (width - region_width) // 2)
        region = np.asarray(
            image[
                top:top + region_height,
                left:left + region_width,
            ],
            dtype=np.float32,
        )
        if region.size == 0:
            return None

        if region.ndim >= 3 and region.shape[2] >= 3:
            luminance = (
                region[..., 0] * 0.114
                + region[..., 1] * 0.587
                + region[..., 2] * 0.299
            )
        else:
            luminance = region

        return (
            float(np.mean(luminance)),
            float(np.mean(luminance >= self._HIGHLIGHT_LEVEL)),
            float(np.percentile(luminance, 95)),
        )

    @staticmethod
    def _set_property(
        capture: Any,
        property_id: Any,
        value: float,
    ) -> bool:
        try:
            return bool(capture.set(property_id, value))
        except Exception:
            return False

    def _read_exposure(
        self,
        capture: Any,
        property_id: Any,
        *,
        fallback: float,
    ) -> float:
        try:
            value = float(capture.get(property_id))
        except Exception:
            return fallback
        if (
            not math.isfinite(value)
            or value < self.config.exposure_min
            or value > self.config.exposure_max
        ):
            return fallback
        return value
