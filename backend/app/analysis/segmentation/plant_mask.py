from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class PlantMaskResult:
    mask: np.ndarray
    foreground_ratio: float
    component_count: int
    confidence: float


def _valid_mask(value: np.ndarray | None, shape: tuple[int, int]) -> np.ndarray:
    if value is None:
        return np.full(shape, 255, dtype=np.uint8)
    mask = np.asarray(value, dtype=np.uint8)
    if mask.shape != shape:
        raise ValueError("有效像素遮罩尺寸與影像不一致。")
    return np.where(mask > 0, 255, 0).astype(np.uint8)


def _remove_small_components(
    mask: np.ndarray,
    minimum_area: int,
) -> tuple[np.ndarray, int]:
    count, labels, statistics, _ = cv2.connectedComponentsWithStats(
        mask,
        connectivity=8,
    )
    output = np.zeros_like(mask)
    retained = 0
    for label in range(1, count):
        area = int(statistics[label, cv2.CC_STAT_AREA])
        if area < minimum_area:
            continue
        output[labels == label] = 255
        retained += 1
    return output, retained


def create_plant_mask(
    image: np.ndarray,
    *,
    valid_pixel_mask: np.ndarray | None = None,
) -> PlantMaskResult:
    """Build a single-image plant mask without ROI or inter-Round differencing."""

    bgr = np.asarray(image, dtype=np.uint8)
    if bgr.ndim != 3 or bgr.shape[2] != 3:
        raise ValueError("植物分割影像必須是三通道彩色影像。")
    height, width = bgr.shape[:2]
    valid = _valid_mask(valid_pixel_mask, (height, width))

    blue, green, red = cv2.split(bgr.astype(np.float32))
    excess_green = 2.0 * green - red - blue
    valid_values = excess_green[valid > 0]
    if valid_values.size == 0:
        raise ValueError("影像沒有有效像素可建立植物遮罩。")
    normalized_excess = cv2.normalize(
        excess_green,
        None,
        0,
        255,
        cv2.NORM_MINMAX,
    ).astype(np.uint8)
    _, excess_mask = cv2.threshold(
        normalized_excess,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )

    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    hsv_mask = cv2.inRange(
        hsv,
        np.asarray((20, 24, 18), dtype=np.uint8),
        np.asarray((105, 255, 255), dtype=np.uint8),
    )

    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    a_channel = lab[..., 1]
    a_threshold = float(np.percentile(a_channel[valid > 0], 48))
    lab_mask = np.where(a_channel <= a_threshold, 255, 0).astype(np.uint8)

    votes = (
        (excess_mask > 0).astype(np.uint8)
        + (hsv_mask > 0).astype(np.uint8)
        + (lab_mask > 0).astype(np.uint8)
    )
    combined = np.where(votes >= 2, 255, 0).astype(np.uint8)
    combined = cv2.bitwise_and(combined, valid)
    scale = max(1, round(min(width, height) / 480))
    opening = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (2 * scale + 1, 2 * scale + 1),
    )
    closing = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (4 * scale + 1, 4 * scale + 1),
    )
    combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, opening)
    combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, closing)
    minimum_area = max(32, round(width * height * 0.00015))
    combined, component_count = _remove_small_components(
        combined,
        minimum_area,
    )

    foreground = int(np.count_nonzero(combined))
    valid_count = max(int(np.count_nonzero(valid)), 1)
    ratio = foreground / valid_count
    coverage_score = min(ratio / 0.03, 1.0) * min(0.55 / max(ratio, 1e-6), 1.0)
    agreement = float(np.mean(votes[combined > 0]) / 3.0) if foreground else 0.0
    confidence = float(np.clip(0.55 * agreement + 0.45 * coverage_score, 0.0, 1.0))
    return PlantMaskResult(
        mask=combined,
        foreground_ratio=float(ratio),
        component_count=component_count,
        confidence=confidence,
    )


__all__ = ["PlantMaskResult", "create_plant_mask"]
