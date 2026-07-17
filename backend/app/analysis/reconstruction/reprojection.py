from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ReprojectionStatistics:
    top_mean_px: float
    side_mean_px: float
    overall_mean_px: float
    overall_std_px: float
    maximum_error_px: float
    high_error_count: int
    high_error_ratio: float


def project_points(
    projection_matrix: np.ndarray,
    points_3d: np.ndarray,
) -> np.ndarray:
    projection = np.asarray(projection_matrix, dtype=np.float64)
    points = np.asarray(points_3d, dtype=np.float64).reshape(-1, 3)
    if projection.shape != (3, 4) or not np.isfinite(projection).all():
        raise ValueError("投影矩陣格式無效。")
    if not np.isfinite(points).all():
        raise ValueError("三維點包含無效數值。")
    homogeneous = np.column_stack([points, np.ones(len(points))])
    projected = (projection @ homogeneous.T).T
    depth = projected[:, 2]
    if np.any(np.abs(depth) <= 1e-12):
        raise ValueError("重投影深度無效。")
    pixels = projected[:, :2] / depth[:, None]
    if not np.isfinite(pixels).all():
        raise ValueError("重投影結果包含無效數值。")
    return pixels


def reprojection_errors(
    projection_matrix: np.ndarray,
    points_3d: np.ndarray,
    observed_points: np.ndarray,
) -> np.ndarray:
    observed = np.asarray(observed_points, dtype=np.float64).reshape(-1, 2)
    projected = project_points(projection_matrix, points_3d)
    if len(projected) != len(observed) or not np.isfinite(observed).all():
        raise ValueError("重投影觀測點格式無效。")
    return np.linalg.norm(projected - observed, axis=1)


def summarize_reprojection_errors(
    top_errors: np.ndarray,
    side_errors: np.ndarray,
    *,
    high_error_threshold_px: float = 10.0,
) -> ReprojectionStatistics:
    top = np.asarray(top_errors, dtype=np.float64).reshape(-1)
    side = np.asarray(side_errors, dtype=np.float64).reshape(-1)
    if len(top) != len(side) or not len(top):
        raise ValueError("俯視與側視重投影誤差數量必須相同且非空。")
    if not np.isfinite(top).all() or not np.isfinite(side).all():
        raise ValueError("重投影誤差包含無效數值。")
    if high_error_threshold_px <= 0:
        raise ValueError("高誤差門檻必須大於零。")
    overall = np.concatenate([top, side])
    per_frame_high = np.maximum(top, side) > high_error_threshold_px
    return ReprojectionStatistics(
        top_mean_px=float(np.mean(top)),
        side_mean_px=float(np.mean(side)),
        overall_mean_px=float(np.mean(overall)),
        overall_std_px=float(np.std(overall)),
        maximum_error_px=float(np.max(overall)),
        high_error_count=int(np.count_nonzero(per_frame_high)),
        high_error_ratio=float(np.count_nonzero(per_frame_high) / len(top)),
    )
