from __future__ import annotations

import cv2
import numpy as np


def _kernel(size: int | None) -> np.ndarray | None:
    if size is None:
        return None
    if size <= 0 or size % 2 == 0:
        raise ValueError("Morphology kernel 大小必須是正奇數。")
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))


def clean_foreground_mask(
    mask: np.ndarray,
    *,
    opening_kernel_size: int | None = None,
    closing_kernel_size: int | None = None,
    erosion_kernel_size: int | None = None,
) -> np.ndarray:
    if mask.ndim != 2:
        raise ValueError("前景遮罩必須是單通道影像。")
    cleaned = np.where(mask > 0, 255, 0).astype(np.uint8)
    opening = _kernel(opening_kernel_size)
    closing = _kernel(closing_kernel_size)
    erosion = _kernel(erosion_kernel_size)
    if opening is not None:
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, opening)
    if closing is not None:
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, closing)
    if erosion is not None:
        cleaned = cv2.erode(cleaned, erosion)
    return cleaned


def significant_contours(
    mask: np.ndarray,
    *,
    minimum_area_px: float,
) -> list[np.ndarray]:
    if minimum_area_px < 0:
        raise ValueError("最小輪廓面積不可為負值。")
    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_NONE,
    )
    return sorted(
        (
            contour
            for contour in contours
            if cv2.contourArea(contour) >= minimum_area_px
        ),
        key=cv2.contourArea,
        reverse=True,
    )


def total_contour_area(contours: list[np.ndarray]) -> float:
    return float(sum(cv2.contourArea(contour) for contour in contours))
