from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import cv2
import numpy as np

from app.analysis.image_probe import read_analysis_image

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
StageCallback = Callable[[str, float], None]
TIP_ANALYSIS_VERSION = 6


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


def _used_reprojection_errors(
    point: np.ndarray,
    observations: Sequence[tuple[str, Any]],
    used_observations: Sequence[bool],
    projections: Mapping[str, np.ndarray],
) -> tuple[float, ...]:
    errors = []
    for (view_id, candidate), used in zip(observations, used_observations):
        if not used:
            continue
        projection = projections.get(view_id)
        pixel = _project_point(projection, point) if projection is not None else None
        errors.append(
            float(np.hypot(pixel[0] - candidate.x_px, pixel[1] - candidate.y_px))
            if pixel is not None
            else float("inf")
        )
    return tuple(errors)


def _point_on_plant_mask(mask_path: Path, pixel, tolerance_px: float) -> bool:
    if pixel is None or not np.isfinite(pixel).all():
        return False
    mask = read_analysis_image(mask_path, cv2.IMREAD_GRAYSCALE)
    if mask is None:
        return False
    x, y = pixel
    if not (0 <= x < mask.shape[1] and 0 <= y < mask.shape[0]):
        return False
    radius = int(np.ceil(tolerance_px))
    left, top = max(0, int(np.floor(x)) - radius), max(0, int(np.floor(y)) - radius)
    right, bottom = min(mask.shape[1], int(np.ceil(x)) + radius + 1), min(mask.shape[0], int(np.ceil(y)) + radius + 1)
    rows, columns = np.nonzero(mask[top:bottom, left:right])
    return bool(np.any((columns + left - x) ** 2 + (rows + top - y) ** 2 <= tolerance_px ** 2))


def _write_reprojection_overlay(
    image_path: Path,
    output_path: Path,
    candidates,
    selected_ids: set[str],
    projected_point: tuple[float, float] | None,
    *,
    confirmed: bool = False,
) -> None:
    image = read_analysis_image(image_path, cv2.IMREAD_COLOR)
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
            (6, 16, 12),
            markerType=cv2.MARKER_CROSS,
            markerSize=32,
            thickness=6,
            line_type=cv2.LINE_AA,
        )
        color = (120, 230, 70) if confirmed else (70, 190, 255)
        cv2.drawMarker(image, center, color, markerType=cv2.MARKER_CROSS, markerSize=32,
                       thickness=2, line_type=cv2.LINE_AA)
        label = "TIP - CONFIRMED" if confirmed else "TIP CANDIDATE - REVIEW"
        label_position = (max(4, min(center[0] + 22, image.shape[1] - 260)), max(24, min(center[1] - 18, image.shape[0] - 8)))
        cv2.putText(image, label, label_position, cv2.FONT_HERSHEY_SIMPLEX, .6, (6, 16, 12), 5, cv2.LINE_AA)
        cv2.putText(image, label, label_position, cv2.FONT_HERSHEY_SIMPLEX, .6, color, 1, cv2.LINE_AA)
    _write_image(output_path, image)


def _candidate_artifact_payloads(
    payloads: Sequence[Mapping[str, Any]],
    selected_ids: set[str],
    *,
    export_all: bool,
) -> list[dict[str, Any]]:
    result = []
    for payload in payloads:
        candidates = [
            dict(candidate)
            for candidate in payload.get("candidates", [])
            if (
                export_all
                or candidate.get("candidate_id") in selected_ids
            )
        ]
        result.append({
            **dict(payload),
            "candidates": candidates,
        })
    return result


