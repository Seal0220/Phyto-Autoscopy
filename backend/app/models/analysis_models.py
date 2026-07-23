from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


AnalysisStatus = Literal[
    "draft",
    "validating",
    "ready",
    "processing",
    "needs_review",
    "reviewing",
    "reconstructing",
    "completed",
    "partially_completed",
    "failed",
    "cancelled",
]

AnalysisStage = Literal[
    "validating",
    "grouping_rounds",
    "snapshotting_intrinsics",
    "undistorting_images",
    "detecting_aruco",
    "estimating_camera_poses",
    "refining_camera_poses",
    "selecting_reconstruction_views",
    "extracting_features",
    "matching_features",
    "initializing_round_geometry",
    "detecting_tip_candidates",
    "reconstructing_round_model",
    "isolating_plant_model",
    "extracting_model_point_cloud",
    "extracting_model_skeleton",
    "triangulating_tip_marker",
    "refining_tip_marker",
    "linking_tip_trajectory",
    "calculating_quality_metrics",
    "waiting_for_review",
    "exporting",
    "completed",
]

NewAnalysisMethod = Literal[
    "round_multiview",
    "top_side_tip_only",
]

CameraIdentifier = Literal["top", "side", "rotating"]

class AnalysisCameraSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    path: str = Field(default="", max_length=2048)


class AnalysisCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(min_length=1, max_length=160)
    mode_ids: list[str] = Field(default_factory=list, max_length=20)
    method: NewAnalysisMethod = "top_side_tip_only"
    camera_sources: dict[CameraIdentifier, AnalysisCameraSource] = Field(
        default_factory=lambda: {
            "top": AnalysisCameraSource(enabled=True),
            "side": AnalysisCameraSource(enabled=True),
            "rotating": AnalysisCameraSource(enabled=False),
        }
    )
    parameters: dict[str, Any] = Field(default_factory=dict)
    manual_review_required: bool = True

    @model_validator(mode="after")
    def validate_sources(self) -> "AnalysisCreateRequest":
        if len(self.mode_ids) != len(set(self.mode_ids)):
            raise ValueError("分析擷取模式不可重複。")
        if not self.mode_ids:
            raise ValueError("請至少選擇一個擷取模式。")
        unknown = set(self.camera_sources).difference({"top", "side", "rotating"})
        if unknown:
            raise ValueError("相機來源包含不支援的識別碼。")
        required = (
            ("top", "side", "rotating")
            if self.method == "round_multiview"
            else ("top", "side")
        )
        missing = [
            camera_id
            for camera_id in required
            if not self.camera_sources.get(camera_id)
            or not self.camera_sources[camera_id].enabled
        ]
        if missing:
            label = (
                "每輪多視角三維重建"
                if self.method == "round_multiview"
                else "雙鏡頭尖端分析"
            )
            raise ValueError(
                f"{label}方法必須啟用：{', '.join(missing)}。"
            )
        return self


class AnalysisSourcePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(min_length=1, max_length=160)
    mode_ids: list[str] = Field(default_factory=list, max_length=20)
    method: NewAnalysisMethod = "top_side_tip_only"
    camera_sources: dict[CameraIdentifier, AnalysisCameraSource]


class AnalysisRoundReadiness(BaseModel):
    round_key: str
    mode_id: str
    round_id: str
    status: str
    view_count: int = 0
    top_view_count: int = 0
    side_view_count: int = 0
    rotating_view_count: int = 0
    angular_coverage_deg: float | None = None
    duration_seconds: float | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AnalysisSourcePreview(BaseModel):
    ready: bool
    camera_frame_counts: dict[str, int] = Field(default_factory=dict)
    camera_resolutions: dict[str, tuple[int, int]] = Field(default_factory=dict)
    camera_directories: dict[str, str] = Field(default_factory=dict)
    pairable_frame_count: int = 0
    rotating_pairable_frame_count: int = 0
    total_frame_count: int = 0
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    round_count: int = 0
    ready_round_count: int = 0
    incomplete_round_count: int = 0
    total_view_count: int = 0
    round_readiness: list[AnalysisRoundReadiness] = Field(default_factory=list)
    intrinsics_readiness: dict[str, dict[str, Any]] = Field(default_factory=dict)
    aruco_readiness: dict[str, Any] = Field(default_factory=dict)
    backend_readiness: dict[str, Any] = Field(default_factory=dict)


class AnalysisReconstructRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manual_review_completed: bool = True


