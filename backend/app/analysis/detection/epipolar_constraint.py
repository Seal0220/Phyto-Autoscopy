from __future__ import annotations

import cv2
import numpy as np


def epipolar_line_from_top_point(
    fundamental_matrix: np.ndarray,
    top_point: tuple[float, float],
) -> tuple[float, float, float]:
    matrix = np.asarray(fundamental_matrix, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        raise ValueError("Fundamental Matrix 格式無效。")
    point = np.asarray(top_point, dtype=np.float32).reshape(1, 1, 2)
    line = cv2.computeCorrespondEpilines(point, 1, matrix).reshape(3)
    if not np.isfinite(line).all() or np.hypot(line[0], line[1]) <= 1e-12:
        raise ValueError("無法由俯視尖端計算有效的側視極線。")
    return tuple(float(value) for value in line)


def point_line_distance(
    point: tuple[float, float],
    line: tuple[float, float, float],
) -> float:
    a, b, c = line
    denominator = float(np.hypot(a, b))
    if denominator <= 1e-12:
        raise ValueError("極線係數無效。")
    return abs(a * point[0] + b * point[1] + c) / denominator


def contour_epipolar_distance(
    contour: np.ndarray,
    line: tuple[float, float, float],
) -> float:
    points = contour.reshape(-1, 2)
    if not len(points):
        return float("inf")
    return min(
        point_line_distance((float(x), float(y)), line)
        for x, y in points
    )


def filter_contours_by_epipolar_line(
    contours: list[np.ndarray],
    line: tuple[float, float, float],
    *,
    maximum_distance_px: float,
    maximum_count: int,
) -> list[np.ndarray]:
    if maximum_distance_px <= 0 or maximum_count < 1:
        raise ValueError("極線距離門檻與候選數必須大於零。")
    ranked = sorted(
        (
            (contour_epipolar_distance(contour, line), contour)
            for contour in contours
        ),
        key=lambda item: item[0],
    )
    return [
        contour
        for distance, contour in ranked
        if distance <= maximum_distance_px
    ][:maximum_count]
