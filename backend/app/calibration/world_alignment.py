from __future__ import annotations

import numpy as np

from app.models.calibration_models import CalibrationWorldAlignment


def validate_rigid_transform(value: object) -> list[list[float]]:
    matrix = np.asarray(value, dtype=np.float64)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError("系統計算的世界座標轉換不是有效的 4×4 矩陣。")
    rotation = matrix[:3, :3]
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-5):
        raise ValueError("系統計算的世界座標旋轉矩陣不是正交矩陣。")
    if not np.isclose(np.linalg.det(rotation), 1.0, atol=1e-5):
        raise ValueError("系統計算的世界座標旋轉矩陣方向無效。")
    if not np.allclose(matrix[3], [0, 0, 0, 1], atol=1e-8):
        raise ValueError("系統計算的世界座標齊次矩陣格式無效。")
    return matrix.astype(float).tolist()


def default_world_alignment(
    template: CalibrationWorldAlignment,
    transform_world_from_rig: object | None = None,
) -> CalibrationWorldAlignment:
    transform = (
        np.eye(4, dtype=np.float64)
        if transform_world_from_rig is None
        else np.asarray(transform_world_from_rig, dtype=np.float64)
    )
    offset = np.asarray(template.origin_offset_mm, dtype=np.float64)
    if offset.shape != (3,) or not np.isfinite(offset).all():
        raise ValueError("世界原點偏移必須包含三個有限的毫米數值。")
    transform = transform.copy()
    transform[:3, 3] += offset
    return template.model_copy(
        update={
            "origin_definition": template.origin_definition,
            "x_axis_definition": template.x_axis_definition or "平台水平方向",
            "y_axis_definition": template.y_axis_definition or "平台深度方向",
            "z_axis_definition": "垂直向上",
            "unit": "mm",
            "transform_world_from_rig": validate_rigid_transform(transform),
        },
        deep=True,
    )
