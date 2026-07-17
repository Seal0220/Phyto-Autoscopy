from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    AliasChoices,
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
    "failed",
    "cancelled",
]

AnalysisStage = Literal[
    "validating",
    "pairing_frames",
    "calibrating",
    "initializing_background",
    "detecting_top_tip",
    "detecting_side_tip",
    "interpolating",
    "waiting_for_review",
    "triangulating",
    "calculating_reprojection_error",
    "exporting",
    "completed",
]

PairStatus = Literal[
    "paired",
    "top_missing",
    "side_missing",
    "outside_tolerance",
    "manually_aligned",
]

AnalysisMethod = Literal[
    "top_side",
    "top_side_rotating",
]

CameraIdentifier = Literal["top", "side", "rotating"]

DetectionType = Literal[
    "Automatic",
    "Estimated",
    "Interpolated",
    "Manual",
    "Missing",
    "Invalid",
    "background_initialization",
    "lighting_transition",
]


class Roi(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class AnalysisCameraSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    path: str = Field(default="", max_length=2048)


class AnalysisCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str | None = Field(default=None, min_length=1, max_length=160)
    method: AnalysisMethod = "top_side"
    camera_sources: dict[CameraIdentifier, AnalysisCameraSource] = Field(
        default_factory=lambda: {
            "top": AnalysisCameraSource(enabled=True),
            "side": AnalysisCameraSource(enabled=True),
            "rotating": AnalysisCameraSource(enabled=False),
        }
    )
    calibration_id: str = Field(min_length=1, max_length=160)
    start_frame: int | None = Field(default=None, ge=1)
    end_frame: int | None = Field(default=None, ge=1)
    top_roi: Roi | None = None
    side_roi: Roi | None = None
    manual_frame_offset: int | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    manual_review_required: bool = True

    @model_validator(mode="after")
    def validate_frame_range(self) -> "AnalysisCreateRequest":
        if (
            self.start_frame is not None
            and self.end_frame is not None
            and self.end_frame < self.start_frame
        ):
            raise ValueError("結束影格不可小於起始影格。")
        unknown = set(self.camera_sources).difference({"top", "side", "rotating"})
        if unknown:
            raise ValueError("相機來源包含不支援的識別碼。")
        required = (
            ("top", "side", "rotating")
            if self.method == "top_side_rotating"
            else ("top", "side")
        )
        missing = [
            camera_id
            for camera_id in required
            if not self.camera_sources.get(camera_id)
            or not self.camera_sources[camera_id].enabled
        ]
        if missing:
            label = "頂+側+環繞" if self.method == "top_side_rotating" else "頂+側"
            raise ValueError(
                f"{label}方法必須啟用：{', '.join(missing)}。"
            )
        if self.record_id is None:
            missing_paths = [
                camera_id
                for camera_id in required
                if not self.camera_sources[camera_id].path.strip()
            ]
            if missing_paths:
                raise ValueError(
                    "未自動帶入紀錄時必須填寫相機目錄："
                    + ", ".join(missing_paths)
                )
        return self


class AnalysisSourcePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str | None = Field(default=None, min_length=1, max_length=160)
    method: AnalysisMethod = "top_side"
    camera_sources: dict[CameraIdentifier, AnalysisCameraSource]


class AnalysisSourcePreview(BaseModel):
    ready: bool
    camera_frame_counts: dict[str, int] = Field(default_factory=dict)
    camera_resolutions: dict[str, tuple[int, int]] = Field(default_factory=dict)
    camera_directories: dict[str, str] = Field(default_factory=dict)
    pairable_frame_count: int = 0
    rotating_pairable_frame_count: int = 0
    total_frame_count: int = 0
    errors: list[str] = Field(default_factory=list)


class AnalysisReconstructRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manual_review_completed: bool = True


class AnalysisRun(BaseModel):
    analysis_id: str
    record_id: str | None = None
    calibration_id: str | None = None
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


class AnalysisSourceSummary(BaseModel):
    record_id: str
    created_at: str
    status: str
    record_path: str
    top_frame_count: int
    side_frame_count: int
    rotating_frame_count: int = 0
    pairable_frame_count: int
    total_frame_count: int
    camera_resolutions: dict[str, tuple[int, int]] = Field(default_factory=dict)
    camera_directories: dict[str, str] = Field(default_factory=dict)
    calibration_status: str
    ready: bool
    not_ready_reasons: list[str] = Field(default_factory=list)
    analysis_runs: list[AnalysisRun] = Field(default_factory=list)


class AnalysisFramePair(BaseModel):
    pair_id: str
    frame_id: int
    cycle_id: int | None = None
    top_frame_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices("top_frame_id", "top_capture_id"),
    )
    side_frame_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices("side_frame_id", "side_capture_id"),
    )
    rotating_frame_id: int | None = None
    top_timestamp: str | None = None
    side_timestamp: str | None = None
    rotating_timestamp: str | None = None
    rotating_angle_deg: float | None = None
    rotating_timestamp_delta_ms: float | None = None
    timestamp_delta_ms: float | None = None
    frame_offset: int = 0
    pair_status: PairStatus

    @property
    def top_capture_id(self) -> int | None:
        """Compatibility name for the SQLite captures foreign key."""

        return self.top_frame_id

    @property
    def side_capture_id(self) -> int | None:
        """Compatibility name for the SQLite captures foreign key."""

        return self.side_frame_id

    @property
    def rotating_capture_id(self) -> int | None:
        return self.rotating_frame_id


