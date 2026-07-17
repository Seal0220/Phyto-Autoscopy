from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class RotatingTipObservation:
    point: tuple[float, float] | None
    confidence: float
    search_bounds: tuple[int, int, int, int]


def detect_rotating_tip_near_projection(
    image: np.ndarray,
    projected_point: Sequence[float],
    *,
    radius_px: int = 80,
) -> RotatingTipObservation:
    """Find a plant-like edge close to the baseline 3D reprojection.

    The rotating view is an optional refinement. Returning no observation is
    intentional when the local evidence is weak, so a bad rotating frame never
    invalidates the top + side result.
    """

    if image.ndim != 3 or image.shape[2] < 3:
        return RotatingTipObservation(None, 0.0, (0, 0, 0, 0))
    height, width = image.shape[:2]
    center_x, center_y = (float(value) for value in projected_point)
    if not np.isfinite((center_x, center_y)).all():
        return RotatingTipObservation(None, 0.0, (0, 0, 0, 0))
    left = max(0, int(round(center_x)) - radius_px)
    top = max(0, int(round(center_y)) - radius_px)
    right = min(width, int(round(center_x)) + radius_px + 1)
    bottom = min(height, int(round(center_y)) + radius_px + 1)
    bounds = (left, top, right - left, bottom - top)
    if right - left < 5 or bottom - top < 5:
        return RotatingTipObservation(None, 0.0, bounds)

    roi = image[top:bottom, left:right, :3].astype(np.float32)
    blue, green, red = cv2.split(roi)
    excess_green = 2.0 * green - red - blue
    normalized = cv2.normalize(
        excess_green,
        None,
        0,
        255,
        cv2.NORM_MINMAX,
    ).astype(np.uint8)
    _, mask = cv2.threshold(
        normalized,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        np.ones((3, 3), dtype=np.uint8),
    )
    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_NONE,
    )
    candidates = []
    local_center = np.asarray([center_x - left, center_y - top])
    for contour in contours:
        if cv2.contourArea(contour) < 3:
            continue
        points = contour.reshape(-1, 2).astype(np.float64)
        distances = np.linalg.norm(points - local_center, axis=1)
        nearest_index = int(np.argmin(distances))
        candidates.append((float(distances[nearest_index]), points[nearest_index]))
    if not candidates:
        return RotatingTipObservation(None, 0.0, bounds)
    distance, local_point = min(candidates, key=lambda item: item[0])
    if distance > radius_px * 0.75:
        return RotatingTipObservation(None, 0.0, bounds)
    confidence = max(0.05, 1.0 - distance / max(float(radius_px), 1.0))
    return RotatingTipObservation(
        (
            float(local_point[0] + left),
            float(local_point[1] + top),
        ),
        float(confidence),
        bounds,
    )


__all__ = ["RotatingTipObservation", "detect_rotating_tip_near_projection"]
