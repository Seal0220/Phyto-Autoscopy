from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np


Resolution = tuple[int, int]


def _resolution(
    value: Resolution,
    label: str,
) -> Resolution:
    try:
        width, height = (int(item) for item in value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label}解析度格式無效。") from error
    if width <= 0 or height <= 0:
        raise ValueError(f"{label}解析度必須大於零。")
    return width, height


def pixel_scale_matrix(
    source_resolution: Resolution,
    target_resolution: Resolution,
) -> np.ndarray:
    source_width, source_height = _resolution(source_resolution, "校正影像")
    target_width, target_height = _resolution(target_resolution, "分析影像")
    return np.asarray(
        [
            [target_width / source_width, 0.0, 0.0],
            [0.0, target_height / source_height, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def scale_camera_matrix(
    camera_matrix: np.ndarray,
    source_resolution: Resolution,
    target_resolution: Resolution,
) -> np.ndarray:
    matrix = np.asarray(camera_matrix, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        raise ValueError("相機矩陣格式無效。")
    return pixel_scale_matrix(source_resolution, target_resolution) @ matrix


def scale_projection_matrix(
    projection_matrix: np.ndarray,
    source_resolution: Resolution,
    target_resolution: Resolution,
) -> np.ndarray:
    matrix = np.asarray(projection_matrix, dtype=np.float64)
    if matrix.shape != (3, 4) or not np.isfinite(matrix).all():
        raise ValueError("投影矩陣格式無效。")
    return pixel_scale_matrix(source_resolution, target_resolution) @ matrix


def scale_fundamental_matrix(
    fundamental_matrix: np.ndarray,
    top_source_resolution: Resolution,
    side_source_resolution: Resolution,
    top_target_resolution: Resolution,
    side_target_resolution: Resolution,
) -> np.ndarray:
    matrix = np.asarray(fundamental_matrix, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        raise ValueError("Fundamental Matrix 格式無效。")
    top_scale = pixel_scale_matrix(
        top_source_resolution,
        top_target_resolution,
    )
    side_scale = pixel_scale_matrix(
        side_source_resolution,
        side_target_resolution,
    )
    return np.linalg.inv(side_scale).T @ matrix @ np.linalg.inv(top_scale)


@dataclass(frozen=True, slots=True)
class CameraResolutionAdaptation:
    resolution: Resolution
    scale_x: float
    scale_y: float
    camera_matrix: np.ndarray
    projection_matrix: np.ndarray


@dataclass(frozen=True, slots=True)
class CameraPairResolutionAdaptation:
    projection_resolution: Resolution
    calibration_resolutions: dict[str, Resolution]
    top: CameraResolutionAdaptation
    side: CameraResolutionAdaptation
    fundamental_matrix: np.ndarray

    def metadata(self) -> dict:
        return {
            "policy": "scale_pixel_coordinate_matrices",
            "projection_resolution": list(self.projection_resolution),
            "cameras": {
                "top": {
                    "calibration_resolution": list(
                        self.calibration_resolutions["top"]
                    ),
                    "analysis_resolution": list(self.top.resolution),
                    "scale_x": self.top.scale_x,
                    "scale_y": self.top.scale_y,
                },
                "side": {
                    "calibration_resolution": list(
                        self.calibration_resolutions["side"]
                    ),
                    "analysis_resolution": list(self.side.resolution),
                    "scale_x": self.side.scale_x,
                    "scale_y": self.side.scale_y,
                },
            },
        }


def adapt_camera_pair_resolution(
    *,
    projection_resolution: Resolution,
    calibration_resolutions: Mapping[str, Resolution],
    camera_resolutions: Mapping[str, Resolution],
    top_camera_matrix: np.ndarray,
    side_camera_matrix: np.ndarray,
    top_projection_matrix: np.ndarray,
    side_projection_matrix: np.ndarray,
    fundamental_matrix: np.ndarray,
) -> CameraPairResolutionAdaptation:
    projection_source = _resolution(
        projection_resolution,
        "投影矩陣",
    )
    missing = [
        camera_id
        for camera_id in ("top", "side")
        if camera_id not in camera_resolutions
        or camera_id not in calibration_resolutions
    ]
    if missing:
        raise ValueError("缺少分析影像解析度：" + ", ".join(missing))

    def adapt_camera(
        camera_id: str,
        camera_matrix: np.ndarray,
        projection_matrix: np.ndarray,
    ) -> CameraResolutionAdaptation:
        target_resolution = _resolution(
            camera_resolutions[camera_id],
            f"{camera_id} 分析影像",
        )
        scale = pixel_scale_matrix(
            calibration_sources[camera_id],
            target_resolution,
        )
        return CameraResolutionAdaptation(
            resolution=target_resolution,
            scale_x=float(scale[0, 0]),
            scale_y=float(scale[1, 1]),
            camera_matrix=scale_camera_matrix(
                camera_matrix,
                calibration_sources[camera_id],
                target_resolution,
            ),
            projection_matrix=scale_projection_matrix(
                projection_matrix,
                projection_source,
                target_resolution,
            ),
        )

    calibration_sources = {
        camera_id: _resolution(
            calibration_resolutions[camera_id],
            f"{camera_id} 校正影像",
        )
        for camera_id in ("top", "side")
    }
    top = adapt_camera(
        "top",
        top_camera_matrix,
        top_projection_matrix,
    )
    side = adapt_camera(
        "side",
        side_camera_matrix,
        side_projection_matrix,
    )
    return CameraPairResolutionAdaptation(
        projection_resolution=projection_source,
        calibration_resolutions=calibration_sources,
        top=top,
        side=side,
        fundamental_matrix=scale_fundamental_matrix(
            fundamental_matrix,
            calibration_sources["top"],
            calibration_sources["side"],
            top.resolution,
            side.resolution,
        ),
    )
