from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import cv2
import numpy as np

from app.analysis.pose_alignment.models import (
    CameraPoseResult,
    PoseAlignmentResult,
    PoseQualitySummary,
)
from app.analysis.pose_alignment.pose_estimator import estimate_aruco_pose
from app.analysis.pose_alignment.sfm_refinement import (
    fill_rotating_results,
    motor_trajectory_consistency,
    pose_sequence_continuity,
    refine_rotating_results,
    stabilize_fixed_camera_results,
    stable_fixed_camera_pose,
)


CAMERA_IDS = ("top", "side", "rotating")


def _value(source: object, name: str, default=None):
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _camera_intrinsics(
    intrinsics_by_camera: Mapping[str, object],
    camera_id: str,
) -> object | None:
    return intrinsics_by_camera.get(camera_id)


def _frame_sequence_key(frame: object) -> tuple[str, int]:
    return (
        str(_value(frame, "timestamp", "")),
        int(_value(frame, "capture_id", 0)),
    )


def _unresolved_without_intrinsics(frame: object) -> CameraPoseResult:
    motor_angle = _value(frame, "angle_deg")
    if motor_angle is None:
        motor_angle = _value(frame, "motor_position_deg")
    return CameraPoseResult(
        input_id=int(_value(frame, "capture_id")),
        camera_id=str(_value(frame, "camera_id")),
        relative_path=str(_value(frame, "relative_path")),
        timestamp=_value(frame, "timestamp"),
        motor_angle_deg=motor_angle,
        failure_reason="相機缺少有效內參，無法估算姿態。",
    )


def _fixed_installation_warnings(
    pose: CameraPoseResult,
    parameters: object,
) -> list[str]:
    if pose.camera_to_world_matrix is None:
        return []
    matrix = np.asarray(
        pose.camera_to_world_matrix,
        dtype=np.float64,
    ).reshape(4, 4)
    center = matrix[:3, 3]
    warnings: list[str] = []
    height = _value(parameters, "height_mm")
    if height is not None:
        observed_height = abs(float(center[2]))
        tolerance = max(25.0, abs(float(height)) * 0.05)
        if abs(observed_height - float(height)) > tolerance:
            warnings.append(
                "ArUco 求得高度與安裝參數差異較大："
                f"{observed_height:.1f}/{float(height):.1f} mm。"
            )
    horizontal_distance = _value(
        parameters,
        "horizontal_distance_to_origin_mm",
    )
    if horizontal_distance is not None:
        observed = float(np.linalg.norm(center[:2]))
        tolerance = max(25.0, abs(float(horizontal_distance)) * 0.05)
        if abs(observed - float(horizontal_distance)) > tolerance:
            warnings.append(
                "ArUco 求得至原點水平距離與安裝參數差異較大："
                f"{observed:.1f}/{float(horizontal_distance):.1f} mm。"
            )
    facing_angle = _value(parameters, "facing_origin_angle_deg")
    if facing_angle is not None:
        optical_axis = matrix[:3, 2]
        observed = abs(math.degrees(
            math.atan2(
                -float(optical_axis[2]),
                float(np.linalg.norm(optical_axis[:2])),
            )
        ))
        if abs(observed - abs(float(facing_angle))) > 20.0:
            warnings.append(
                "ArUco 求得朝向角與安裝參數差異較大："
                f"{observed:.1f}/{float(facing_angle):.1f}°。"
            )
    return warnings


def _rotating_installation_warnings(
    pose: CameraPoseResult,
    parameters: object,
) -> list[str]:
    if pose.camera_to_world_matrix is None:
        return []
    matrix = np.asarray(
        pose.camera_to_world_matrix,
        dtype=np.float64,
    ).reshape(4, 4)
    warnings: list[str] = []
    arm_height = _value(parameters, "arm_height_mm")
    if arm_height is not None:
        observed_height = abs(float(matrix[2, 3]))
        tolerance = max(25.0, abs(float(arm_height)) * 0.05)
        if abs(observed_height - float(arm_height)) > tolerance:
            warnings.append(
                "環繞相機高度與安裝參數差異較大："
                f"{observed_height:.1f}/{float(arm_height):.1f} mm。"
            )
    horizontal_distance = _value(
        parameters,
        "horizontal_distance_to_origin_mm",
    )
    if horizontal_distance is not None:
        observed_distance = float(np.linalg.norm(matrix[:2, 3]))
        tolerance = max(
            25.0,
            abs(float(horizontal_distance)) * 0.05,
        )
        if abs(observed_distance - float(horizontal_distance)) > tolerance:
            warnings.append(
                "環繞相機至原點水平距離與安裝參數差異較大："
                f"{observed_distance:.1f}/{float(horizontal_distance):.1f} mm。"
            )
    return warnings