class AnalysisRun(BaseModel):
    analysis_id: str
    record_id: str | None = None
    intrinsics_snapshot: dict[str, dict[str, Any]] = Field(default_factory=dict)
    aruco_layout_snapshot: dict[str, Any] = Field(default_factory=dict)
    camera_pose_results: list[dict[str, Any]] = Field(default_factory=list)
    pose_estimation_version: str | None = None
    pose_quality: dict[str, Any] = Field(default_factory=dict)
    reconstruction_backend: str | None = None
    reconstruction_backend_version: str | None = None
    reconstruction_environment: dict[str, Any] = Field(default_factory=dict)
    round_count: int = 0
    completed_round_count: int = 0
    failed_round_count: int = 0
    tip_marker_count: int = 0
    trajectory_status: str | None = None
    cancel_requested_at: str | None = None
    cancel_requested_by: str | None = None
    method_name: str
    method_version: str
    git_commit: str
    parameters: dict[str, Any]
    created_at: str
    updated_at: str
    created_by: str
    output_path: str
    status: AnalysisStatus
    stage: AnalysisStage | None = None
    current_frame: int = 0
    total_frames: int = 0
    progress: float = 0.0
    manual_review_completed: bool = False
    average_reprojection_error_px: float | None = None
    last_error: str | None = None


class AnalysisSourceMode(BaseModel):
    id: str
    type: str
    label: str
    folder: str
    storage_scope: str
    configuration: dict[str, Any] = Field(default_factory=dict)
    image_count: int = Field(default=0, ge=0)


class AnalysisSourceSummary(BaseModel):
    record_id: str
    created_at: str
    ended_at: str | None = None
    status: str
    record_path: str
    top_frame_count: int
    side_frame_count: int
    rotating_frame_count: int = 0
    pairable_frame_count: int
    total_frame_count: int
    total_image_count: int = Field(default=0, ge=0)
    camera_resolutions: dict[str, tuple[int, int]] = Field(default_factory=dict)
    camera_directories: dict[str, str] = Field(default_factory=dict)
    capture_configuration: dict[str, Any] = Field(default_factory=dict)
    ready: bool
    not_ready_reasons: list[str] = Field(default_factory=list)
    available_modes: list[AnalysisSourceMode] = Field(default_factory=list)
    analysis_runs: list[AnalysisRun] = Field(default_factory=list)


class AnalysisRound(BaseModel):
    analysis_id: str
    round_key: str
    record_id: str
    mode_id: str
    round_id: str
    started_at: str | None = None
    ended_at: str | None = None
    duration_seconds: float | None = None
    status: str
    view_count: int = 0
    top_view_count: int = 0
    side_view_count: int = 0
    rotating_view_count: int = 0
    angular_coverage_deg: float | None = None
    static_scene_score: float | None = None
    model_result_id: str | None = None
    tip_landmark_id: str | None = None
    failure_reason: str | None = None


class AnalysisView(BaseModel):
    analysis_id: str
    round_key: str
    view_id: str
    capture_id: int
    camera_id: CameraIdentifier
    snapshot_id: str | None = None
    timestamp: str
    relative_path: str
    absolute_path: str
    angle_deg: float | None = None
    motor_position_deg: float | None = None
    image_width: int
    image_height: int
    image_sha256: str
    selected_for_reconstruction: bool = False
    exclusion_reason: str | None = None
    pose_status: str | None = None
    pose_reprojection_error_px: float | None = None


class CameraPoseResult(BaseModel):
    analysis_id: str
    round_key: str
    view_id: str
    camera_id: CameraIdentifier
    rotation_matrix: list[list[float]] | None = None
    translation_vector_mm: list[float] | None = None
    camera_center_world_mm: list[float] | None = None
    detected_marker_ids: list[int] = Field(default_factory=list)
    detected_corner_count: int = 0
    aruco_reprojection_error_px: float | None = None
    refinement_reprojection_error_px: float | None = None
    pose_source: str
    valid: bool
    failure_reason: str | None = None


class RoundModelResult(BaseModel):
    analysis_id: str
    round_key: str
    model_id: str
    backend: str
    backend_version: str
    status: str
    source_view_ids: list[str] = Field(default_factory=list)
    model_path: str | None = None
    point_cloud_path: str | None = None
    plant_point_cloud_path: str | None = None
    skeleton_path: str | None = None
    preview_paths: list[str] = Field(default_factory=list)
    gaussian_count: int | None = None
    point_count: int | None = None
    training_iterations: int | None = None
    training_duration_seconds: float | None = None
    model_quality: dict[str, Any] = Field(default_factory=dict)
    failure_reason: str | None = None