class Point2D(BaseModel):
    x_px: float
    y_px: float


class DetectionResult(BaseModel):
    frame_id: int
    camera_id: CameraIdentifier
    timestamp: str | None = None
    candidate_points: list[Point2D] = Field(default_factory=list)
    selected_point: Point2D | None = None
    detection_type: DetectionType
    valid: bool
    contour: list[list[float]] = Field(default_factory=list)
    epipolar_line: list[float] | None = None
    minimum_path: list[Point2D] = Field(default_factory=list)
    status_reason: str | None = None


class StoredDetection(BaseModel):
    analysis_id: str
    frame_id: int
    camera_id: CameraIdentifier
    automatic_detection: DetectionResult | None = None
    interpolated_detection: DetectionResult | None = None
    resolved_detection: DetectionResult | None = None
    updated_at: str


class ManualCorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frame_id: int = Field(ge=1)
    camera_id: Literal["top", "side"]
    corrected_x_px: float | None = None
    corrected_y_px: float | None = None
    reason: str | None = Field(default=None, max_length=500)
    invalid: bool = False

    @model_validator(mode="after")
    def validate_point(self) -> "ManualCorrectionRequest":
        has_x = self.corrected_x_px is not None
        has_y = self.corrected_y_px is not None
        if not self.invalid and (not has_x or not has_y):
            raise ValueError("人工修正必須同時提供 X 與 Y 座標。")
        if has_x != has_y:
            raise ValueError("人工修正必須同時提供 X 與 Y 座標。")
        return self


class ManualCorrection(BaseModel):
    correction_id: str
    analysis_id: str
    frame_id: int
    camera_id: CameraIdentifier
    automatic_x_px: float | None = None
    automatic_y_px: float | None = None
    corrected_x_px: float | None = None
    corrected_y_px: float | None = None
    operator_id: str
    created_at: str
    reason: str | None = None
    invalid: bool = False


class AnalysisFrameDetail(BaseModel):
    pair: AnalysisFramePair
    top_image_url: str | None = None
    side_image_url: str | None = None
    rotating_image_url: str | None = None
    top_detection: StoredDetection | None = None
    side_detection: StoredDetection | None = None
    rotating_detection: StoredDetection | None = None
    corrections: list[ManualCorrection] = Field(default_factory=list)


class TrajectoryPoint(BaseModel):
    frame_id: int
    cycle_id: int | None = None
    timestamp: str | None = None
    top_x_px: float
    top_y_px: float
    side_x_px: float
    side_y_px: float
    rotating_x_px: float | None = None
    rotating_y_px: float | None = None
    rotating_angle_deg: float | None = None
    x_mm: float
    y_mm: float
    z_mm: float
    refined_x_mm: float | None = None
    refined_y_mm: float | None = None
    refined_z_mm: float | None = None
    top_detection_type: str
    side_detection_type: str
    top_reprojection_error_px: float
    side_reprojection_error_px: float
    rotating_reprojection_error_px: float | None = None
    rotating_used: bool = False
    valid: bool


class ReprojectionErrorRecord(BaseModel):
    frame_id: int
    top_error_px: float
    side_error_px: float
    rotating_error_px: float | None = None
    refined_overall_error_px: float | None = None
    overall_error_px: float
    high_error: bool


class DetectionCategoryStats(BaseModel):
    count: int = 0
    ratio: float = 0.0


class DetectionSummary(BaseModel):
    top: dict[str, DetectionCategoryStats]
    side: dict[str, DetectionCategoryStats]
    rotating: dict[str, DetectionCategoryStats] = Field(default_factory=dict)
    overall: dict[str, DetectionCategoryStats]
    reprojection: dict[str, float | int]
    paper_comparison_notice: str


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
