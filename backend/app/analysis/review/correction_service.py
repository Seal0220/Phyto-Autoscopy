from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from app.analysis.tip.candidate_detector import TipCandidate2D
from app.analysis.tip.candidate_matcher import (
    TipCandidateView,
    triangulate_tip_hypotheses,
)
from app.analysis.tip.marker_optimizer import optimize_tip_marker
from app.analysis.tip.skeleton_extractor import SkeletonEndpoint
from app.analysis.reconstruction.plant_isolation import point_cloud_support
from app.models.analysis_models import (
    AnalysisRound,
    AnalysisView,
    CameraPoseResult,
    RoundModelResult,
    TipCorrection,
    TipCorrectionObservation,
    TipCorrectionRequest,
    TipLandmark,
)


def _projection(
    pose: CameraPoseResult,
    intrinsics: Mapping[str, Any],
) -> np.ndarray:
    rotation = np.asarray(pose.rotation_matrix, dtype=np.float64)
    translation = np.asarray(
        pose.translation_vector_mm,
        dtype=np.float64,
    ).reshape(3)
    camera_matrix = np.asarray(
        intrinsics["undistorted_camera_matrix"],
        dtype=np.float64,
    )
    if rotation.shape != (3, 3) or camera_matrix.shape != (3, 3):
        raise ValueError("人工修正使用的相機姿態或內參格式無效。")
    return camera_matrix @ np.column_stack((rotation, translation))


def _camera_center(pose: CameraPoseResult) -> np.ndarray:
    if pose.camera_center_world_mm is not None:
        return np.asarray(pose.camera_center_world_mm, dtype=np.float64)
    rotation = np.asarray(pose.rotation_matrix, dtype=np.float64)
    translation = np.asarray(
        pose.translation_vector_mm,
        dtype=np.float64,
    ).reshape(3)
    return -(rotation.T @ translation)


def _project(
    projection: np.ndarray,
    point: np.ndarray,
) -> tuple[float, float] | None:
    homogeneous = projection @ np.append(point, 1.0)
    if not np.all(np.isfinite(homogeneous)) or homogeneous[2] <= 1e-9:
        return None
    return (
        float(homogeneous[0] / homogeneous[2]),
        float(homogeneous[1] / homogeneous[2]),
    )


def _automatic_position(item: TipLandmark) -> np.ndarray | None:
    values = (item.x_mm, item.y_mm, item.z_mm)
    if any(value is None for value in values):
        return None
    point = np.asarray(values, dtype=np.float64)
    return point if np.all(np.isfinite(point)) else None


def _mean_reprojection_error(
    point: np.ndarray | None,
    observations: Sequence[TipCorrectionObservation],
    projections: Mapping[str, np.ndarray],
) -> float | None:
    if point is None or not observations:
        return None
    errors = []
    for observation in observations:
        projection = projections.get(observation.view_id)
        if projection is None:
            continue
        pixel = _project(projection, point)
        if pixel is None:
            continue
        errors.append(float(np.hypot(
            pixel[0] - observation.x_px,
            pixel[1] - observation.y_px,
        )))
    return float(np.mean(errors)) if errors else None


