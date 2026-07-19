from __future__ import annotations

import cv2
import numpy as np


def _projection_matrix(value: np.ndarray, name: str) -> np.ndarray:
    matrix = np.asarray(value, dtype=np.float64)
    if matrix.shape != (3, 4) or not np.isfinite(matrix).all():
        raise ValueError(f"{name} 投影矩陣格式無效。")
    return matrix


def triangulate_points(
    top_projection_matrix: np.ndarray,
    side_projection_matrix: np.ndarray,
    top_points: np.ndarray,
    side_points: np.ndarray,
    *,
    homogeneous_epsilon: float = 1e-10,
) -> np.ndarray:
    top_projection = _projection_matrix(top_projection_matrix, "俯視")
    side_projection = _projection_matrix(side_projection_matrix, "側視")
    top = np.asarray(top_points, dtype=np.float64).reshape(-1, 2)
    side = np.asarray(side_points, dtype=np.float64).reshape(-1, 2)
    if len(top) != len(side) or not len(top):
        raise ValueError("雙鏡頭三角化需要數量相同且非空的二維點。")
    if not np.isfinite(top).all() or not np.isfinite(side).all():
        raise ValueError("雙鏡頭二維點包含無效數值。")
    homogeneous = cv2.triangulatePoints(
        top_projection,
        side_projection,
        top.T,
        side.T,
    ).T
    weights = homogeneous[:, 3]
    if np.any(np.abs(weights) <= homogeneous_epsilon):
        raise ValueError("三角化結果的齊次座標無效。")
    points = homogeneous[:, :3] / weights[:, None]
    if not np.isfinite(points).all():
        raise ValueError("三角化結果包含無效數值。")
    return points


def triangulate_point(
    top_projection_matrix: np.ndarray,
    side_projection_matrix: np.ndarray,
    top_point: tuple[float, float],
    side_point: tuple[float, float],
) -> tuple[float, float, float]:
    point = triangulate_points(
        top_projection_matrix,
        side_projection_matrix,
        np.asarray([top_point]),
        np.asarray([side_point]),
    )[0]
    return tuple(float(value) for value in point)
