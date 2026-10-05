from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from app.analysis.gpu_operations import binary_morphology, convert_color


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
    hsv = convert_color(bgr, cv2.COLOR_BGR2HSV)
    hue, saturation, value = cv2.split(hsv)
    # Relative Lab/Otsu votes classify the dark green cast of the enclosure as
    # foliage. Require actual illuminated green tissue before growing a region.
    brightness = max(30.0, min(60.0, float(np.percentile(value[valid > 0], 75)) + 10))
    green_pixels = (
        (hue >= 20) & (hue <= 105) & (saturation >= 24)
        & (excess_green > 4) & (green > red) & (value >= brightness)
    )
    seeds = green_pixels & (excess_green >= 8) & (value >= max(40, brightness)) & (valid > 0)
    # Keep white leaf highlights and pale/yellow stems connected to foliage.
    # Detached lamps and the red/brown pot cannot seed a plant component.
    highlights = (saturation < 48) & (value >= max(80, brightness + 20))
    stems = (hue >= 15) & (hue <= 40) & (excess_green > 3) & (value >= brightness)
    candidate = np.where((green_pixels | highlights | stems) & (valid > 0), 255, 0).astype(np.uint8)
    combined = binary_morphology(
        candidate,
        np.ones((1, 1), dtype=np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
    )
    combined[valid == 0] = 0
    count, labels, statistics, _ = cv2.connectedComponentsWithStats(combined, connectivity=8)
    seed_counts = np.bincount(labels[seeds], minlength=count)
    minimum_area = max(12, round(width * height * 0.00001))
    retained = (statistics[:, cv2.CC_STAT_AREA] >= minimum_area) & (seed_counts >= 3)
    retained[0] = False
    if retained.any():
        main = int(np.argmax(np.where(retained, seed_counts, 0)))
        distance = cv2.distanceTransform((labels != main).astype(np.uint8), cv2.DIST_L2, 3)
        nearest = np.full(count, np.inf)
        np.minimum.at(nearest, labels.ravel(), distance.ravel())
        green_fraction = seed_counts / np.maximum(statistics[:, cv2.CC_STAT_AREA], 1)
        retained &= (nearest <= max(16, min(width, height) * .04)) & (green_fraction >= .2)
        retained[main] = True
    combined = (retained[labels] * 255).astype(np.uint8)
    component_count = int(retained.sum())

    foreground = int(np.count_nonzero(combined))
    valid_count = max(int(np.count_nonzero(valid)), 1)
    ratio = foreground / valid_count
    # A small plant can legitimately occupy less than one percent of a full
    # enclosure frame; clean seed agreement matters more than scene coverage.
    coverage_score = min(ratio / 0.003, 1.0) * min(0.55 / max(ratio, 1e-6), 1.0)
    agreement = float(np.mean(green_pixels[combined > 0])) if foreground else 0.0
    confidence = float(np.clip(0.55 * agreement + 0.45 * coverage_score, 0.0, 1.0))
    return PlantMaskResult(
        mask=combined,
        foreground_ratio=float(ratio),
        component_count=component_count,
        confidence=confidence,
    )


__all__ = ["PlantMaskResult", "create_plant_mask"]
