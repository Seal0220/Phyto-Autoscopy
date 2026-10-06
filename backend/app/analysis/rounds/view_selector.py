from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from app.analysis.rounds.round_quality import ViewImageQuality
from app.models.analysis_models import (
    AnalysisView,
    CameraPoseResult,
)


@dataclass(frozen=True, slots=True)
class ViewSelectionResult:
    views: tuple[AnalysisView, ...]
    selected_view_ids: tuple[str, ...]
    warnings: tuple[str, ...]


def select_round_reconstruction_views(
    views: Sequence[AnalysisView],
    poses: Mapping[str, CameraPoseResult],
    qualities: Mapping[str, ViewImageQuality],
) -> ViewSelectionResult:
    selected: set[str] = set()
    warnings: list[str] = []
    for view in views:
        pose = poses.get(view.view_id)
        if pose is None or not pose.valid:
            continue
        if view.camera_id == "rotating" and view.angle_deg is None and view.motor_position_deg is None:
            continue
        selected.add(view.view_id)
    for camera_id, label in (("top", "俯視"), ("side", "側視")):
        if not any(view.camera_id == camera_id and view.view_id in selected for view in views):
            warnings.append(f"找不到具有有效姿態的{label}影像。")

    updated: list[AnalysisView] = []
    for view in views:
        pose = poses.get(view.view_id)
        selected_for_reconstruction = view.view_id in selected
        exclusion_reason = None
        if not selected_for_reconstruction:
            if pose is None or not pose.valid:
                exclusion_reason = (
                    pose.failure_reason
                    if pose is not None and pose.failure_reason
                    else "相機姿態無效。"
                )
            elif view.angle_deg is None and view.motor_position_deg is None:
                exclusion_reason = "旋臂影像缺少角度資料。"
        updated.append(
            view.model_copy(
                update={
                    "selected_for_reconstruction": (
                        selected_for_reconstruction
                    ),
                    "exclusion_reason": exclusion_reason,
                    "pose_status": (
                        pose.pose_source if pose is not None else "invalid"
                    ),
                    "pose_reprojection_error_px": (
                        pose.refinement_reprojection_error_px
                        if pose is not None and pose.refinement_reprojection_error_px is not None
                        else pose.aruco_reprojection_error_px
                        if pose is not None
                        else None
                    ),
                }
            )
        )
    return ViewSelectionResult(
        views=tuple(updated),
        selected_view_ids=tuple(sorted(selected)),
        warnings=tuple(warnings),
    )