def _append_installation_warnings(
    poses: Sequence[CameraPoseResult],
    camera_parameters: object,
) -> list[CameraPoseResult]:
    updated: list[CameraPoseResult] = []
    for pose in poses:
        parameters = _value(camera_parameters, pose.camera_id)
        warnings = (
            _rotating_installation_warnings(pose, parameters)
            if pose.camera_id == "rotating"
            else _fixed_installation_warnings(pose, parameters)
        )
        if not warnings:
            updated.append(pose)
            continue
        updated.append(
            pose.model_copy(
                update={
                    "quality_warnings": [
                        *pose.quality_warnings,
                        *warnings,
                    ]
                }
            )
        )
    return updated


def _quality_summary(
    poses: Sequence[CameraPoseResult],
    required_camera_ids: Sequence[str],
    fixed_dispersion: dict[str, dict[str, float]],
) -> PoseQualitySummary:
    counts = Counter(pose.source for pose in poses)
    resolved_count = sum(1 for pose in poses if pose.resolved)
    aruco_errors = [
        float(pose.aruco_reprojection_error_px)
        for pose in poses
        if pose.aruco_reprojection_error_px is not None
    ]
    failures = [
        camera_id
        for camera_id in required_camera_ids
        if not any(
            pose.camera_id == camera_id and pose.resolved
            for pose in poses
        )
    ]
    rotating = [pose for pose in poses if pose.camera_id == "rotating"]
    sfm_registered_count = sum(
        1
        for pose in rotating
        if pose.source in {"aruco_refined", "sfm"}
        and pose.sfm_match_count > 0
    )
    sfm_registration_rate = (
        float(sfm_registered_count) / float(len(rotating))
        if rotating
        else 0.0
    )
    if failures or resolved_count == 0:
        status = "failed"
    elif resolved_count < len(poses):
        status = "partial"
    else:
        status = "success"
    return PoseQualitySummary(
        status=status,
        total_image_count=len(poses),
        resolved_image_count=resolved_count,
        unresolved_image_count=len(poses) - resolved_count,
        aruco_image_count=counts["aruco"],
        aruco_refined_image_count=counts["aruco_refined"],
        sfm_image_count=counts["sfm"],
        sfm_registered_image_count=sfm_registered_count,
        motor_prior_image_count=counts["motor_prior"],
        average_aruco_reprojection_error_px=(
            float(np.mean(aruco_errors)) if aruco_errors else None
        ),
        sfm_registration_rate=sfm_registration_rate,
        fixed_camera_dispersion=fixed_dispersion,
        rotating_pose_continuity=pose_sequence_continuity(rotating),
        motor_trajectory_consistency=motor_trajectory_consistency(rotating),
        required_camera_failures=failures,
    )