class TipLandmark(BaseModel):
    analysis_id: str
    round_key: str
    tip_id: str
    record_id: str = ""
    mode_id: str = ""
    round_id: str = ""
    timestamp: str | None = None
    x_mm: float | None = None
    y_mm: float | None = None
    z_mm: float | None = None
    confidence: float = Field(ge=0, le=1)
    valid: bool
    source: str
    supporting_view_ids: list[str] = Field(default_factory=list)
    visible_view_count: int = 0
    mean_reprojection_error_px: float | None = None
    maximum_reprojection_error_px: float | None = None
    distance_to_model_mm: float | None = None
    distance_to_skeleton_mm: float | None = None
    temporal_distance_mm: float | None = None
    detection_type: str
    manually_corrected: bool = False
    failure_reason: str | None = None


class TipObservation2D(BaseModel):
    analysis_id: str
    round_key: str
    view_id: str
    candidate_id: str
    x_px: float
    y_px: float
    confidence: float = Field(ge=0, le=1)
    visibility_confidence: float = Field(ge=0, le=1)
    selected: bool = False
    rejection_reason: str | None = None


class TipTrajectoryPoint(BaseModel):
    analysis_id: str
    record_id: str
    mode_id: str
    round_key: str
    round_id: str
    point_index: int = Field(ge=0)
    timestamp: str | None = None
    x_mm: float | None = None
    y_mm: float | None = None
    z_mm: float | None = None
    confidence: float = Field(ge=0, le=1)
    valid: bool
    detection_type: Literal[
        "measured",
        "estimated",
        "interpolated",
        "manual",
        "invalid",
    ]
    visible_view_count: int = 0
    mean_reprojection_error_px: float | None = None
    manually_corrected: bool = False
    elapsed_seconds: float | None = None
    adjacent_distance_mm: float | None = None
    speed_mm_per_second: float | None = None
    acceleration_mm_per_second2: float | None = None
    direction_x: float | None = None
    direction_y: float | None = None
    direction_z: float | None = None
    horizontal_displacement_mm: float | None = None
    vertical_displacement_mm: float | None = None
    path_length_mm: float | None = None
    curvature_per_mm: float | None = None
    missing_segment: bool = False


class TipCorrectionObservation(BaseModel):
    view_id: str = Field(min_length=1, max_length=240)
    x_px: float
    y_px: float


class TipCorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round_key: str = Field(min_length=1, max_length=320)
    observations: list[TipCorrectionObservation] = Field(
        default_factory=list,
        max_length=64,
    )
    corrected_point_mm: list[float] | None = Field(
        default=None,
        min_length=3,
        max_length=3,
    )
    invalid: bool = False
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_correction(self) -> "TipCorrectionRequest":
        if self.invalid:
            if self.observations or self.corrected_point_mm is not None:
                raise ValueError("無效標記不可同時提供修正座標。")
            return self
        if self.corrected_point_mm is not None:
            if self.observations:
                raise ValueError("二維與三維修正不可同時送出。")
            return self
        unique_views = {item.view_id for item in self.observations}
        if len(unique_views) < 2:
            raise ValueError("二維修正至少需要兩個不同視角。")
        if len(unique_views) != len(self.observations):
            raise ValueError("每個視角只能提供一個人工尖端位置。")
        return self


class TipCorrection(BaseModel):
    correction_id: str
    analysis_id: str
    round_key: str
    operator_id: str
    created_at: str
    reason: str
    correction_type: Literal["views", "point", "invalid"] = "views"
    invalid: bool = False
    automatic_tip: TipLandmark
    corrected_tip: TipLandmark
    supporting_views: list[str] = Field(default_factory=list)
    projected_observations: list[TipCorrectionObservation] = Field(
        default_factory=list
    )
    reprojection_before_px: float | None = None
    reprojection_after_px: float | None = None
    confidence_before: float
    confidence_after: float


class AnalysisProgress(BaseModel):
    analysis_id: str | None = None
    status: str = "idle"
    stage: str | None = None
    current_frame: int = 0
    total_frames: int = 0
    progress: float = 0.0
    last_error: str | None = None

    @field_validator("progress")
    @classmethod
    def clamp_progress(cls, value: float) -> float:
        return min(max(value, 0.0), 1.0)
