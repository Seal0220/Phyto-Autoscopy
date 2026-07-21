from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import cv2
import numpy as np

from app.analysis.pose_alignment.models import CameraPoseResult


def _value(source: object, name: str, default=None):
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _matrix(pose: CameraPoseResult, name: str) -> np.ndarray:
    value = getattr(pose, name)
    if value is None:
        raise ValueError("姿態矩陣尚未解析。")
    return np.asarray(value, dtype=np.float64).reshape(4, 4)


def _rotation_distance_deg(first: np.ndarray, second: np.ndarray) -> float:
    relative = first.T @ second
    cosine = float(np.clip((np.trace(relative) - 1.0) / 2.0, -1.0, 1.0))
    return math.degrees(math.acos(cosine))


def _average_rotation(rotations: Sequence[np.ndarray]) -> np.ndarray:
    accumulated = np.sum(np.stack(rotations), axis=0)
    left, _, right = np.linalg.svd(accumulated)
    averaged = left @ right
    if np.linalg.det(averaged) < 0:
        left[:, -1] *= -1
        averaged = left @ right
    return averaged


def _robust_pose_indices(matrices: Sequence[np.ndarray]) -> list[int]:
    if len(matrices) <= 2:
        return list(range(len(matrices)))
    centers = np.stack([np.linalg.inv(matrix)[:3, 3] for matrix in matrices])
    center_median = np.median(centers, axis=0)
    center_errors = np.linalg.norm(centers - center_median, axis=1)
    rotation_seed = _average_rotation([matrix[:3, :3] for matrix in matrices])
    rotation_errors = np.asarray(
        [
            _rotation_distance_deg(rotation_seed, matrix[:3, :3])
            for matrix in matrices
        ],
        dtype=np.float64,
    )

    def threshold(values: np.ndarray, floor: float) -> float:
        median = float(np.median(values))
        mad = float(np.median(np.abs(values - median)))
        return median + max(floor, 3.0 * 1.4826 * mad)

    center_limit = threshold(center_errors, 1.0)
    rotation_limit = threshold(rotation_errors, 0.5)
    accepted = [
        index
        for index in range(len(matrices))
        if center_errors[index] <= center_limit
        and rotation_errors[index] <= rotation_limit
    ]
    return accepted or list(range(len(matrices)))


def stable_fixed_camera_pose(
    poses: Sequence[CameraPoseResult],
) -> tuple[np.ndarray | None, dict[str, float]]:
    resolved = [
        pose
        for pose in poses
        if pose.resolved and pose.world_to_camera_matrix is not None
    ]
    if not resolved:
        return None, {}
    matrices = [
        np.asarray(pose.world_to_camera_matrix, dtype=np.float64).reshape(4, 4)
        for pose in resolved
    ]
    accepted_indices = _robust_pose_indices(matrices)
    accepted = [matrices[index] for index in accepted_indices]
    camera_to_world = [np.linalg.inv(matrix) for matrix in accepted]
    rotations = [matrix[:3, :3] for matrix in camera_to_world]
    centers = np.stack([matrix[:3, 3] for matrix in camera_to_world])
    stable_camera_to_world = np.eye(4, dtype=np.float64)
    stable_camera_to_world[:3, :3] = _average_rotation(rotations)
    stable_camera_to_world[:3, 3] = np.median(centers, axis=0)
    center_errors = np.linalg.norm(
        centers - stable_camera_to_world[:3, 3],
        axis=1,
    )
    rotation_errors = np.asarray(
        [
            _rotation_distance_deg(
                stable_camera_to_world[:3, :3],
                rotation,
            )
            for rotation in rotations
        ],
        dtype=np.float64,
    )
    dispersion = {
        "sample_count": float(len(resolved)),
        "accepted_sample_count": float(len(accepted)),
        "translation_median_mm": float(np.median(center_errors)),
        "translation_maximum_mm": float(np.max(center_errors)),
        "rotation_median_deg": float(np.median(rotation_errors)),
        "rotation_maximum_deg": float(np.max(rotation_errors)),
    }
    return np.linalg.inv(stable_camera_to_world), dispersion


