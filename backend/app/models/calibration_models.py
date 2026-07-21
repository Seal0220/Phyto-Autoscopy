from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class CalibrationLockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["intrinsic"] = "intrinsic"
    run_id: str | None = Field(default=None, max_length=160)


class CalibrationLockStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locked: bool = False
    owner: str | None = None
    mode: str | None = None
    run_id: str | None = None
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


class UnifiedCalibrationStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lock: CalibrationLockStatus
    lock_owned_by_requester: bool = False
    cameras: list[dict]
    intrinsics: list[CameraIntrinsics]
    detections: dict[str, CalibrationDetection] = Field(default_factory=dict)
    latest_calibration_at: str | None = None
    recent_error: str | None = None
    storage_synchronized: bool = True
    storage_error: str | None = None
