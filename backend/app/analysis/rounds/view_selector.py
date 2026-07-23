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


def _selection_score(
    view: AnalysisView,
    pose: CameraPoseResult | None,
    quality: ViewImageQuality | None,
) -> float:
    score = quality.selection_score if quality is not None else 0.0
    if pose is not None and pose.aruco_reprojection_error_px is not None:
        score -= float(pose.aruco_reprojection_error_px) * 0.15
    return score


def _best_view(
    views: Sequence[AnalysisView],
    poses: Mapping[str, CameraPoseResult],
    qualities: Mapping[str, ViewImageQuality],
) -> AnalysisView | None:
    valid = [
        view
        for view in views
        if (pose := poses.get(view.view_id)) is not None and pose.valid
    ]
    if not valid:
        return None
    return max(
        valid,
        key=lambda item: (
            _selection_score(
                item,
                poses.get(item.view_id),
                qualities.get(item.view_id),
            ),
            item.timestamp,
            item.view_id,
        ),
    )


def select_round_reconstruction_views(
    views: Sequence[AnalysisView],
    poses: Mapping[str, CameraPoseResult],
    qualities: Mapping[str, ViewImageQuality],
) -> ViewSelectionResult:
    selected: set[str] = set()
    warnings: list[str] = []
    for camera_id, label in (("top", "俯視"), ("side", "側視")):
        candidates = [view for view in views if view.camera_id == camera_id]
        representative = _best_view(candidates, poses, qualities)
        if representative is None:
            warnings.append(f"找不到具有有效姿態的{label}代表影像。")
        else:
            selected.add(representative.view_id)

    rotating_by_angle: dict[float, list[AnalysisView]] = {}
    for view in views:
        if view.camera_id != "rotating":
            continue
        if view.angle_deg is None:
            continue
        rotating_by_angle.setdefault(round(float(view.angle_deg), 6), []).append(
            view
        )
    for angle, candidates in sorted(rotating_by_angle.items()):
        representative = _best_view(candidates, poses, qualities)
        if representative is None:
            warnings.append(f"旋臂 {angle:g}° 沒有具有有效姿態的影像。")
        else:
            selected.add(representative.view_id)

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
            elif view.camera_id in {"top", "side"}:
                exclusion_reason = "固定攝影機重複影像未選為代表影像。"
            elif view.angle_deg is None:
                exclusion_reason = "旋臂影像缺少角度資料。"
            else:
                exclusion_reason = "相同旋臂角度已有品質較佳的代表影像。"
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
                        pose.aruco_reprojection_error_px
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
