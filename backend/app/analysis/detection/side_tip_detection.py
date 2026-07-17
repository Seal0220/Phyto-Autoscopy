from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from app.analysis.detection.epipolar_constraint import (
    filter_contours_by_epipolar_line,
)
from app.analysis.detection.minimum_path import (
    MinimumPathResult,
    minimum_path_tip,
)


@dataclass(frozen=True)
class SideCandidateResult:
    candidate_points: list[tuple[float, float]]
    selected_contours: list[np.ndarray]
    minimum_paths: list[MinimumPathResult]


def side_tip_candidates(
    contours: list[np.ndarray],
    *,
    image_shape: tuple[int, int],
    plant_base: tuple[float, float],
    epipolar_line: tuple[float, float, float],
    maximum_epipolar_distance_px: float,
    num_selected_points: int,
    connectivity: int,
    roi_origin: tuple[int, int] = (0, 0),
) -> SideCandidateResult:
    if num_selected_points < 1:
        raise ValueError("側視候選輪廓數至少為 1。")
    origin_x, origin_y = roi_origin
    local_line = (
        epipolar_line[0],
        epipolar_line[1],
        epipolar_line[2]
        + epipolar_line[0] * origin_x
        + epipolar_line[1] * origin_y,
    )
    selected = filter_contours_by_epipolar_line(
        contours,
        local_line,
        maximum_distance_px=maximum_epipolar_distance_px,
        maximum_count=num_selected_points,
    )
    paths = []
    for contour in selected:
        mask = np.zeros(image_shape, dtype=np.uint8)
        cv2.drawContours(mask, [contour], -1, 255, thickness=cv2.FILLED)
        result = minimum_path_tip(
            mask,
            plant_base=plant_base,
            epipolar_line=epipolar_line,
            maximum_epipolar_distance_px=maximum_epipolar_distance_px,
            connectivity=connectivity,
            origin=roi_origin,
        )
        if result is not None:
            paths.append(result)
    return SideCandidateResult(
        candidate_points=[result.candidate_point for result in paths],
        selected_contours=selected,
        minimum_paths=paths,
    )