def _remove_temporary_paths(paths: Sequence[Path]) -> None:
    parents = set()
    for path in paths:
        parents.add(path.parent)
        path.unlink(missing_ok=True)
    for parent in sorted(
        parents,
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        try:
            parent.rmdir()
        except OSError:
            pass


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
    export_all_2d_candidates: bool = False,
    export_scene_point_cloud: bool = True,
    export_plant_point_cloud: bool = True,
    export_background_point_cloud: bool = False,
    export_skeleton: bool = True,
    export_tip_marker: bool = True,
    save_reprojection_overlays: bool = True,
    save_diagnostics: bool = True,
    cancel_check: CancelCheck | None = None,
    stage_callback: StageCallback | None = None,
    view_callback: Callable[[AnalysisView], None] | None = None,
    tracked_candidates: Mapping[str, Any] | None = None,
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
    temporary_paths: list[Path] = []
    if not save_diagnostics:
        shutil.rmtree(masks_root, ignore_errors=True)
    if not save_reprojection_overlays:
        shutil.rmtree(
            tip_root / "reprojections",
            ignore_errors=True,
        )
    if stage_callback is not None:
        stage_callback("detecting_tip_candidates", 0.0)
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
        if view_callback is not None:
            view_callback(view)
        detection = detect_tip_candidates(
            image_path,
            valid_mask_path=valid_mask_path,
            candidate_prefix=view.view_id,
            checkpoint_root=artifacts_root,
        )
        if tracked_candidates is not None:
            from dataclasses import replace
            tracked = tracked_candidates.get(view.view_id)
            detection = replace(detection, candidates=(tracked,) if tracked is not None else ())
        safe_view_id = safe_artifact_name(view.view_id)
        mask_output_root = (
            masks_root
            if save_diagnostics
            else round_root / "temporary" / "tip_masks"
        )
        plant_mask_path = (
            mask_output_root / f"{safe_view_id}.plant.png"
        )
        skeleton_path = masks_root / f"{safe_view_id}.skeleton.png"
        heatmap_path = masks_root / f"{safe_view_id}.tip_heatmap.png"
        _write_image(plant_mask_path, detection.plant_mask)
        if save_diagnostics:
            _write_image(skeleton_path, detection.skeleton)
            _write_image(heatmap_path, detection.heatmap)
        else:
            temporary_paths.append(plant_mask_path)
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
            "plant_mask_path": (
                str(plant_mask_path.relative_to(artifacts_root))
                if save_diagnostics
                else None
            ),
            "skeleton_path": (
                str(skeleton_path.relative_to(artifacts_root))
                if save_diagnostics
                else None
            ),
            "heatmap_path": (
                str(heatmap_path.relative_to(artifacts_root))
                if save_diagnostics
                else None
            ),
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
    if stage_callback is not None:
        stage_callback("triangulating_tip_marker", 0.30)
    hypotheses = triangulate_tip_hypotheses(
        candidate_views,
        rejection_threshold_px=maximum_reprojection_error_px,
    )
    candidates_3d_path = tip_root / "candidates_3d.json"
    if save_diagnostics:
        write_json_atomic(
            candidates_3d_path,
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
    else:
        candidates_3d_path.unlink(missing_ok=True)

    updated_model = model_result
    skeleton = None
    plant_point_cloud_path = None
    immutable_reference = model_result is not None and (
        model_result.model_quality.get("immutable_reference") or model_result.model_quality.get("reference_only"))
    if model_result is not None and model_result.point_cloud_path and not immutable_reference:
        scene_path = artifacts_root / model_result.point_cloud_path
        plant_path = (
            round_root / "model" / "plant_point_cloud.ply"
            if export_plant_point_cloud
            else round_root / "temporary" / "plant_point_cloud.ply"
        )
        background_path = (
            round_root / "model" / "background_point_cloud.ply"
            if export_background_point_cloud
            else None
        )
        if not export_plant_point_cloud:
            temporary_paths.append(plant_path)
        try:
            if stage_callback is not None:
                stage_callback("isolating_plant_model", 0.40)
            isolation = isolate_plant_point_cloud(
                scene_path,
                plant_path,
                plant_views,
                background_output_path=background_path,
            )
            plant_point_cloud_path = plant_path
            updated_model = model_result.model_copy(
                update={
                    "plant_point_cloud_path": (
                        str(plant_path.relative_to(artifacts_root))
                        if export_plant_point_cloud
                        else None
                    ),
                    "background_point_cloud_path": (
                        str(
                            isolation.background_output_path.relative_to(
                                artifacts_root
                            )
                        )
                        if isolation.background_output_path is not None
                        else None
                    ),
                    "model_quality": {
                        **model_result.model_quality,
                        "plant_isolation": isolation.quality,
                    },
                }
            )
        except Exception as error:
            reason = f"植物模型分離失敗：{error}"
            warnings.append(reason)
            postprocessing_required = any((
                export_plant_point_cloud,
                export_background_point_cloud,
                export_skeleton,
            ))
            updated_model = model_result.model_copy(
                update={
                    "status": (
                        "postprocessing_failed"
                        if postprocessing_required
                        else model_result.status
                    ),
                    "model_quality": {
                        **model_result.model_quality,
                        "plant_isolation": {
                            "status": "failed",
                            "failure_reason": str(error),
                        },
                    },
                    "failure_reason": (
                        reason
                        if postprocessing_required
                        else model_result.failure_reason
                    ),
                }
            )

        if plant_point_cloud_path is not None:
            skeleton_path = (
                round_root / "model" / "skeleton.json"
                if export_skeleton
                else round_root / "temporary" / "skeleton.json"
            )
            if not export_skeleton:
                temporary_paths.append(skeleton_path)
            try:
                if stage_callback is not None:
                    stage_callback("extracting_model_skeleton", 0.52)
                skeleton = extract_plant_skeleton(
                    plant_path,
                    skeleton_path,
                )
                updated_model = updated_model.model_copy(
                    update={
                        "skeleton_path": (
                            str(
                                skeleton.path.relative_to(
                                    artifacts_root
                                )
                            )
                            if export_skeleton
                            else None
                        ),
                        "model_quality": {
                            **updated_model.model_quality,
                            "skeleton_node_count": skeleton.node_count,
                            "skeleton_endpoint_count": len(
                                skeleton.endpoints
                            ),
                        },
                    }
                )
            except Exception as error:
                reason = f"植物骨架建立失敗：{error}"
                warnings.append(reason)
                updated_model = updated_model.model_copy(
                    update={
                        "status": (
                            "postprocessing_failed"
                            if export_skeleton
                            else updated_model.status
                        ),
                        "model_quality": {
                            **updated_model.model_quality,
                            "skeleton": {
                                "status": "failed",
                                "failure_reason": str(error),
                            },
                        },
                        "failure_reason": (
                            reason
                            if export_skeleton
                            else updated_model.failure_reason
                        ),
                    }
                )
        if not export_scene_point_cloud:
            scene_path.unlink(missing_ok=True)
            updated_model = updated_model.model_copy(
                update={"point_cloud_path": None}
            )

    if not hypotheses:
        if stage_callback is not None:
            stage_callback("refining_tip_marker", 0.72)
        reprojection_payloads = []
        resolved_observations = tuple(
            item.model_copy(update={"rejection_reason": "not_matched"})
            for item in observation_rows
        )
        write_json_atomic(
            tip_root / "candidates_2d.json",
            {
                "coordinate_space": "undistorted_pixels",
                "views": _candidate_artifact_payloads(
                    candidate_payloads,
                    set(),
                    export_all=export_all_2d_candidates,
                ),
            },
        )
        write_json_atomic(
            tip_root / "observations_2d.json",
            [
                item.model_dump(mode="json")
                for item in resolved_observations
                if export_all_2d_candidates
            ],
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
        tip_marker_path = tip_root / "tip_marker.json"
        if export_tip_marker:
            write_json_atomic(
                tip_marker_path,
                {
                    **landmark.model_dump(mode="json"),
                    "quality": {
                        "hypothesis_count": 0,
                        "warnings": warnings,
                    },
                },
            )
        else:
            tip_marker_path.unlink(missing_ok=True)
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
        _remove_temporary_paths(temporary_paths)
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
    if stage_callback is not None:
        stage_callback("refining_tip_marker", 0.72)
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
        tip_root / "candidates_2d.json",
        {
            "coordinate_space": "undistorted_pixels",
            "views": _candidate_artifact_payloads(
                candidate_payloads,
                selected_ids,
                export_all=export_all_2d_candidates,
            ),
        },
    )
    write_json_atomic(
        tip_root / "observations_2d.json",
        [
            item.model_dump(mode="json")
            for item in resolved_observations
            if export_all_2d_candidates or item.selected
        ],
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
    reprojection_errors = _used_reprojection_errors(
        point,
        optimized.hypothesis.observations,
        optimized.hypothesis.used_observations,
        projections,
    )
    reprojection_exceeds_limit = (
        not reprojection_errors
        or not np.isfinite(reprojection_errors).all()
        or max(reprojection_errors) > maximum_reprojection_error_px
    )
    refinement_rejected = reprojection_exceeds_limit and not np.array_equal(
        point, optimized.hypothesis.point_world_mm
    )
    if refinement_rejected:
        point = optimized.hypothesis.point_world_mm.copy()
        reprojection_errors = _used_reprojection_errors(
            point,
            optimized.hypothesis.observations,
            optimized.hypothesis.used_observations,
            projections,
        )
        warnings.append("骨架微調超過重投影門檻，已保留雙鏡頭／多視角三角定位結果。")
    actual_mean_error = (
        float(np.mean(reprojection_errors))
        if reprojection_errors and np.isfinite(reprojection_errors).all()
        else None
    )
    actual_maximum_error = (
        float(max(reprojection_errors))
        if reprojection_errors and np.isfinite(reprojection_errors).all()
        else None
    )
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
    reprojection_score = (
        float(np.exp(-actual_mean_error / max(maximum_reprojection_error_px, 1.0)))
        if actual_mean_error is not None
        else 0.0
    )
    confidence = float(np.clip(
        0.68 * optimized.confidence
        + 0.10 * reprojection_score
        + 0.12 * pose_score
        + 0.10 * model_score,
        0,
        1,
    ))
    plant_masks = {view.view_id: view.plant_mask_path for view in plant_views}
    foreground_support = [view_id for view_id in selected_view_ids
                          if _point_on_plant_mask(plant_masks[view_id], _project_point(projections[view_id], point),
                                                  maximum_reprojection_error_px)]
    supporting_cameras = {view.camera_id for view in candidate_views if view.view_id in selected_view_ids}
    geometric_valid = (
        confidence >= minimum_confidence
        and supporting_count >= minimum_supporting_views
        and len(supporting_cameras) >= 2
        and len(foreground_support) >= minimum_supporting_views
        and actual_maximum_error is not None
        and actual_maximum_error <= maximum_reprojection_error_px
    )
    # This detector supplies contour/skeleton endpoints, including leaf edges.
    # Consistent geometry cannot establish which endpoint is the growing apex.
    # Preserve the proposal for review; only an apex-aware detector may confirm it.
    identity_confirmed = all(candidate.source == "shoot_apex"
                             for (_, candidate), used in zip(optimized.hypothesis.observations,
                                                           optimized.hypothesis.used_observations) if used)
    valid = geometric_valid and identity_confirmed
    reprojection_payloads = []
    if save_reprojection_overlays:
        if stage_callback is not None:
            stage_callback("calculating_quality_metrics", 0.86)
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
                confirmed=valid,
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
        source=(
            optimized.source
            if not refinement_rejected
            else "multiview_joint"
            if supporting_count > 2
            else "fixed_triangulation"
        ),
        supporting_view_ids=selected_view_ids,
        visible_view_count=supporting_count,
        mean_reprojection_error_px=actual_mean_error,
        maximum_reprojection_error_px=actual_maximum_error,
        distance_to_model_mm=distance_to_model,
        distance_to_skeleton_mm=optimized.distance_to_skeleton_mm,
        temporal_distance_mm=optimized.temporal_distance_mm,
        detection_type="measured" if valid else "invalid",
        failure_reason=(
            None
            if valid
            else "候選點尚未確認為生長尖端，請在本輪人工標記尖端。"
            if geometric_valid and not identity_confirmed
            else "尖端標記信心、植物範圍、支持視角或重投影品質未達門檻。"
        ),
    )
    quality = {
        **optimized.quality,
        **optimized.hypothesis.aggregation_quality,
        "round_input_camera_counts": {camera: sum(view.camera_id == camera for view in candidate_views)
                                      for camera in ("top", "side", "rotating")},
        "hypothesis_count": len(hypotheses),
        "foreground_supporting_view_ids": foreground_support,
        "foreground_supporting_view_count": len(foreground_support),
        "mean_reprojection_error_px": actual_mean_error,
        "maximum_reprojection_error_px": actual_maximum_error,
        "triangulation_mean_reprojection_error_px": (
            optimized.hypothesis.mean_error_px
        ),
        "skeleton_refinement_rejected": refinement_rejected,
        "confidence": confidence,
        "final_reprojection_score": reprojection_score,
        "pose_quality_score": pose_score,
        "model_surface_score": model_score,
        "local_model_supporting_point_count": local_model_support,
        "valid": valid,
        "geometric_valid": geometric_valid,
        "tip_identity_confirmed": identity_confirmed,
        "model_used_for_tip_refinement": not immutable_reference and skeleton is not None,
        "reprojections": reprojection_payloads,
        "warnings": warnings,
    }
    tip_marker_path = tip_root / "tip_marker.json"
    if export_tip_marker:
        write_json_atomic(
            tip_marker_path,
            {
                **landmark.model_dump(mode="json"),
                "quality": quality,
            },
        )
    else:
        tip_marker_path.unlink(missing_ok=True)
    write_json_atomic(
        tip_root / "marker_quality.json",
        quality,
    )
    write_json_atomic(
        tip_root / "reprojection.json",
        reprojection_payloads,
    )
    _remove_temporary_paths(temporary_paths)
    if stage_callback is not None:
        stage_callback("exporting", 1.0)
    return RoundTipAnalysisResult(
        landmark=landmark,
        observations=resolved_observations,
        model_result=updated_model,
        warnings=tuple(warnings),
        quality=quality,
    )


__all__ = ["RoundTipAnalysisResult", "TIP_ANALYSIS_VERSION", "analyze_round_tip"]
