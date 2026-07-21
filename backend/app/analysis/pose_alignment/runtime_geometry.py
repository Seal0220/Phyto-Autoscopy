from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class RuntimeAnalysisGeometry:
    """Ephemeral geometry derived only from one Analysis Run's snapshots."""

    image_width: int
    image_height: int
    camera_projection_models: dict[str, str]
    camera_image_sizes: dict[str, list[int]]
    top_camera_matrix: list[list[float]]
    top_distortion_coefficients: list[float]
    side_camera_matrix: list[list[float]]
    side_distortion_coefficients: list[float]
    fundamental_matrix: list[list[float]]
    top_projection_matrix: list[list[float]]
    side_projection_matrix: list[list[float]]
    top_rectification_rotation: list[list[float]]
    side_rectification_rotation: list[list[float]]
    world_transform_matrix: list[list[float]]


def _value(source: object, name: str):
    if isinstance(source, Mapping):
        return source[name]
    return getattr(source, name)


def _camera_model_label(intrinsics: object) -> str:
    return (
        "fisheye"
        if _value(intrinsics, "camera_model") == "opencv_fisheye"
        else "pinhole"
    )


def _scaled_matrix(
    intrinsics: object,
    target_size: tuple[int, int],
) -> np.ndarray:
    matrix = np.asarray(
        _value(intrinsics, "camera_matrix"),
        dtype=np.float64,
    ).reshape(3, 3)
    scale_x = target_size[0] / float(_value(intrinsics, "width"))
    scale_y = target_size[1] / float(_value(intrinsics, "height"))
    result = matrix.copy()
    result[0, :3] *= scale_x
    result[1, :3] *= scale_y
    return result


def _skew(vector: np.ndarray) -> np.ndarray:
    x, y, z = vector.reshape(3)
    return np.asarray(
        [
            [0.0, -z, y],
            [z, 0.0, -x],
            [-y, x, 0.0],
        ],
        dtype=np.float64,
    )


def build_runtime_analysis_geometry(
    intrinsics_by_camera: Mapping[str, object],
    fixed_world_to_camera: Mapping[str, list[list[float]]],
) -> RuntimeAnalysisGeometry:
    missing_intrinsics = [
        camera_id
        for camera_id in ("top", "side")
        if camera_id not in intrinsics_by_camera
    ]
    missing_poses = [
        camera_id
        for camera_id in ("top", "side")
        if camera_id not in fixed_world_to_camera
    ]
    if missing_intrinsics:
        raise ValueError("缺少固定相機內參：" + ", ".join(missing_intrinsics))
    if missing_poses:
        raise ValueError("缺少固定相機姿態：" + ", ".join(missing_poses))

    top = intrinsics_by_camera["top"]
    side = intrinsics_by_camera["side"]
    canonical_size = (
        int(_value(top, "width")),
        int(_value(top, "height")),
    )
    top_matrix = _scaled_matrix(top, canonical_size)
    side_matrix = _scaled_matrix(side, canonical_size)
    top_world_to_camera = np.asarray(
        fixed_world_to_camera["top"],
        dtype=np.float64,
    ).reshape(4, 4)
    side_world_to_camera = np.asarray(
        fixed_world_to_camera["side"],
        dtype=np.float64,
    ).reshape(4, 4)
    side_from_top = side_world_to_camera @ np.linalg.inv(top_world_to_camera)
    rotation = side_from_top[:3, :3]
    translation = side_from_top[:3, 3]
    try:
        (
            top_rectification,
            side_rectification,
            top_projection,
            side_projection,
            *_,
        ) = cv2.stereoRectify(
            top_matrix,
            np.zeros(5, dtype=np.float64),
            side_matrix,
            np.zeros(5, dtype=np.float64),
            canonical_size,
            rotation,
            translation.reshape(3, 1),
            flags=cv2.CALIB_ZERO_DISPARITY,
            alpha=0,
        )
    except cv2.error as error:
        raise ValueError(f"同次分析的雙鏡頭幾何建立失敗：{error}") from error
    essential = _skew(translation) @ rotation
    fundamental = (
        np.linalg.inv(side_matrix).T
        @ essential
        @ np.linalg.inv(top_matrix)
    )
    norm = float(np.linalg.norm(fundamental))
    if norm <= 1e-12 or not np.isfinite(fundamental).all():
        raise ValueError("同次分析的 Fundamental Matrix 無效。")
    fundamental /= norm
    image_sizes = {
        camera_id: [
            int(_value(intrinsics, "width")),
            int(_value(intrinsics, "height")),
        ]
        for camera_id, intrinsics in intrinsics_by_camera.items()
    }
    projection_models = {
        camera_id: _camera_model_label(intrinsics)
        for camera_id, intrinsics in intrinsics_by_camera.items()
    }
    return RuntimeAnalysisGeometry(
        image_width=canonical_size[0],
        image_height=canonical_size[1],
        camera_projection_models=projection_models,
        camera_image_sizes=image_sizes,
        top_camera_matrix=_value(top, "camera_matrix"),
        top_distortion_coefficients=_value(
            top,
            "distortion_coefficients",
        ),
        side_camera_matrix=_value(side, "camera_matrix"),
        side_distortion_coefficients=_value(
            side,
            "distortion_coefficients",
        ),
        fundamental_matrix=fundamental.tolist(),
        top_projection_matrix=top_projection.tolist(),
        side_projection_matrix=side_projection.tolist(),
        top_rectification_rotation=top_rectification.tolist(),
        side_rectification_rotation=side_rectification.tolist(),
        world_transform_matrix=np.linalg.inv(top_world_to_camera).tolist(),
    )
