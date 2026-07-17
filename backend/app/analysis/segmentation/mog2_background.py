from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from app.analysis.segmentation.contour_processing import (
    clean_foreground_mask,
    significant_contours,
    total_contour_area,
)
from app.analysis.segmentation.lighting_change import LightingChangeDetector


@dataclass(frozen=True)
class SegmentationFrame:
    status: str
    mask: np.ndarray
    contours: list[np.ndarray]
    contour_area_px: float
    roi_origin: tuple[int, int]


class Mog2BackgroundSegmenter:
    def __init__(
        self,
        *,
        history: int,
        variance_threshold: float,
        detect_shadows: bool,
        initialization_frames: int,
        opening_kernel_size: int | None,
        closing_kernel_size: int | None,
        erosion_kernel_size: int | None,
        minimum_contour_area_px: float,
        lighting_change_area_px: float,
        lighting_change_est_time_frames: int,
    ) -> None:
        if history < 1 or initialization_frames < 1:
            raise ValueError("MOG2 歷史與初始化影格數至少為 1。")
        if variance_threshold <= 0:
            raise ValueError("MOG2 變異門檻必須大於零。")
        self.history = history
        self.variance_threshold = variance_threshold
        self.detect_shadows = detect_shadows
        self.initialization_frames = initialization_frames
        self.opening_kernel_size = opening_kernel_size
        self.closing_kernel_size = closing_kernel_size
        self.erosion_kernel_size = erosion_kernel_size
        self.minimum_contour_area_px = minimum_contour_area_px
        self.lighting = LightingChangeDetector(
            area_threshold_px=lighting_change_area_px,
            stabilization_frames=lighting_change_est_time_frames,
        )
        self._processed_since_reset = 0
        self._initialization_completed = False
        self._subtractor = self._create_subtractor()

    def _create_subtractor(self):
        return cv2.createBackgroundSubtractorMOG2(
            history=self.history,
            varThreshold=self.variance_threshold,
            detectShadows=self.detect_shadows,
        )

    def reset(self) -> None:
        self._subtractor = self._create_subtractor()
        self._processed_since_reset = 0

    @staticmethod
    def _crop(
        image: np.ndarray,
        roi: tuple[int, int, int, int] | None,
    ) -> tuple[np.ndarray, tuple[int, int]]:
        if image.ndim not in {2, 3} or image.size == 0:
            raise ValueError("分析影像格式無效。")
        if roi is None:
            return image, (0, 0)
        x, y, width, height = roi
        image_height, image_width = image.shape[:2]
        if (
            x < 0
            or y < 0
            or width <= 0
            or height <= 0
            or x + width > image_width
            or y + height > image_height
        ):
            raise ValueError("ROI 超出影像範圍。")
        return image[y:y + height, x:x + width], (x, y)

    def process(
        self,
        image: np.ndarray,
        *,
        roi: tuple[int, int, int, int] | None = None,
        learning_rate: float = -1,
    ) -> SegmentationFrame:
        # MOG2 is a per-pixel temporal model, so its coordinate system must stay
        # fixed even when the detection ROI follows the selected contour. Apply
        # it to the full frame first, then crop only the foreground mask.
        self._crop(image, roi)
        raw_full_mask = self._subtractor.apply(image, learningRate=learning_rate)
        if roi is None:
            raw_mask = raw_full_mask
            origin = (0, 0)
        else:
            x, y, width, height = roi
            raw_mask = raw_full_mask[y:y + height, x:x + width]
            origin = (x, y)
        self._processed_since_reset += 1
        cleaned = clean_foreground_mask(
            raw_mask,
            opening_kernel_size=self.opening_kernel_size,
            closing_kernel_size=self.closing_kernel_size,
            erosion_kernel_size=self.erosion_kernel_size,
        )
        contours = significant_contours(
            cleaned,
            minimum_area_px=self.minimum_contour_area_px,
        )
        area = total_contour_area(contours)

        if (
            not self._initialization_completed
            and self._processed_since_reset <= self.initialization_frames
        ):
            return SegmentationFrame(
                status="background_initialization",
                mask=cleaned,
                contours=[],
                contour_area_px=area,
                roi_origin=origin,
            )
        self._initialization_completed = True

        lighting_state = self.lighting.observe(area)
        if lighting_state.changed:
            self.reset()
        if lighting_state.transitioning:
            return SegmentationFrame(
                status="lighting_transition",
                mask=cleaned,
                contours=[],
                contour_area_px=area,
                roi_origin=origin,
            )

        if self._processed_since_reset <= self.initialization_frames:
            return SegmentationFrame(
                status="background_initialization",
                mask=cleaned,
                contours=[],
                contour_area_px=area,
                roi_origin=origin,
            )

        return SegmentationFrame(
            status="ready",
            mask=cleaned,
            contours=contours,
            contour_area_px=area,
            roi_origin=origin,
        )
