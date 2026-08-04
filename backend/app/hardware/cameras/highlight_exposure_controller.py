from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class CameraHighlightExposureController:
    """Protect full-frame highlights with automatic hardware exposure updates."""

    _ADJUSTMENT_INTERVAL_SECONDS = 0.75
    _TARGET_HIGHLIGHT_LEVEL = 225.0
    _HIGHLIGHT_HYSTERESIS = 12.0
    _CLIPPED_LEVEL = 250.0
    _CLIPPED_PIXEL_LIMIT = 0.003
    _SEVERE_CLIPPED_PIXEL_LIMIT = 0.05
    _EXPOSURE_STEP = 1.0
    _FAST_EXPOSURE_STEP = 2.0
    _FALLBACK_EXPOSURE = -6.0
    _SAMPLE_STRIDE = 4
    _PROPERTY_TOLERANCE = 0.25

    def __init__(
        self,
        camera_id: str,
        cv2_module: Any,
    ) -> None:
        self.camera_id = camera_id
        self.cv2 = cv2_module
        self._backend: str | None = None
        self._capture: Any | None = None
        self._exposure_property: Any | None = None
        self._current_exposure = self._FALLBACK_EXPOSURE
        self._next_adjustment_at = 0.0
        self._supported = False

    def configure(
        self,
        capture: Any,
        backend: str | None,
    ) -> None:
        self._backend = backend
        self._capture = capture
        self._exposure_property = getattr(
            self.cv2,
            "CAP_PROP_EXPOSURE",
            None,
        )
        self._next_adjustment_at = 0.0
        self._supported = False

        if self._exposure_property is None:
            logger.warning(
                "Camera %s does not expose hardware exposure control.",
                self.camera_id,
            )
            return

        current_exposure = self._read_exposure(
            capture,
            self._exposure_property,
        )
        initial_exposure = (
            current_exposure
            if current_exposure is not None
            else self._FALLBACK_EXPOSURE
        )
        for manual_value in self._manual_auto_exposure_values(backend):
            if manual_value is not None:
                auto_property = getattr(
                    self.cv2,
                    "CAP_PROP_AUTO_EXPOSURE",
                    None,
                )
                if auto_property is not None:
                    self._set_property(
                        capture,
                        auto_property,
                        manual_value,
                    )

            self._current_exposure = initial_exposure
            if self._apply_and_verify_exposure(
                initial_exposure - self._EXPOSURE_STEP,
            ):
                self._supported = True
                logger.info(
                    "Camera %s enabled full-frame highlight exposure via %s at %s.",
                    self.camera_id,
                    backend or "AUTO",
                    self._current_exposure,
                )
                return

        self._restore_native_auto_exposure(capture, backend)
        logger.warning(
            "Camera %s backend %s did not apply hardware exposure changes.",
            self.camera_id,
            backend or "AUTO",
        )

    def adjust(
        self,
        image: Any,
        measured_at: float,
    ) -> None:
        if not self._supported or self._capture is None:
            return
        if measured_at < self._next_adjustment_at:
            return

        self._next_adjustment_at = (
            measured_at
            + self._ADJUSTMENT_INTERVAL_SECONDS
        )
        measurement = self._measure_full_frame_highlights(image)
        if measurement is None:
            return

        highlight_level, clipped_ratio = measurement
        exposure_delta = self._exposure_delta(
            highlight_level,
            clipped_ratio,
        )
        if exposure_delta == 0.0:
            return

        requested_exposure = self._current_exposure + exposure_delta
        if not self._apply_and_verify_exposure(requested_exposure):
            logger.warning(
                "Camera %s backend %s stopped applying exposure changes.",
                self.camera_id,
                self._backend or "AUTO",
            )
            self._supported = False

    def _exposure_delta(
        self,
        highlight_level: float,
        clipped_ratio: float,
    ) -> float:
        upper_limit = (
            self._TARGET_HIGHLIGHT_LEVEL
            + self._HIGHLIGHT_HYSTERESIS
        )
        lower_limit = (
            self._TARGET_HIGHLIGHT_LEVEL
            - self._HIGHLIGHT_HYSTERESIS
        )

        if (
            clipped_ratio >= self._SEVERE_CLIPPED_PIXEL_LIMIT
            or highlight_level >= 252.0
        ):
            return -self._FAST_EXPOSURE_STEP
        if (
            clipped_ratio >= self._CLIPPED_PIXEL_LIMIT
            or highlight_level > upper_limit
        ):
            return -self._EXPOSURE_STEP
        if (
            clipped_ratio < self._CLIPPED_PIXEL_LIMIT / 4
            and highlight_level < lower_limit
        ):
            return self._EXPOSURE_STEP
        return 0.0

    def _measure_full_frame_highlights(
        self,
        image: Any,
    ) -> tuple[float, float] | None:
        shape = getattr(image, "shape", None)
        if shape is None or len(shape) < 2:
            return None

        sampled = np.asarray(
            image[
                ::self._SAMPLE_STRIDE,
                ::self._SAMPLE_STRIDE,
            ],
            dtype=np.float32,
        )
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

        return (
            float(np.percentile(luminance, 99.0)),
            float(np.mean(luminance >= self._CLIPPED_LEVEL)),
        )

    @staticmethod
    def _manual_auto_exposure_values(
        backend: str | None,
    ) -> tuple[float | None, ...]:
        backend_name = str(backend or "").upper()
        return (
            (0.25, 0.0, None)
            if backend_name in {"DSHOW", "MSMF"}
            else (0.0, 0.25, None)
        )

    def _apply_and_verify_exposure(
        self,
        requested_exposure: float,
    ) -> bool:
        if self._capture is None or self._exposure_property is None:
            return False

        previous_exposure = self._read_exposure(
            self._capture,
            self._exposure_property,
        )
        self._set_property(
            self._capture,
            self._exposure_property,
            requested_exposure,
        )
        applied_exposure = self._read_exposure(
            self._capture,
            self._exposure_property,
        )
        if applied_exposure is None:
            return False
        if (
            previous_exposure is not None
            and not math.isclose(
                requested_exposure,
                previous_exposure,
                abs_tol=self._PROPERTY_TOLERANCE,
            )
            and math.isclose(
                applied_exposure,
                previous_exposure,
                abs_tol=self._PROPERTY_TOLERANCE,
            )
        ):
            return False

        self._current_exposure = applied_exposure
        return True

    def _restore_native_auto_exposure(
        self,
        capture: Any,
        backend: str | None,
    ) -> None:
        auto_property = getattr(
            self.cv2,
            "CAP_PROP_AUTO_EXPOSURE",
            None,
        )
        if auto_property is None:
            return

        backend_name = str(backend or "").upper()
        values = (
            (0.75, 1.0)
            if backend_name in {"DSHOW", "MSMF"}
            else (1.0, 0.75, 3.0)
        )
        for value in values:
            if self._set_property(capture, auto_property, value):
                return

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

    @staticmethod
    def _read_exposure(
        capture: Any,
        property_id: Any,
    ) -> float | None:
        try:
            value = float(capture.get(property_id))
        except Exception:
            return None
        return value if math.isfinite(value) else None