def _write_debug_overlays(
    frames: Sequence[object],
    poses: Sequence[CameraPoseResult],
    detections: Sequence[dict],
    directory: Path,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    pose_by_input = {
        (pose.camera_id, pose.input_id): pose
        for pose in poses
    }
    detection_by_input = {
        (
            str(detection["camera_id"]),
            int(detection["input_id"]),
        ): detection
        for detection in detections
    }
    for frame in frames:
        camera_id = str(_value(frame, "camera_id"))
        input_id = int(_value(frame, "capture_id"))
        pose = pose_by_input.get((camera_id, input_id))
        if pose is None:
            continue
        detection = detection_by_input.get((camera_id, input_id), {})
        try:
            encoded = np.fromfile(Path(_value(frame, "file_path")), dtype=np.uint8)
        except OSError:
            continue
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image is None:
            continue
        for corners in detection.get("corners_px", []):
            polygon = np.asarray(corners, dtype=np.int32).reshape(-1, 1, 2)
            cv2.polylines(image, [polygon], True, (60, 220, 130), 2)
        color = (60, 220, 130) if pose.resolved else (60, 80, 230)
        cv2.putText(
            image,
            f"{pose.camera_id} {pose.source}",
            (16, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            color,
            2,
            cv2.LINE_AA,
        )
        success, output = cv2.imencode(".jpg", image)
        if success:
            name = f"{pose.camera_id}_{input_id:08d}.jpg"
            (directory / name).write_bytes(output.tobytes())


def align_dataset_camera_poses(
    frames: Sequence[object],
    intrinsics_by_camera: Mapping[str, object],
    settings: object,
    *,
    required_camera_ids: Sequence[str] = ("top", "side"),
    debug_directory: Path | None = None,
    stage_callback: Callable[[str, float], None] | None = None,
    cancel_check: Callable[[], None] | None = None,
) -> PoseAlignmentResult:
    aruco_settings = _value(settings, "aruco_world")
    minimum_pnp_inliers = int(_value(settings, "minimum_pnp_inliers"))
    maximum_error = float(
        _value(settings, "maximum_aruco_reprojection_error_px")
    )
    detections: list[dict] = []
    grouped_frames: dict[str, list[object]] = {camera_id: [] for camera_id in CAMERA_IDS}
    grouped_poses: dict[str, list[CameraPoseResult]] = {
        camera_id: [] for camera_id in CAMERA_IDS
    }
    if stage_callback is not None:
        stage_callback("detecting_aruco", 0.01)
    for frame in frames:
        if cancel_check is not None:
            cancel_check()
        camera_id = str(_value(frame, "camera_id"))
        if camera_id not in grouped_frames:
            continue
        grouped_frames[camera_id].append(frame)
        intrinsics = _camera_intrinsics(intrinsics_by_camera, camera_id)
        if intrinsics is None:
            pose = _unresolved_without_intrinsics(frame)
            detection = {
                "input_id": pose.input_id,
                "camera_id": camera_id,
                "relative_path": pose.relative_path,
                "marker_ids": [],
                "status": "intrinsics_missing",
            }
        else:
            pose, detection = estimate_aruco_pose(
                frame,
                intrinsics,
                aruco_settings,
                minimum_pnp_inliers=minimum_pnp_inliers,
                maximum_reprojection_error_px=maximum_error,
            )
        grouped_poses[camera_id].append(pose)
        detections.append(detection)

    for camera_id in CAMERA_IDS:
        ordered = sorted(
            zip(
                grouped_frames[camera_id],
                grouped_poses[camera_id],
            ),
            key=lambda item: _frame_sequence_key(item[0]),
        )
        grouped_frames[camera_id] = [frame for frame, _ in ordered]
        grouped_poses[camera_id] = [pose for _, pose in ordered]

    if stage_callback is not None:
        stage_callback("estimating_camera_poses", 0.02)
    fixed_camera_poses: dict[str, list[list[float]]] = {}
    fixed_dispersion: dict[str, dict[str, float]] = {}
    for camera_id in ("top", "side"):
        stable_pose, dispersion = stable_fixed_camera_pose(
            grouped_poses[camera_id]
        )
        if stable_pose is None:
            continue
        grouped_poses[camera_id] = stabilize_fixed_camera_results(
            grouped_poses[camera_id],
            stable_pose,
        )
        fixed_camera_poses[camera_id] = stable_pose.tolist()
        fixed_dispersion[camera_id] = dispersion

    rotating_intrinsics = _camera_intrinsics(
        intrinsics_by_camera,
        "rotating",
    )
    if stage_callback is not None:
        stage_callback("refining_camera_poses", 0.04)
    if cancel_check is not None:
        cancel_check()
    if rotating_intrinsics is not None and grouped_poses["rotating"]:
        grouped_poses["rotating"] = refine_rotating_results(
            grouped_frames["rotating"],
            grouped_poses["rotating"],
            rotating_intrinsics,
            int(_value(settings, "minimum_sfm_matches")),
            cancel_check,
        )
        grouped_poses["rotating"] = fill_rotating_results(
            grouped_frames["rotating"],
            grouped_poses["rotating"],
            rotating_intrinsics,
            int(_value(settings, "minimum_sfm_matches")),
            cancel_check,
        )

    poses = [
        pose
        for camera_id in CAMERA_IDS
        for pose in grouped_poses[camera_id]
    ]
    poses = _append_installation_warnings(
        poses,
        _value(settings, "camera_installation_parameters"),
    )
    quality = _quality_summary(
        poses,
        required_camera_ids,
        fixed_dispersion,
    )
    if debug_directory is not None:
        _write_debug_overlays(
            frames,
            poses,
            detections,
            debug_directory,
        )
    return PoseAlignmentResult(
        pose_estimation_version=str(
            _value(settings, "pose_estimation_version")
        ),
        aruco_alignment_status=quality.status,
        camera_poses=poses,
        fixed_camera_poses=fixed_camera_poses,
        quality=quality,
        aruco_detections=detections,
    )
