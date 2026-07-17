from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorldCoordinateSystem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin: str = Field(default="花盆或植物基部中心", min_length=1)
    x_axis: str = Field(default="水平方向", min_length=1)
    y_axis: str = Field(default="水平深度方向", min_length=1)
    z_axis: str = Field(default="垂直向上", min_length=1)
    unit: Literal["mm"] = "mm"


class RotatingCalibrationImage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    angle_deg: float


class CalibrationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top_camera_identifier: Literal["top"] = "top"
    side_camera_identifier: Literal["side"] = "side"
    rotating_camera_identifier: Literal["rotating"] = "rotating"
    top_image_paths: list[str] = Field(min_length=1)
    side_image_paths: list[str] = Field(min_length=1)
    stereo_image_pairs: list[list[str]] = Field(min_length=1)
    rotating_images: list[RotatingCalibrationImage] = Field(default_factory=list)
    pattern_columns: int = Field(default=10, ge=2)
    pattern_rows: int = Field(default=7, ge=2)
    square_size_mm_x: float = Field(gt=0)
    square_size_mm_y: float = Field(gt=0)
    stereo_pattern_columns: int = Field(ge=2)
    stereo_pattern_rows: int = Field(ge=2)
    stereo_square_size_mm_x: float = Field(gt=0)
    stereo_square_size_mm_y: float = Field(gt=0)
    individual_board_width_cm: float = Field(default=59.4, gt=0)
    individual_board_height_cm: float = Field(default=84.1, gt=0)
    stereo_board_width_cm: float = Field(default=42.0, gt=0)
    stereo_board_height_cm: float = Field(default=59.4, gt=0)
    notes: str = Field(default="", max_length=2000)
    world_coordinate_system: WorldCoordinateSystem = Field(
        default_factory=WorldCoordinateSystem
    )
    world_transform_matrix: list[list[float]]
    camera_model_name: str = "CM1.3M30M12Q"
    sensor_name: str = "AR0130"
    sensor_width_mm: float = Field(default=4.83, gt=0)
    sensor_height_mm: float = Field(default=3.63, gt=0)
    focal_length_mm: float = Field(default=2.1, gt=0)
    diagonal_fov_deg: float = Field(default=126.0, gt=0, lt=180)

    @model_validator(mode="after")
    def validate_pairs(self) -> "CalibrationCreateRequest":
        if any(len(pair) != 2 for pair in self.stereo_image_pairs):
            raise ValueError("每組雙目校正影像必須包含俯視與側視兩個路徑。")
        image_paths = [
            *self.top_image_paths,
            *self.side_image_paths,
            *(path for pair in self.stereo_image_pairs for path in pair),
            *(item.path for item in self.rotating_images),
        ]
        if any(not path.strip() for path in image_paths):
            raise ValueError("校正影像路徑不得為空。")
        if any(pair[0].strip() == pair[1].strip() for pair in self.stereo_image_pairs):
            raise ValueError("雙目校正的俯視與側視影像不得是同一檔案。")
        top_paths = {path.strip() for path in self.top_image_paths}
        side_paths = {path.strip() for path in self.side_image_paths}
        if top_paths & side_paths:
            raise ValueError("俯視與側視單目校正影像不得重複使用同一檔案。")
        if self.rotating_images:
            angles = [item.angle_deg for item in self.rotating_images]
            if len(set(angles)) < 3:
                raise ValueError("環繞校正至少需要三個不同的馬達角度。")

        try:
            transform = np.asarray(self.world_transform_matrix, dtype=np.float64)
        except (TypeError, ValueError) as error:
            raise ValueError("世界座標轉換矩陣必須是 4×4 數值矩陣。") from error
        if transform.shape != (4, 4) or not np.isfinite(transform).all():
            raise ValueError("世界座標轉換矩陣必須是有限數值的 4×4 矩陣。")
        rotation = transform[:3, :3]
        if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-6):
            raise ValueError("世界座標旋轉矩陣必須正交。")
        if not np.isclose(np.linalg.det(rotation), 1.0, atol=1e-6):
            raise ValueError("世界座標旋轉矩陣行列式必須為 1。")
        if not np.allclose(transform[3], [0.0, 0.0, 0.0, 1.0], atol=1e-9):
            raise ValueError("世界座標轉換矩陣最後一列必須為 [0, 0, 0, 1]。")
        return self


class CalibrationProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calibration_id: str
    created_at: str
    updated_at: str
    status: str
    valid: bool
    output_path: str
    top_camera_identifier: str
    side_camera_identifier: str
    rotating_camera_identifier: str = "rotating"
    camera_model_name: str = "CM1.3M30M12Q"
    sensor_name: str = "AR0130"
    sensor_width_mm: float = 4.83
    sensor_height_mm: float = 3.63
    focal_length_mm: float = 2.1
    diagonal_fov_deg: float = 126.0
    image_width: int | None = None
    image_height: int | None = None
    chessboard_pattern: list[int]
    stereo_chessboard_pattern: list[int] | None = None
    square_size_mm: list[float] | None = None
    stereo_square_size_mm: list[float] | None = None
    individual_board_size_cm: list[float]
    stereo_board_size_cm: list[float]
    paper_baseline: dict
    actual_measurement_difference: dict
    selected_images: dict[str, list]
    camera_fingerprint: dict[str, dict] = Field(default_factory=dict)
    selected_image_fingerprints: dict[str, dict] = Field(default_factory=dict)
    distortion_coefficient_order: list[str] = Field(
        default_factory=lambda: ["k1", "k2", "p1", "p2", "k3"]
    )
    camera_projection_models: dict[str, str] = Field(default_factory=dict)
    camera_model_evaluations: dict[str, dict] = Field(default_factory=dict)
    camera_distortion_orders: dict[str, list[str]] = Field(default_factory=dict)
    camera_image_sizes: dict[str, list[int]] = Field(default_factory=dict)
    top_camera_matrix: list[list[float]] | None = None
    top_distortion_coefficients: list[float] | None = None
    side_camera_matrix: list[list[float]] | None = None
    side_distortion_coefficients: list[float] | None = None
    rotating_camera_matrix: list[list[float]] | None = None
    rotating_distortion_coefficients: list[float] | None = None
    rotation_matrix: list[list[float]] | None = None
    translation_vector: list[float] | None = None
    essential_matrix: list[list[float]] | None = None
    fundamental_matrix: list[list[float]] | None = None
    top_projection_matrix: list[list[float]] | None = None
    side_projection_matrix: list[list[float]] | None = None
    top_rectification_rotation: list[list[float]] | None = None
    side_rectification_rotation: list[list[float]] | None = None
    disparity_to_depth_matrix: list[list[float]] | None = None
    top_valid_pixel_roi: list[int] | None = None
    side_valid_pixel_roi: list[int] | None = None
    world_transform_matrix: list[list[float]] | None = None
    top_rotation_vectors: list[list[float]] = Field(default_factory=list)
    top_translation_vectors: list[list[float]] = Field(default_factory=list)
    side_rotation_vectors: list[list[float]] = Field(default_factory=list)
    side_translation_vectors: list[list[float]] = Field(default_factory=list)
    rotating_rotation_vectors: list[list[float]] = Field(default_factory=list)
    rotating_translation_vectors: list[list[float]] = Field(default_factory=list)
    top_mean_reprojection_error: float | None = None
    side_mean_reprojection_error: float | None = None
    rotating_mean_reprojection_error: float | None = None
    stereo_mean_reprojection_error: float | None = None
    reprojection_error_per_image: dict[str, list[dict]] = Field(default_factory=dict)
    point_coverage: dict[str, dict] = Field(default_factory=dict)
    corner_detections: dict[str, list[dict]] = Field(default_factory=dict)
    world_coordinate_system: WorldCoordinateSystem = Field(
        default_factory=WorldCoordinateSystem
    )
    notes: str = ""
    potentially_invalid_reasons: list[str] = Field(default_factory=list)
    manual_invalidation_reasons: list[str] = Field(default_factory=list)
    rotating_axis_origin_mm: list[float] | None = None
    rotating_axis_direction: list[float] | None = None
    rotating_zero_angle_deg: float | None = None
    rotating_angle_direction: int | None = None
    rotating_axis_from_camera_matrix: list[list[float]] | None = None
    rotating_pose_residual_mean_px: float | None = None
    rotating_pose_residual_max_px: float | None = None
    rotating_pose_samples: list[dict] = Field(default_factory=list)
    last_error: str | None = None

    @property
    def supports_rotating(self) -> bool:
        return all((
            self.rotating_camera_matrix is not None,
            self.rotating_distortion_coefficients is not None,
            self.rotating_axis_origin_mm is not None,
            self.rotating_axis_direction is not None,
            self.rotating_zero_angle_deg is not None,
            self.rotating_angle_direction in {-1, 1},
            self.rotating_axis_from_camera_matrix is not None,
        ))


class CalibrationReport(BaseModel):
    profile: CalibrationProfile
    image_count: dict[str, int]
    successful_corner_detections: dict[str, int]
    mean_reprojection_errors: dict[str, float | None]
    reprojection_error_per_image: dict[str, list[dict]]
    point_coverage: dict[str, dict]
    corner_detections: dict[str, list[dict]]
    valid: bool
    potentially_invalid_reasons: list[str]