def stabilize_fixed_camera_results(
    poses: Sequence[CameraPoseResult],
    stable_world_to_camera: np.ndarray,
) -> list[CameraPoseResult]:
    camera_to_world = np.linalg.inv(stable_world_to_camera)
    stabilized: list[CameraPoseResult] = []
    for pose in poses:
        warnings = list(pose.quality_warnings)
        if not pose.resolved:
            warnings.append("固定相機姿態由同次分析的 ArUco 穩定解補齊。")
        stabilized.append(
            pose.model_copy(
                update={
                    "source": "aruco_refined",
                    "resolved": True,
                    "world_to_camera_matrix": stable_world_to_camera.tolist(),
                    "camera_to_world_matrix": camera_to_world.tolist(),
                    "quality_warnings": warnings,
                    "failure_reason": None,
                }
            )
        )
    return stabilized


def _interpolate_pose(
    first_world_to_camera: np.ndarray,
    second_world_to_camera: np.ndarray,
    alpha: float,
) -> np.ndarray:
    first = np.linalg.inv(first_world_to_camera)
    second = np.linalg.inv(second_world_to_camera)
    relative_rotation = first[:3, :3].T @ second[:3, :3]
    rotation_vector, _ = cv2.Rodrigues(relative_rotation)
    interpolated_delta, _ = cv2.Rodrigues(rotation_vector * float(alpha))
    camera_to_world = np.eye(4, dtype=np.float64)
    camera_to_world[:3, :3] = first[:3, :3] @ interpolated_delta
    camera_to_world[:3, 3] = (
        first[:3, 3] * (1.0 - alpha)
        + second[:3, 3] * alpha
    )
    return np.linalg.inv(camera_to_world)


def _load_gray(path: Path) -> np.ndarray | None:
    try:
        encoded = np.fromfile(path, dtype=np.uint8)
    except OSError:
        return None
    if encoded.size == 0:
        return None
    return cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)


def _scaled_camera_matrix(
    intrinsics: object,
    width: int,
    height: int,
) -> np.ndarray:
    matrix = np.asarray(
        _value(intrinsics, "camera_matrix"),
        dtype=np.float64,
    ).reshape(3, 3)
    scale_x = float(width) / float(_value(intrinsics, "width"))
    scale_y = float(height) / float(_value(intrinsics, "height"))
    scaled = matrix.copy()
    scaled[0, :3] *= scale_x
    scaled[1, :3] *= scale_y
    return scaled


def _undistort_feature_points(
    points: np.ndarray,
    intrinsics: object,
    camera_matrix: np.ndarray,
) -> np.ndarray:
    distortion = np.asarray(
        _value(intrinsics, "distortion_coefficients"),
        dtype=np.float64,
    ).reshape(-1)
    shaped = points.reshape(-1, 1, 2)
    if _value(intrinsics, "camera_model") == "opencv_fisheye":
        return cv2.fisheye.undistortPoints(
            shaped,
            camera_matrix,
            distortion.reshape(4, 1),
            P=camera_matrix,
        ).reshape(-1, 2)
    return cv2.undistortPoints(
        shaped,
        camera_matrix,
        distortion,
        P=camera_matrix,
    ).reshape(-1, 2)


def recover_neighbor_rotation(
    anchor_path: Path,
    target_path: Path,
    intrinsics: object,
    minimum_matches: int,
) -> tuple[np.ndarray | None, int]:
    anchor_image = _load_gray(anchor_path)
    target_image = _load_gray(target_path)
    if anchor_image is None or target_image is None:
        return None, 0
    detector = cv2.ORB_create(nfeatures=2500)
    anchor_points, anchor_descriptors = detector.detectAndCompute(
        anchor_image,
        None,
    )
    target_points, target_descriptors = detector.detectAndCompute(
        target_image,
        None,
    )
    if anchor_descriptors is None or target_descriptors is None:
        return None, 0
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    candidates = matcher.knnMatch(
        anchor_descriptors,
        target_descriptors,
        k=2,
    )
    matches = [
        first
        for pair in candidates
        if len(pair) == 2
        for first, second in [pair]
        if first.distance < 0.75 * second.distance
    ]
    if len(matches) < minimum_matches:
        return None, len(matches)
    anchor_pixels = np.asarray(
        [anchor_points[match.queryIdx].pt for match in matches],
        dtype=np.float64,
    )
    target_pixels = np.asarray(
        [target_points[match.trainIdx].pt for match in matches],
        dtype=np.float64,
    )
    height, width = target_image.shape[:2]
    camera_matrix = _scaled_camera_matrix(intrinsics, width, height)
    try:
        anchor_pixels = _undistort_feature_points(
            anchor_pixels,
            intrinsics,
            camera_matrix,
        )
        target_pixels = _undistort_feature_points(
            target_pixels,
            intrinsics,
            camera_matrix,
        )
        essential, mask = cv2.findEssentialMat(
            anchor_pixels,
            target_pixels,
            camera_matrix,
            method=cv2.RANSAC,
            prob=0.999,
            threshold=1.5,
        )
        if essential is None:
            return None, len(matches)
        inliers, rotation, _, _ = cv2.recoverPose(
            essential,
            anchor_pixels,
            target_pixels,
            camera_matrix,
            mask=mask,
        )
    except cv2.error:
        return None, len(matches)
    if int(inliers) < minimum_matches:
        return None, int(inliers)
    return rotation, int(inliers)


