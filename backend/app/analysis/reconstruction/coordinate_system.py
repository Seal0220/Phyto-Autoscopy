from __future__ import annotations

import numpy as np


def apply_world_transform(
    stereo_points_mm: np.ndarray,
    world_from_stereo: np.ndarray,
) -> np.ndarray:
    points = np.asarray(stereo_points_mm, dtype=np.float64).reshape(-1, 3)
    transform = np.asarray(world_from_stereo, dtype=np.float64)
    if transform.shape != (4, 4) or not np.isfinite(transform).all():
        raise ValueError("世界座標轉換矩陣格式無效。")
    homogeneous = np.column_stack([points, np.ones(len(points))])
    transformed = (transform @ homogeneous.T).T
    weights = transformed[:, 3]
    if np.any(np.abs(weights) <= 1e-12):
        raise ValueError("世界座標轉換產生無效齊次座標。")
    world = transformed[:, :3] / weights[:, None]
    if not np.isfinite(world).all():
        raise ValueError("世界座標包含無效數值。")
    return world


def validate_rigid_transform(world_from_stereo: np.ndarray) -> None:
    transform = np.asarray(world_from_stereo, dtype=np.float64)
    if transform.shape != (4, 4):
        raise ValueError("世界座標轉換矩陣必須是 4×4。")
    rotation = transform[:3, :3]
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-6):
        raise ValueError("世界座標旋轉矩陣不是正交矩陣。")
    if not np.isclose(np.linalg.det(rotation), 1.0, atol=1e-6):
        raise ValueError("世界座標旋轉矩陣行列式必須為 1。")
    if not np.allclose(transform[3], [0, 0, 0, 1], atol=1e-9):
        raise ValueError("世界座標轉換矩陣最後一列無效。")
