from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import cv2
import numpy as np

from app.analysis.export.json_export import write_json_atomic
from app.analysis.reconstruction.plant_isolation import (
    PlantIsolationView,
    isolate_plant_point_cloud,
    point_cloud_support,
)
from app.analysis.rounds.paths import (
    round_artifact_directory,
    safe_artifact_name,
)
from app.analysis.tip.candidate_detector import detect_tip_candidates
from app.analysis.tip.candidate_matcher import (
    TipCandidateView,
    triangulate_tip_hypotheses,
)
from app.analysis.tip.marker_optimizer import optimize_tip_marker
from app.analysis.tip.skeleton_extractor import extract_plant_skeleton
from app.models.analysis_models import (
    AnalysisRound,
    AnalysisView,
    CameraPoseResult,
    RoundModelResult,
    TipLandmark,
    TipObservation2D,
)


CancelCheck = Callable[[], None]


@dataclass(frozen=True, slots=True)
class RoundTipAnalysisResult:
    landmark: TipLandmark
    observations: tuple[TipObservation2D, ...]
    model_result: RoundModelResult | None
    warnings: tuple[str, ...]
    quality: dict[str, Any]


def _write_image(path: Path, image: np.ndarray) -> None:
    success, encoded = cv2.imencode(path.suffix or ".png", image)
    if not success:
        raise ValueError(f"尖端分析影像無法編碼：{path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded.tofile(path)


def _projection(
    pose: CameraPoseResult,
    intrinsics: Mapping[str, Any],
) -> tuple[np.ndarray, np.ndarray]:
    rotation = np.asarray(pose.rotation_matrix, dtype=np.float64)
    translation = np.asarray(pose.translation_vector_mm, dtype=np.float64).reshape(3)
    camera_matrix = np.asarray(
        intrinsics["undistorted_camera_matrix"],
        dtype=np.float64,
    )
    if rotation.shape != (3, 3) or camera_matrix.shape != (3, 3):
        raise ValueError("尖端分析的相機姿態或內參格式無效。")
    world_to_camera = np.column_stack((rotation, translation))
    projection = camera_matrix @ world_to_camera
    center = -(rotation.T @ translation)
    return projection, center


def _project_point(
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


def _write_reprojection_overlay(
    image_path: Path,
    output_path: Path,
    candidates,
    selected_ids: set[str],
    projected_point: tuple[float, float] | None,
) -> None:
    encoded = np.fromfile(image_path, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"尖端重投影影像無法解碼：{image_path.name}")
    for candidate in candidates:
        selected = candidate.candidate_id in selected_ids
        color = (80, 220, 120) if selected else (60, 180, 255)
        cv2.circle(
            image,
            (int(round(candidate.x_px)), int(round(candidate.y_px))),
            6 if selected else 4,
            color,
            thickness=2,
            lineType=cv2.LINE_AA,
        )
    if projected_point is not None:
        center = (
            int(round(projected_point[0])),
            int(round(projected_point[1])),
        )
        cv2.drawMarker(
            image,
            center,
            (255, 220, 70),
            markerType=cv2.MARKER_CROSS,
            markerSize=18,
            thickness=2,
            line_type=cv2.LINE_AA,
        )
    _write_image(output_path, image)


def analyze_round_tip(
    *,
    analysis_id: str,
    round_item: AnalysisRound,
    views: Sequence[AnalysisView],
    poses: Sequence[CameraPoseResult],
    intrinsics_snapshot: Mapping[str, Mapping[str, Any]],
    undistortion_manifest: Sequence[Mapping[str, Any]],
    artifacts_root: Path,
    model_result: RoundModelResult | None,
    previous_landmark: TipLandmark | None,
    minimum_confidence: float,
    minimum_supporting_views: int,
    maximum_reprojection_error_px: float,
    use_skeleton_refinement: bool = True,
    use_temporal_prior: bool = True,
    save_reprojection_overlays: bool = True,
    cancel_check: CancelCheck | None = None,
) -> RoundTipAnalysisResult:
    round_root = round_artifact_directory(artifacts_root, round_item.round_key)
    tip_root = round_root / "tip"
    masks_root = round_root / "masks"
    manifest_by_view = {
        str(item.get("view_id")): item
        for item in undistortion_manifest
        if isinstance(item, Mapping)
    }
    pose_by_view = {
        item.view_id: item
        for item in poses
        if item.valid and item.rotation_matrix and item.translation_vector_mm
    }
    candidate_views: list[TipCandidateView] = []
    observation_rows: list[TipObservation2D] = []
    plant_views: list[PlantIsolationView] = []
    candidate_payloads = []
    source_images: dict[str, Path] = {}
    projections: dict[str, np.ndarray] = {}
    warnings: list[str] = []
    for view in views:
        if cancel_check is not None:
            cancel_check()
        pose = pose_by_view.get(view.view_id)
        metadata = manifest_by_view.get(view.view_id)
        intrinsics = intrinsics_snapshot.get(view.camera_id)
        if pose is None or metadata is None or intrinsics is None:
            continue
        image_path = artifacts_root / str(metadata.get("undistorted_path") or "")
        valid_mask_path = artifacts_root / str(
            metadata.get("valid_pixel_mask_path") or ""
        )
        if not image_path.is_file() or not valid_mask_path.is_file():
            warnings.append(f"{view.view_id} 缺少去畸變影像或有效遮罩。")
            continue
        projection, center = _projection(pose, intrinsics)
        source_images[view.view_id] = image_path
        projections[view.view_id] = projection
        detection = detect_tip_candidates(
            image_path,
            valid_mask_path=valid_mask_path,
            candidate_prefix=view.view_id,
        )
        safe_view_id = safe_artifact_name(view.view_id)
        plant_mask_path = masks_root / f"{safe_view_id}.plant.png"
        skeleton_path = masks_root / f"{safe_view_id}.skeleton.png"
        heatmap_path = masks_root / f"{safe_view_id}.tip_heatmap.png"
        _write_image(plant_mask_path, detection.plant_mask)
        _write_image(skeleton_path, detection.skeleton)
        _write_image(heatmap_path, detection.heatmap)
        candidate_view = TipCandidateView(
            view_id=view.view_id,
            camera_id=view.camera_id,
            projection_matrix=projection,
            camera_center_world_mm=center,
            candidates=detection.candidates,
        )
        candidate_views.append(candidate_view)
        plant_views.append(PlantIsolationView(
            view_id=view.view_id,
            projection_matrix=projection,
            plant_mask_path=plant_mask_path,
        ))
        for candidate in detection.candidates:
            observation_rows.append(TipObservation2D(
                analysis_id=analysis_id,
                round_key=round_item.round_key,
                view_id=view.view_id,
                candidate_id=candidate.candidate_id,
                x_px=candidate.x_px,
                y_px=candidate.y_px,
                confidence=candidate.confidence,
                visibility_confidence=candidate.visibility_confidence,
                selected=False,
            ))
        candidate_payloads.append({
            "view_id": view.view_id,
            "camera_id": view.camera_id,
            "plant_mask_path": str(plant_mask_path.relative_to(artifacts_root)),
            "skeleton_path": str(skeleton_path.relative_to(artifacts_root)),
            "heatmap_path": str(heatmap_path.relative_to(artifacts_root)),
            "mask_confidence": detection.mask_confidence,
            "foreground_ratio": detection.foreground_ratio,
            "candidates": [
                {
                    "candidate_id": item.candidate_id,
                    "x_px": item.x_px,
                    "y_px": item.y_px,
                    "confidence": item.confidence,
                    "visibility_confidence": item.visibility_confidence,
                    "source": item.source,
                }
                for item in detection.candidates
            ],
        })
    write_json_atomic(
        tip_root / "candidates_2d.json",
        {
            "coordinate_space": "undistorted_pixels",
            "views": candidate_payloads,
        },
    )
    hypotheses = triangulate_tip_hypotheses(
        candidate_views,
        rejection_threshold_px=maximum_reprojection_error_px,
    )
    write_json_atomic(
        tip_root / "candidates_3d.json",
        [
            {
                "position_world_mm": item.point_world_mm.tolist(),
                "observations": [
                    {
                        "view_id": view_id,
                        "candidate_id": candidate.candidate_id,
                    }
                    for view_id, candidate in item.observations
                ],
                "used_observations": list(item.used_observations),
                "reprojection_errors_px": list(
                    item.reprojection_errors_px
                ),
                "mean_reprojection_error_px": item.mean_error_px,
                "maximum_reprojection_error_px": item.maximum_error_px,
                "angular_spread_deg": item.angular_spread_deg,
                "confidence": item.confidence,
            }
            for item in hypotheses
        ],
    )

    updated_model = model_result
    skeleton = None
    plant_point_cloud_path = None
    if model_result is not None and model_result.point_cloud_path:
        try:
            scene_path = artifacts_root / model_result.point_cloud_path
            plant_path = round_root / "model" / "plant_point_cloud.ply"
            isolation = isolate_plant_point_cloud(
                scene_path,
                plant_path,
                plant_views,
            )
            skeleton = extract_plant_skeleton(
                plant_path,
                round_root / "model" / "skeleton.json",
            )
            updated_model = model_result.model_copy(
                update={
                    "plant_point_cloud_path": str(
                        plant_path.relative_to(artifacts_root)
                    ),
                    "skeleton_path": str(
                        skeleton.path.relative_to(artifacts_root)
                    ),
                    "model_quality": {
                        **model_result.model_quality,
                        "plant_isolation": isolation.quality,
                        "skeleton_node_count": skeleton.node_count,
                        "skeleton_endpoint_count": len(skeleton.endpoints),
                    },
                }
            )
            plant_point_cloud_path = plant_path
        except Exception as error:
            warnings.append(f"植物模型分離或骨架建立失敗：{error}")

    if not hypotheses:
        reprojection_payloads = []
        resolved_observations = tuple(
            item.model_copy(update={"rejection_reason": "not_matched"})
            for item in observation_rows
        )
        write_json_atomic(
            tip_root / "observations_2d.json",
            [item.model_dump(mode="json") for item in resolved_observations],
        )
        if save_reprojection_overlays:
            for candidate_view in candidate_views:
                view_id = candidate_view.view_id
                overlay_path = (
                    tip_root
                    / "reprojections"
                    / f"{safe_artifact_name(view_id)}.jpg"
                )
                _write_reprojection_overlay(
                    source_images[view_id],
                    overlay_path,
                    candidate_view.candidates,
                    set(),
                    None,
                )
                reprojection_payloads.append({
                    "view_id": view_id,
                    "x_px": None,
                    "y_px": None,
                    "overlay_path": str(
                        overlay_path.relative_to(artifacts_root)
                    ),
                })
        landmark = TipLandmark(
            analysis_id=analysis_id,
            round_key=round_item.round_key,
            tip_id=f"{round_item.round_key}:tip",
            record_id=round_item.record_id,
            mode_id=round_item.mode_id,
            round_id=round_item.round_id,
            timestamp=round_item.started_at,
            confidence=0.0,
            valid=False,
            source="invalid",
            detection_type="invalid",
            failure_reason="至少需要兩個具有一致尖端候選的有效視角。",
        )
        write_json_atomic(
            tip_root / "tip_marker.json",
            {
                **landmark.model_dump(mode="json"),
                "quality": {
                    "hypothesis_count": 0,
                    "warnings": warnings,
                },
            },
        )
        write_json_atomic(
            tip_root / "marker_quality.json",
            {
                "hypothesis_count": 0,
                "warnings": warnings,
                "valid": False,
            },
        )
        write_json_atomic(
            tip_root / "reprojection.json",
            reprojection_payloads,
        )
        return RoundTipAnalysisResult(
            landmark=landmark,
            observations=resolved_observations,
            model_result=updated_model,
            warnings=tuple(warnings),
            quality={
                "hypothesis_count": 0,
                "warnings": warnings,
            },
        )

    previous_position = (
        np.asarray(
            [
                previous_landmark.x_mm,
                previous_landmark.y_mm,
                previous_landmark.z_mm,
            ],
            dtype=np.float64,
        )
        if use_temporal_prior
        and previous_landmark is not None
        and previous_landmark.valid
        and None not in (
            previous_landmark.x_mm,
            previous_landmark.y_mm,
            previous_landmark.z_mm,
        )
        else None
    )
    optimized = optimize_tip_marker(
        hypotheses,
        skeleton_endpoints=(
            skeleton.endpoints
            if use_skeleton_refinement and skeleton is not None
            else ()
        ),
        previous_position_mm=previous_position,
    )
    selected_ids = {
        candidate.candidate_id
        for (_, candidate), used in zip(
            optimized.hypothesis.observations,
            optimized.hypothesis.used_observations,
        )
        if used
    }
    hypothesis_ids = {
        candidate.candidate_id
        for _, candidate in optimized.hypothesis.observations
    }
    resolved_observations = tuple(
        item.model_copy(
            update={
                "selected": item.candidate_id in selected_ids,
                "rejection_reason": (
                    None
                    if item.candidate_id in selected_ids
                    else "reprojection_outlier"
                    if item.candidate_id in hypothesis_ids
                    else "not_selected"
                ),
            }
        )
        for item in observation_rows
    )
    write_json_atomic(
        tip_root / "observations_2d.json",
        [item.model_dump(mode="json") for item in resolved_observations],
    )
    supporting_count = len(selected_ids)
    selected_view_ids = [
        view_id
        for (view_id, _), used in zip(
            optimized.hypothesis.observations,
            optimized.hypothesis.used_observations,
        )
        if used
    ]
    pose_errors = []
    for view_id in selected_view_ids:
        pose = pose_by_view.get(view_id)
        if pose is None:
            continue
        error = (
            pose.refinement_reprojection_error_px
            if pose.refinement_reprojection_error_px is not None
            else pose.aruco_reprojection_error_px
        )
        if error is not None and np.isfinite(error):
            pose_errors.append(float(error))
    pose_score = (
        float(np.exp(-np.mean(pose_errors) / 5.0))
        if pose_errors
        else 0.7
    )
    point = optimized.position_world_mm
    distance_to_model, local_model_support = (
        point_cloud_support(plant_point_cloud_path, point)
        if plant_point_cloud_path is not None
        else (None, 0)
    )
    model_score = (
        float(np.exp(-distance_to_model / 8.0))
        if distance_to_model is not None
        else 0.7
    )
    confidence = float(np.clip(
        0.78 * optimized.confidence
        + 0.12 * pose_score
        + 0.10 * model_score,
        0,
        1,
    ))
    valid = (
        confidence >= minimum_confidence
        and supporting_count >= minimum_supporting_views
        and optimized.hypothesis.maximum_error_px
        <= maximum_reprojection_error_px
    )
    reprojection_payloads = []
    if save_reprojection_overlays:
        selected_by_view = {
            view_id: candidate.candidate_id
            for (view_id, candidate), used in zip(
                optimized.hypothesis.observations,
                optimized.hypothesis.used_observations,
            )
            if used
        }
        candidate_by_view = {
            item.view_id: item.candidates
            for item in candidate_views
        }
        for view_id, projection in projections.items():
            projected = _project_point(projection, point)
            safe_view_id = safe_artifact_name(view_id)
            overlay_path = (
                tip_root
                / "reprojections"
                / f"{safe_view_id}.jpg"
            )
            _write_reprojection_overlay(
                source_images[view_id],
                overlay_path,
                candidate_by_view.get(view_id, ()),
                {selected_by_view[view_id]}
                if view_id in selected_by_view
                else set(),
                projected,
            )
            reprojection_payloads.append({
                "view_id": view_id,
                "x_px": projected[0] if projected is not None else None,
                "y_px": projected[1] if projected is not None else None,
                "overlay_path": str(
                    overlay_path.relative_to(artifacts_root)
                ),
            })
    landmark = TipLandmark(
        analysis_id=analysis_id,
        round_key=round_item.round_key,
        tip_id=f"{round_item.round_key}:tip",
        record_id=round_item.record_id,
        mode_id=round_item.mode_id,
        round_id=round_item.round_id,
        timestamp=round_item.started_at,
        x_mm=float(point[0]),
        y_mm=float(point[1]),
        z_mm=float(point[2]),
        confidence=confidence,
        valid=valid,
        source=optimized.source,
        supporting_view_ids=selected_view_ids,
        visible_view_count=supporting_count,
        mean_reprojection_error_px=optimized.hypothesis.mean_error_px,
        maximum_reprojection_error_px=optimized.hypothesis.maximum_error_px,
        distance_to_model_mm=distance_to_model,
        distance_to_skeleton_mm=optimized.distance_to_skeleton_mm,
        temporal_distance_mm=optimized.temporal_distance_mm,
        detection_type="measured" if valid else "invalid",
        failure_reason=(
            None
            if valid
            else "尖端標記信心、支持視角或重投影品質未達門檻。"
        ),
    )
    quality = {
        **optimized.quality,
        "hypothesis_count": len(hypotheses),
        "mean_reprojection_error_px": optimized.hypothesis.mean_error_px,
        "maximum_reprojection_error_px": optimized.hypothesis.maximum_error_px,
        "confidence": confidence,
        "pose_quality_score": pose_score,
        "model_surface_score": model_score,
        "local_model_supporting_point_count": local_model_support,
        "valid": valid,
        "reprojections": reprojection_payloads,
        "warnings": warnings,
    }
    write_json_atomic(
        tip_root / "tip_marker.json",
        {
            **landmark.model_dump(mode="json"),
            "quality": quality,
        },
    )
    write_json_atomic(
        tip_root / "marker_quality.json",
        quality,
    )
    write_json_atomic(
        tip_root / "reprojection.json",
        reprojection_payloads,
    )
    return RoundTipAnalysisResult(
        landmark=landmark,
        observations=resolved_observations,
        model_result=updated_model,
        warnings=tuple(warnings),
        quality=quality,
    )


__all__ = ["RoundTipAnalysisResult", "analyze_round_tip"]