def _load_skeleton_endpoints(
    artifacts_root: Path,
    model: RoundModelResult | None,
) -> tuple[SkeletonEndpoint, ...]:
    if model is None or not model.skeleton_path:
        return ()
    root = artifacts_root.resolve()
    path = (root / model.skeleton_path).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return ()
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return ()
    endpoints = payload.get("endpoints") if isinstance(payload, dict) else None
    if not isinstance(endpoints, list):
        return ()
    resolved = []
    for item in endpoints:
        if not isinstance(item, dict):
            continue
        try:
            position = np.asarray(item["position_mm"], dtype=np.float64)
            if position.shape != (3,) or not np.all(np.isfinite(position)):
                continue
            resolved.append(SkeletonEndpoint(
                endpoint_id=str(item["endpoint_id"]),
                position_mm=position,
                branch_id=str(item.get("branch_id") or "unknown"),
                path_length_mm=float(item.get("path_length_mm") or 0),
                local_radius_mm=float(item.get("local_radius_mm") or 0),
                local_density=float(item.get("local_density") or 0),
                supporting_point_count=int(
                    item.get("supporting_point_count") or 0
                ),
                main_axis_score=float(item.get("main_axis_score") or 0),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return tuple(resolved)


def _distance_to_plant_model(
    artifacts_root: Path,
    model: RoundModelResult | None,
    point: np.ndarray,
) -> float | None:
    if model is None or not model.plant_point_cloud_path:
        return None
    root = artifacts_root.resolve()
    path = (root / model.plant_point_cloud_path).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    if not path.is_file():
        return None
    distance, _ = point_cloud_support(path, point)
    return distance


def create_tip_correction(
    *,
    correction_id: str,
    operator_id: str,
    created_at: str,
    request: TipCorrectionRequest,
    round_item: AnalysisRound,
    views: Sequence[AnalysisView],
    poses: Sequence[CameraPoseResult],
    intrinsics_snapshot: Mapping[str, Mapping[str, Any]],
    automatic_tip: TipLandmark,
    artifacts_root: Path,
    model_result: RoundModelResult | None = None,
    maximum_reprojection_error_px: float = 5.0,
) -> TipCorrection:
    view_by_id = {item.view_id: item for item in views}
    pose_by_id = {
        item.view_id: item
        for item in poses
        if item.valid and item.rotation_matrix and item.translation_vector_mm
    }
    projections: dict[str, np.ndarray] = {}
    for view_id, pose in pose_by_id.items():
        view = view_by_id.get(view_id)
        intrinsics = (
            intrinsics_snapshot.get(view.camera_id)
            if view is not None
            else None
        )
        if intrinsics is not None:
            projections[view_id] = _projection(pose, intrinsics)

    if request.invalid:
        corrected = automatic_tip.model_copy(
            update={
                "tip_id": f"{automatic_tip.tip_id}:{correction_id}",
                "x_mm": None,
                "y_mm": None,
                "z_mm": None,
                "confidence": 0.0,
                "valid": False,
                "source": "manual",
                "supporting_view_ids": [],
                "visible_view_count": 0,
                "mean_reprojection_error_px": None,
                "maximum_reprojection_error_px": None,
                "distance_to_model_mm": None,
                "distance_to_skeleton_mm": None,
                "temporal_distance_mm": None,
                "detection_type": "invalid",
                "manually_corrected": True,
                "failure_reason": "manual_invalid",
            }
        )
        return TipCorrection(
            correction_id=correction_id,
            analysis_id=round_item.analysis_id,
            round_key=round_item.round_key,
            operator_id=operator_id,
            created_at=created_at,
            reason=request.reason,
            correction_type="invalid",
            invalid=True,
            automatic_tip=automatic_tip,
            corrected_tip=corrected,
            confidence_before=automatic_tip.confidence,
            confidence_after=0.0,
        )

    skeleton_endpoints = _load_skeleton_endpoints(
        artifacts_root,
        model_result,
    )
    if request.corrected_point_mm is not None:
        point = np.asarray(request.corrected_point_mm, dtype=np.float64)
        if point.shape != (3,) or not np.all(np.isfinite(point)):
            raise ValueError("人工三維尖端位置必須是有限的毫米座標。")
        supporting_views = []
        after_error = None
        distance_to_skeleton = (
            min(
                float(np.linalg.norm(point - item.position_mm))
                for item in skeleton_endpoints
            )
            if skeleton_endpoints
            else None
        )
    else:
        correction_views = []
        for observation in request.observations:
            view = view_by_id.get(observation.view_id)
            pose = pose_by_id.get(observation.view_id)
            projection = projections.get(observation.view_id)
            if view is None or pose is None or projection is None:
                raise ValueError(
                    f"視角 {observation.view_id} 沒有可用的相機姿態。"
                )
            correction_views.append(TipCandidateView(
                view_id=view.view_id,
                camera_id=view.camera_id,
                projection_matrix=projection,
                camera_center_world_mm=_camera_center(pose),
                candidates=(TipCandidate2D(
                    candidate_id=f"{correction_id}:{view.view_id}",
                    x_px=observation.x_px,
                    y_px=observation.y_px,
                    confidence=1.0,
                    visibility_confidence=1.0,
                    source="manual",
                ),),
            ))
        hypotheses = triangulate_tip_hypotheses(
            correction_views,
            rejection_threshold_px=maximum_reprojection_error_px,
        )
        if not hypotheses:
            raise ValueError("人工指定的多視角位置無法形成有效三維尖端標記。")
        optimized = optimize_tip_marker(
            hypotheses,
            skeleton_endpoints=skeleton_endpoints,
        )
        point = optimized.position_world_mm
        supporting_views = [
            view_id
            for (view_id, _), used in zip(
                optimized.hypothesis.observations,
                optimized.hypothesis.used_observations,
            )
            if used
        ]
        after_error = _mean_reprojection_error(
            point,
            request.observations,
            projections,
        )
        distance_to_skeleton = optimized.distance_to_skeleton_mm

    projected = []
    for view_id, projection in projections.items():
        pixel = _project(projection, point)
        if pixel is not None:
            projected.append(TipCorrectionObservation(
                view_id=view_id,
                x_px=pixel[0],
                y_px=pixel[1],
            ))
    if request.corrected_point_mm is not None:
        supporting_views = [item.view_id for item in projected]
    distance_to_model = _distance_to_plant_model(
        artifacts_root,
        model_result,
        point,
    )
    reprojection_score = (
        float(np.exp(-after_error / max(maximum_reprojection_error_px, 1.0)))
        if after_error is not None
        else 0.75
    )
    model_score = (
        float(np.exp(-distance_to_model / 15.0))
        if distance_to_model is not None
        else 0.65
    )
    corrected_confidence = float(np.clip(
        0.60 * reprojection_score
        + 0.30 * model_score
        + 0.10,
        0.0,
        1.0,
    ))
    before_error = _mean_reprojection_error(
        _automatic_position(automatic_tip),
        request.observations,
        projections,
    )
    corrected = automatic_tip.model_copy(
        update={
            "tip_id": f"{automatic_tip.tip_id}:{correction_id}",
            "x_mm": float(point[0]),
            "y_mm": float(point[1]),
            "z_mm": float(point[2]),
            "confidence": corrected_confidence,
            "valid": True,
            "source": "manual",
            "supporting_view_ids": supporting_views,
            "visible_view_count": len(supporting_views),
            "mean_reprojection_error_px": after_error,
            "maximum_reprojection_error_px": after_error,
            "distance_to_model_mm": distance_to_model,
            "distance_to_skeleton_mm": distance_to_skeleton,
            "temporal_distance_mm": None,
            "detection_type": "manual",
            "manually_corrected": True,
            "failure_reason": None,
        }
    )
    return TipCorrection(
        correction_id=correction_id,
        analysis_id=round_item.analysis_id,
        round_key=round_item.round_key,
        operator_id=operator_id,
        created_at=created_at,
        reason=request.reason,
        correction_type=(
            "point"
            if request.corrected_point_mm is not None
            else "views"
        ),
        automatic_tip=automatic_tip,
        corrected_tip=corrected,
        supporting_views=supporting_views,
        projected_observations=projected,
        reprojection_before_px=before_error,
        reprojection_after_px=after_error,
        confidence_before=automatic_tip.confidence,
        confidence_after=corrected_confidence,
    )


__all__ = ["create_tip_correction"]
