from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator


def _finite_vector(
    value: object,
    size: int,
    label: str,
) -> np.ndarray:
    try:
        vector = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label}必須包含 {size} 個有限數值。") from error
    if vector.shape != (size,) or not np.isfinite(vector).all():
        raise ValueError(f"{label}必須包含 {size} 個有限數值。")
    return vector


def _finite_matrix(
    value: object,
    shape: tuple[int, int],
    label: str,
) -> np.ndarray:
    try:
        matrix = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{label}必須是 {shape[0]}×{shape[1]} 的有限數值矩陣。"
        ) from error
    if matrix.shape != shape or not np.isfinite(matrix).all():
        raise ValueError(
            f"{label}必須是 {shape[0]}×{shape[1]} 的有限數值矩陣。"
        )
    return matrix


def _rigid_matrix(value: object, label: str) -> np.ndarray:
    matrix = _finite_matrix(value, (4, 4), label)
    rotation = matrix[:3, :3]
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-5):
        raise ValueError(f"{label}的旋轉部分必須為正交矩陣。")
    if not np.isclose(np.linalg.det(rotation), 1.0, atol=1e-5):
        raise ValueError(f"{label}的旋轉方向無效。")
    if not np.allclose(matrix[3], [0.0, 0.0, 0.0, 1.0], atol=1e-8):
        raise ValueError(f"{label}最後一列必須為 [0, 0, 0, 1]。")
    return matrix


CameraIdentifier = Literal["top", "side", "rotating"]
CameraModelName = Literal["opencv", "opencv_rational", "opencv_fisheye"]
CalibrationQualityStatus = Literal[
    "excellent",
    "acceptable",
    "warning",
    "failed",
]


class CalibrationBoardProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    board_profile_id: str
    name: str = Field(min_length=1, max_length=120)
    board_type: Literal["charuco", "chessboard"] = "charuco"
    squares_x: int = Field(ge=3, le=64)
    squares_y: int = Field(ge=3, le=64)
    square_length_mm: float = Field(gt=0, le=1000)
    marker_length_mm: float = Field(gt=0, le=1000)
    aruco_dictionary: str = Field(default="DICT_5X5_100", min_length=1, max_length=64)
    paper_size: Literal["a3", "a4", "a5", "letter"] = "a4"
    paper_orientation: Literal["portrait", "landscape"] = "landscape"
    print_margin_mm: float = Field(default=10.0, ge=5, le=30)
    unit: Literal["mm"] = "mm"
    created_at: str
    updated_at: str

    @model_validator(mode="after")
    def validate_marker_size(self) -> "CalibrationBoardProfile":
        if self.board_type == "charuco" and self.marker_length_mm >= self.square_length_mm:
            raise ValueError("ChArUco marker 邊長必須小於方格邊長。")
        return self


class CalibrationBoardCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_size: Literal["a3", "a4", "a5", "letter"] = "a4"
    paper_orientation: Literal["portrait", "landscape"] = "landscape"
    squares_x: int = Field(default=8, ge=3, le=64)
    squares_y: int = Field(default=6, ge=3, le=64)


class IntrinsicRunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    board_profile_id: str = Field(min_length=1, max_length=160)
    capture_mode: Literal["manual", "automatic"] = "manual"
    camera_model: Literal[
        "auto",
        "opencv",
        "opencv_rational",
        "opencv_fisheye",
    ] = "auto"
    minimum_interval_seconds: float = Field(default=1.0, ge=0.1, le=60)


class IntrinsicRunActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=160)


class IntrinsicSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str
    camera_id: CameraIdentifier
    captured_at: str
    image_path: str
    accepted: bool
    rejection_reason: str | None = None
    resolution: list[int]
    marker_count: int = 0
    corner_count: int = 0
    sharpness: float = 0.0
    mean_brightness: float = 0.0
    overexposed_ratio: float = 0.0
    underexposed_ratio: float = 0.0
    board_center: list[float] | None = None
    board_scale: float | None = None
    pose_signature: list[float] | None = None
    object_points: list[list[float]] = Field(default_factory=list)
    image_points: list[list[float]] = Field(default_factory=list)


class IntrinsicRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    camera_id: CameraIdentifier
    board_profile_id: str
    capture_mode: Literal["manual", "automatic"]
    requested_camera_model: str
    minimum_interval_seconds: float = Field(default=1.0, ge=0.1, le=60)
    status: Literal[
        "capturing",
        "ready",
        "solving",
        "solved",
        "failed",
        "cancelled",
        "applied",
    ] = "capturing"
    created_at: str
    updated_at: str
    samples: list[IntrinsicSample] = Field(default_factory=list)
    coverage: dict = Field(default_factory=dict)
    candidate_results: dict[str, dict] = Field(default_factory=dict)
    selected_result: dict | None = None
    last_error: str | None = None


class CameraIntrinsics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    camera_id: CameraIdentifier
    camera_model: CameraModelName
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    camera_matrix: list[list[float]]
    distortion_coefficients: list[float]
    reprojection_error_px: float = Field(ge=0)
    median_reprojection_error_px: float = Field(ge=0)
    maximum_reprojection_error_px: float = Field(ge=0)
    validation_error_px: float = Field(ge=0)
    sample_count: int = Field(ge=1)
    board_profile_id: str
    quality_status: CalibrationQualityStatus
    quality: dict = Field(default_factory=dict)
    source_run_id: str
    created_at: str
    updated_at: str
    status: Literal["valid", "potentially_invalid", "invalid"] = "valid"
    invalidation_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_calibration_values(self) -> "CameraIntrinsics":
        matrix = _finite_matrix(self.camera_matrix, (3, 3), "相機內參矩陣")
        if matrix[0, 0] <= 0 or matrix[1, 1] <= 0:
            raise ValueError("相機內參矩陣的焦距必須大於 0。")
        if not np.allclose(matrix[2], [0.0, 0.0, 1.0], atol=1e-8):
            raise ValueError("相機內參矩陣最後一列必須為 [0, 0, 1]。")
        distortion = np.asarray(
            self.distortion_coefficients,
            dtype=np.float64,
        ).reshape(-1)
        if not len(distortion) or not np.isfinite(distortion).all():
            raise ValueError("鏡頭畸變係數必須包含有限數值。")
        if self.camera_model == "opencv_fisheye" and len(distortion) != 4:
            raise ValueError("OpenCV fisheye 內參必須包含 4 個畸變係數。")
        if self.camera_model == "opencv" and len(distortion) not in {4, 5}:
            raise ValueError("OpenCV 內參必須包含 4 或 5 個畸變係數。")
        if self.camera_model == "opencv_rational" and len(distortion) < 8:
            raise ValueError("OpenCV rational 內參至少需要 8 個畸變係數。")
        return self


class ExtrinsicCameraConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    camera_id: CameraIdentifier
    position_label: str = Field(default="", max_length=120)
    height_mm: float = Field(ge=0, le=10000)
    offset_x_mm: float = Field(default=0.0, ge=-10000, le=10000)
    offset_y_mm: float = Field(default=0.0, ge=-10000, le=10000)
    offset_z_mm: float = Field(default=0.0, ge=-10000, le=10000)
    mount_description: str = Field(default="", max_length=1000)
    is_movable: bool = False
    transform_rig_from_camera: list[list[float]] | None = None
    transform_world_from_camera: list[list[float]] | None = None

    @model_validator(mode="after")
    def validate_transforms(self) -> "ExtrinsicCameraConfiguration":
        if self.transform_rig_from_camera is not None:
            _rigid_matrix(
                self.transform_rig_from_camera,
                f"相機 {self.camera_id} 的 rig 轉換矩陣",
            )
        if self.transform_world_from_camera is not None:
            _rigid_matrix(
                self.transform_world_from_camera,
                f"相機 {self.camera_id} 的世界轉換矩陣",
            )
        return self


class CalibrationMotionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arm_height_mm: float = Field(default=0.0, ge=0, le=10000)
    arm_radius_mm: float = Field(default=0.0, ge=0, le=10000)
    rotation_axis_origin_mm: list[float] | None = None
    rotation_axis_direction: list[float] | None = None
    motor_zero_offset_deg: float | None = None
    mount_transform_from_camera: list[list[float]] | None = None
    lift_axis_direction: list[float] | None = None
    height_reference_mm: float = 0.0
    usable_angle_range_deg: list[float] = Field(default_factory=lambda: [0.0, 360.0])
    fitted_angles_deg: list[float] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_motion_geometry(self) -> "CalibrationMotionModel":
        if self.rotation_axis_origin_mm is not None:
            _finite_vector(self.rotation_axis_origin_mm, 3, "旋轉軸原點")
        if self.rotation_axis_direction is not None:
            direction = _finite_vector(
                self.rotation_axis_direction,
                3,
                "旋轉軸方向",
            )
            if not np.isclose(np.linalg.norm(direction), 1.0, atol=1e-4):
                raise ValueError("旋轉軸方向必須是長度為 1 的向量。")
        if self.lift_axis_direction is not None:
            direction = _finite_vector(
                self.lift_axis_direction,
                3,
                "升降軸方向",
            )
            if not np.isclose(np.linalg.norm(direction), 1.0, atol=1e-4):
                raise ValueError("升降軸方向必須是長度為 1 的向量。")
        if self.mount_transform_from_camera is not None:
            _rigid_matrix(
                self.mount_transform_from_camera,
                "旋臂相機安裝轉換矩陣",
            )
        angle_range = _finite_vector(
            self.usable_angle_range_deg,
            2,
            "可用角度範圍",
        )
        if angle_range[1] <= angle_range[0]:
            raise ValueError("可用角度範圍的結束角度必須大於起始角度。")
        if self.fitted_angles_deg and not np.isfinite(
            np.asarray(self.fitted_angles_deg, dtype=np.float64)
        ).all():
            raise ValueError("校正使用角度必須是有限數值。")
        return self


class CalibrationWorldAlignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin_definition: Literal[
        "platform_center",
        "board_fixture",
        "custom_offset",
    ] = "platform_center"
    origin_offset_mm: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    x_axis_definition: str = "平台水平方向"
    y_axis_definition: str = "平台深度方向"
    z_axis_definition: str = "垂直向上"
    plant_center_mm: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    platform_height_mm: float = 0.0
    unit: Literal["mm"] = "mm"
    transform_world_from_rig: list[list[float]] | None = None

    @model_validator(mode="after")
    def validate_world_geometry(self) -> "CalibrationWorldAlignment":
        _finite_vector(self.origin_offset_mm, 3, "世界原點偏移")
        _finite_vector(self.plant_center_mm, 3, "植物中心")
        if not np.isfinite(self.platform_height_mm):
            raise ValueError("平台高度必須是有限數值。")
        if self.transform_world_from_rig is not None:
            _rigid_matrix(
                self.transform_world_from_rig,
                "世界座標轉換矩陣",
            )
        return self


class ExtrinsicProfileCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    board_profile_id: str = Field(min_length=1, max_length=160)
    camera_ids: list[CameraIdentifier] = Field(min_length=1, max_length=16)
    cameras: list[ExtrinsicCameraConfiguration]
    motion_model: CalibrationMotionModel = Field(default_factory=CalibrationMotionModel)
    world_alignment: CalibrationWorldAlignment = Field(
        default_factory=CalibrationWorldAlignment
    )
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_camera_set(self) -> "ExtrinsicProfileCreateRequest":
        if len(self.camera_ids) != len(set(self.camera_ids)):
            raise ValueError("參與校正的相機不可重複。")
        configured = [item.camera_id for item in self.cameras]
        if len(configured) != len(set(configured)):
            raise ValueError("相機位置資料不可重複。")
        if set(configured) != set(self.camera_ids):
            raise ValueError("相機位置資料必須涵蓋所有參與校正的相機。")
        return self


class ExtrinsicProfilePatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    cameras: list[ExtrinsicCameraConfiguration] | None = None
    motion_model: CalibrationMotionModel | None = None
    world_alignment: CalibrationWorldAlignment | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ExtrinsicProfileCopyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)


class ExtrinsicProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str
    name: str
    status: Literal[
        "draft",
        "validating",
        "valid",
        "invalid",
        "active",
        "archived",
    ] = "draft"
    is_active: bool = False
    board_profile_id: str
    camera_ids: list[CameraIdentifier]
    cameras: list[ExtrinsicCameraConfiguration]
    motion_model: CalibrationMotionModel
    world_alignment: CalibrationWorldAlignment
    quality_status: CalibrationQualityStatus | None = None
    quality: dict = Field(default_factory=dict)
    observation_count: int = 0
    notes: str = ""
    created_at: str
    updated_at: str
    last_error: str | None = None


class CalibrationObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_id: str
    profile_id: str
    captured_at: str
    motor_angle_deg: float | None = None
    arm_height_mm: float | None = None
    camera_images: dict[CameraIdentifier, str]
    detections: dict[CameraIdentifier, dict]
    accepted: bool
    rejection_reason: str | None = None


class ExtrinsicCaptureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    camera_ids: list[CameraIdentifier] | None = None
    motor_angle_deg: float | None = None
    arm_height_mm: float | None = Field(default=None, ge=0, le=10000)


class CalibrationArmHeightRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arm_height_mm: float = Field(ge=0, le=10000)


class QuickRelocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_profile_id: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=120)
    changed_items: list[Literal[
        "arm_height",
        "rotating_mount",
        "top_moved",
        "side_moved",
        "rig_moved",
        "motor_zero",
    ]] = Field(min_length=1)
    arm_height_mm: float | None = Field(default=None, ge=0, le=10000)


class CalibrationLockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["unified", "intrinsic", "extrinsic", "relocation"]
    run_id: str | None = Field(default=None, max_length=160)
    profile_id: str | None = Field(default=None, max_length=160)


class CalibrationLockStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locked: bool = False
    owner: str | None = None
    mode: str | None = None
    run_id: str | None = None
    profile_id: str | None = None
    acquired_at: str | None = None
    expires_at: str | None = None


class CalibrationDetection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    camera_id: CameraIdentifier
    captured_at: str
    connected: bool
    enabled: bool
    board_detected: bool
    marker_count: int = 0
    corner_count: int = 0
    capture_ready: bool = False
    sharpness: float = 0.0
    mean_brightness: float = 0.0
    overexposed_ratio: float = 0.0
    underexposed_ratio: float = 0.0
    warnings: list[str] = Field(default_factory=list)


class CalibrationCaptureResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: bool
    message: str
    intrinsic_run: IntrinsicRun | None = None
    observation: CalibrationObservation | None = None


class CalibrationExportResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str
    export_path: str


class UnifiedCalibrationStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lock: CalibrationLockStatus
    lock_owned_by_requester: bool = False
    cameras: list[dict]
    intrinsics: list[CameraIntrinsics]
    active_extrinsic: ExtrinsicProfile | None = None
    motor: dict = Field(default_factory=dict)
    arm_height_mm: float | None = None
    motor_angle_deg: float | None = None
    detections: dict[str, CalibrationDetection] = Field(default_factory=dict)
    latest_calibration_at: str | None = None
    recent_error: str | None = None
    storage_synchronized: bool = True
    storage_error: str | None = None