def refine_rotating_results(
    frames: Sequence[object],
    poses: Sequence[CameraPoseResult],
    intrinsics: object,
    minimum_matches: int,
    cancel_check: Callable[[], None] | None = None,
) -> list[CameraPoseResult]:
    """Refine direct rotating-camera poses with neighboring SfM rotation.

    ArUco remains the metric translation and world-frame authority. The
    feature-derived relative rotation only reduces frame-to-frame rotational
    jitter, so monocular SfM is never promoted to an independent scale source.
    """

    result = list(poses)
    previous_index: int | None = None
    for index, pose in enumerate(poses):
        if cancel_check is not None:
            cancel_check()
        if (
            not pose.resolved
            or pose.source != "aruco"
            or pose.world_to_camera_matrix is None
        ):
            continue
        if previous_index is None:
            previous_index = index
            continue
        previous = result[previous_index]
        recovered_rotation, match_count = recover_neighbor_rotation(
            Path(_value(frames[previous_index], "file_path")),
            Path(_value(frames[index], "file_path")),
            intrinsics,
            minimum_matches,
        )
        if recovered_rotation is None:
            previous_index = index
            continue

        previous_matrix = _matrix(previous, "world_to_camera_matrix")
        current_matrix = _matrix(pose, "world_to_camera_matrix")
        sfm_rotation = recovered_rotation @ previous_matrix[:3, :3]
        refined_rotation = _average_rotation(
            [
                current_matrix[:3, :3],
                current_matrix[:3, :3],
                sfm_rotation,
            ]
        )
        refined = current_matrix.copy()
        refined[:3, :3] = refined_rotation
        result[index] = pose.model_copy(
            update={
                "source": "aruco_refined",
                "world_to_camera_matrix": refined.tolist(),
                "camera_to_world_matrix": np.linalg.inv(refined).tolist(),
                "sfm_match_count": match_count,
            }
        )
        previous_index = index
    return result


def fill_rotating_results(
    frames: Sequence[object],
    poses: Sequence[CameraPoseResult],
    intrinsics: object,
    minimum_sfm_matches: int,
    cancel_check: Callable[[], None] | None = None,
) -> list[CameraPoseResult]:
    resolved_indices = [
        index
        for index, pose in enumerate(poses)
        if pose.resolved and pose.world_to_camera_matrix is not None
    ]
    if len(resolved_indices) < 2:
        return list(poses)
    result = list(poses)
    for index, pose in enumerate(poses):
        if cancel_check is not None:
            cancel_check()
        if pose.resolved:
            continue
        previous = [
            anchor_index
            for anchor_index in resolved_indices
            if anchor_index < index
        ]
        following = [
            anchor_index
            for anchor_index in resolved_indices
            if anchor_index > index
        ]
        if not previous or not following:
            continue
        first_index = max(previous)
        second_index = min(following)
        temporal_alpha = (
            float(index - first_index)
            / float(second_index - first_index)
        )
        predicted = _interpolate_pose(
            _matrix(poses[first_index], "world_to_camera_matrix"),
            _matrix(poses[second_index], "world_to_camera_matrix"),
            temporal_alpha,
        )
        nearest_index = (
            first_index
            if abs(index - first_index) <= abs(second_index - index)
            else second_index
        )
        recovered_rotation, match_count = recover_neighbor_rotation(
            Path(_value(frames[nearest_index], "file_path")),
            Path(_value(frames[index], "file_path")),
            intrinsics,
            minimum_sfm_matches,
        )
        warnings = list(pose.quality_warnings)
        if recovered_rotation is not None:
            anchor_world_to_camera = _matrix(
                poses[nearest_index],
                "world_to_camera_matrix",
            )
            predicted[:3, :3] = (
                recovered_rotation @ anchor_world_to_camera[:3, :3]
            )
            source = "sfm"
        else:
            has_motor_prior = all(
                candidate.motor_angle_deg is not None
                for candidate in (
                    pose,
                    poses[first_index],
                    poses[second_index],
                )
            )
            if not has_motor_prior:
                continue
            first_angle = float(poses[first_index].motor_angle_deg)
            second_angle = float(poses[second_index].motor_angle_deg)
            target_angle = float(pose.motor_angle_deg)
            angle_span = second_angle - first_angle
            if abs(angle_span) < 1e-9:
                if abs(target_angle - first_angle) > 1e-6:
                    continue
                motor_alpha = temporal_alpha
            else:
                motor_alpha = (target_angle - first_angle) / angle_span
                if not -0.05 <= motor_alpha <= 1.05:
                    continue
            predicted = _interpolate_pose(
                _matrix(poses[first_index], "world_to_camera_matrix"),
                _matrix(poses[second_index], "world_to_camera_matrix"),
                float(np.clip(motor_alpha, 0.0, 1.0)),
            )
            source = "motor_prior"
            warnings.append(
                "環繞影像特徵不足，使用同次分析的相鄰 ArUco 姿態與馬達角度補齊。"
            )
        camera_to_world = np.linalg.inv(predicted)
        result[index] = pose.model_copy(
            update={
                "source": source,
                "resolved": True,
                "world_to_camera_matrix": predicted.tolist(),
                "camera_to_world_matrix": camera_to_world.tolist(),
                "sfm_match_count": match_count,
                "quality_warnings": warnings,
                "failure_reason": None,
            }
        )
    return result


