from __future__ import annotations

from dataclasses import dataclass
from math import hypot

import cv2
import numpy as np


Point = tuple[float, float]


@dataclass(frozen=True)
class TopCandidateResult:
    candidate_points: list[Point]
    selected_contours: list[np.ndarray]


def farthest_contour_point(
    contour: np.ndarray,
    plant_base: Point,
) -> Point:
    points = contour.reshape(-1, 2)
    if not len(points):
        raise ValueError("植物輪廓沒有可用像素。")
    x, y = max(
        points,
        key=lambda point: (
            hypot(float(point[0]) - plant_base[0], float(point[1]) - plant_base[1]),
            -int(point[1]),
            -int(point[0]),
        ),
    )
    return float(x), float(y)


def top_tip_candidates(
    contours: list[np.ndarray],
    *,
    plant_base: Point,
    num_selected_points: int,
    roi_origin: tuple[int, int] = (0, 0),
) -> TopCandidateResult:
    if num_selected_points < 1:
        raise ValueError("俯視候選輪廓數至少為 1。")
    selected = sorted(contours, key=cv2.contourArea, reverse=True)[
        :num_selected_points
    ]
    origin_x, origin_y = roi_origin
    local_base = plant_base[0] - origin_x, plant_base[1] - origin_y
    candidates = []
    for contour in selected:
        x, y = farthest_contour_point(contour, local_base)
        candidates.append((x + origin_x, y + origin_y))
    return TopCandidateResult(candidates, selected)
