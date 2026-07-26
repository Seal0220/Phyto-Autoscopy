from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


PoseSource = Literal[
    "aruco",
    "aruco_refined",
    "sfm",
    "motor_prior",
    "interpolated",
    "unresolved",
]


class CameraPoseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_id: int
    camera_id: Literal["top", "side", "rotating"]
    relative_path: str
    timestamp: str | None = None
    motor_angle_deg: float | None = None
    source: PoseSource = "unresolved"
    resolved: bool = False
    world_to_camera_matrix: list[list[float]] | None = None
    camera_to_world_matrix: list[list[float]] | None = None
    visible_marker_ids: list[int] = Field(default_factory=list)
    visible_marker_count: int = 0
    pnp_inlier_count: int = 0
    aruco_reprojection_error_px: float | None = None
    sfm_match_count: int = 0
    quality_warnings: list[str] = Field(default_factory=list)
    failure_reason: str | None = None


class PoseQualitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["success", "partial", "failed"]
    total_image_count: int
    resolved_image_count: int
    unresolved_image_count: int
    aruco_image_count: int
    aruco_refined_image_count: int
    sfm_image_count: int
    sfm_registered_image_count: int
    motor_prior_image_count: int
    interpolated_image_count: int
    average_aruco_reprojection_error_px: float | None = None
    sfm_registration_rate: float = 0.0
    fixed_camera_dispersion: dict[str, dict[str, float]] = Field(
        default_factory=dict
    )
    rotating_pose_continuity: dict[str, float | int | None] = Field(
        default_factory=dict
    )
    motor_trajectory_consistency: dict[str, float | int | None] = Field(
        default_factory=dict
    )
    required_camera_failures: list[str] = Field(default_factory=list)


class PoseAlignmentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pose_estimation_version: str
    aruco_alignment_status: Literal["success", "partial", "failed"]
    camera_poses: list[CameraPoseResult]
    fixed_camera_poses: dict[str, list[list[float]]] = Field(default_factory=dict)
    quality: PoseQualitySummary
    aruco_detections: list[dict] = Field(default_factory=list)