def pose_sequence_continuity(
    poses: Sequence[CameraPoseResult],
) -> dict[str, float | int | None]:
    resolved = [
        pose
        for pose in poses
        if pose.resolved and pose.camera_to_world_matrix is not None
    ]
    if len(resolved) < 2:
        return {
            "resolved_count": len(resolved),
            "translation_step_median_mm": None,
            "translation_step_maximum_mm": None,
            "rotation_step_median_deg": None,
            "rotation_step_maximum_deg": None,
        }
    matrices = [
        np.asarray(pose.camera_to_world_matrix, dtype=np.float64).reshape(4, 4)
        for pose in resolved
    ]
    translation_steps = np.asarray(
        [
            np.linalg.norm(second[:3, 3] - first[:3, 3])
            for first, second in zip(matrices, matrices[1:])
        ],
        dtype=np.float64,
    )
    rotation_steps = np.asarray(
        [
            _rotation_distance_deg(first[:3, :3], second[:3, :3])
            for first, second in zip(matrices, matrices[1:])
        ],
        dtype=np.float64,
    )
    return {
        "resolved_count": len(resolved),
        "translation_step_median_mm": float(np.median(translation_steps)),
        "translation_step_maximum_mm": float(np.max(translation_steps)),
        "rotation_step_median_deg": float(np.median(rotation_steps)),
        "rotation_step_maximum_deg": float(np.max(rotation_steps)),
    }


def motor_trajectory_consistency(
    poses: Sequence[CameraPoseResult],
) -> dict[str, float | int | None]:
    resolved = [
        pose
        for pose in poses
        if pose.resolved
        and pose.camera_to_world_matrix is not None
        and pose.motor_angle_deg is not None
    ]
    if len(resolved) < 2:
        return {
            "comparable_step_count": 0,
            "rotation_to_motor_delta_median_deg": None,
            "rotation_to_motor_delta_maximum_deg": None,
        }
    errors: list[float] = []
    for first, second in zip(resolved, resolved[1:]):
        first_matrix = np.asarray(
            first.camera_to_world_matrix,
            dtype=np.float64,
        ).reshape(4, 4)
        second_matrix = np.asarray(
            second.camera_to_world_matrix,
            dtype=np.float64,
        ).reshape(4, 4)
        pose_delta = _rotation_distance_deg(
            first_matrix[:3, :3],
            second_matrix[:3, :3],
        )
        motor_delta = abs(
            float(second.motor_angle_deg) - float(first.motor_angle_deg)
        )
        errors.append(abs(pose_delta - motor_delta))
    return {
        "comparable_step_count": len(errors),
        "rotation_to_motor_delta_median_deg": float(np.median(errors)),
        "rotation_to_motor_delta_maximum_deg": float(np.max(errors)),
    }
