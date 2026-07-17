from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import cv2
import numpy as np

from .camera_calibration import create_chessboard_object_points


@dataclass(frozen=True, slots=True)
class RotatingRigCalibrationResult:
    axis_origin_mm: np.ndarray
    axis_direction: np.ndarray
    zero_angle_deg: float
    angle_direction: int
    world_from_camera_at_zero: np.ndarray
    residual_mean_px: float
    residual_max_px: float
    samples: tuple[dict[str, Any], ...]


def _camera_pose(
    object_points: np.ndarray,
    image_points: Sequence[Sequence[float]],
    camera_matrix: np.ndarray,
    distortion: np.ndarray,
    projection_model: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    observed = np.asarray(image_points, dtype=np.float64).reshape(-1, 1, 2)
    if projection_model == "fisheye":
        observed = cv2.fisheye.undistortPoints(
            observed,
            camera_matrix,
            distortion,
            P=camera_matrix,
        )
    success, rotation_vector, translation = cv2.solvePnP(
        object_points,
        observed,
        camera_matrix,
        None if projection_model == "fisheye" else distortion,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not success:
        raise ValueError("環繞相機姿態求解失敗。")
    rotation, _ = cv2.Rodrigues(rotation_vector)
    world_from_camera = np.eye(4, dtype=np.float64)
    world_from_camera[:3, :3] = rotation.T
    world_from_camera[:3, 3] = (-rotation.T @ translation).reshape(3)
    return world_from_camera, rotation_vector, translation, rotation


def _fit_axis(camera_positions: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    center = camera_positions.mean(axis=0)
    centered = camera_positions - center
    _, singular_values, right = np.linalg.svd(centered)
    if singular_values[0] <= 1e-9 or singular_values[1] <= 1e-9:
        raise ValueError("環繞校正角度不足以估計旋轉軸。")
    axis = right[-1]
    axis /= np.linalg.norm(axis)
    basis_x = right[0]
    basis_y = np.cross(axis, basis_x)
    coordinates = np.column_stack((centered @ basis_x, centered @ basis_y))
    system = np.column_stack((2.0 * coordinates, np.ones(len(coordinates))))
    target = np.sum(coordinates * coordinates, axis=1)
    solution, *_ = np.linalg.lstsq(system, target, rcond=None)
    circle_center = center + solution[0] * basis_x + solution[1] * basis_y
    return circle_center, axis


def calibrate_rotating_rig_from_points(
    detections: Sequence[dict[str, Any]],
    *,
    camera_matrix: Sequence[Sequence[float]],
    distortion_coefficients: Sequence[float],
    pattern_size: Sequence[int],
    square_size_mm: Sequence[float],
    projection_model: str = "brown_pinhole",
) -> RotatingRigCalibrationResult:
    if projection_model not in {"brown_pinhole", "fisheye"}:
        raise ValueError("環繞投影模型只能是 brown_pinhole 或 fisheye。")
    if len(detections) < 3:
        raise ValueError("環繞幾何校正至少需要三個不同角度的有效影像。")
    intrinsic = np.asarray(camera_matrix, dtype=np.float64)
    distortion = np.asarray(distortion_coefficients, dtype=np.float64)
    object_points = create_chessboard_object_points(
        pattern_size,
        square_size_mm,
    )
    poses = []
    for detection in detections:
        pose, rotation_vector, translation, _ = _camera_pose(
            object_points,
            detection["corners"],
            intrinsic,
            distortion,
            projection_model,
        )
        if projection_model == "fisheye":
            projected, _ = cv2.fisheye.projectPoints(
                object_points.astype(np.float64).reshape(-1, 1, 3),
                rotation_vector,
                translation,
                intrinsic,
                distortion,
            )
        else:
            projected, _ = cv2.projectPoints(
                object_points,
                rotation_vector,
                translation,
                intrinsic,
                distortion,
            )
        observed = np.asarray(detection["corners"], dtype=np.float64).reshape(-1, 2)
        error = np.linalg.norm(projected.reshape(-1, 2) - observed, axis=1)
        poses.append({
            "angle_deg": float(detection["angle_deg"]),
            "image_id": detection.get("image_id"),
            "world_from_camera": pose,
            "observed_error_px": float(np.mean(error)),
        })
    poses.sort(key=lambda item: item["angle_deg"])
    angles = [item["angle_deg"] for item in poses]
    if len(set(angles)) < 3:
        raise ValueError("環繞幾何校正至少需要三個不同角度。")
    positions = np.asarray(
        [item["world_from_camera"][:3, 3] for item in poses],
        dtype=np.float64,
    )
    origin, axis = _fit_axis(positions)
    reference = min(poses, key=lambda item: abs(item["angle_deg"]))
    reference_rotation = reference["world_from_camera"][:3, :3]
    direction_votes = []
    for item in poses:
        delta = item["angle_deg"] - reference["angle_deg"]
        if abs(delta) <= 1e-9:
            continue
        relative = item["world_from_camera"][:3, :3] @ reference_rotation.T
        vector, _ = cv2.Rodrigues(relative)
        direction_votes.append(float(np.dot(vector.reshape(3), axis) / delta))
    angle_direction = 1 if sum(direction_votes) >= 0 else -1
    if angle_direction < 0:
        axis = -axis
        angle_direction = 1
    residuals = np.asarray(
        [item["observed_error_px"] for item in poses],
        dtype=np.float64,
    )
    samples = tuple({
        "image_id": item["image_id"],
        "angle_deg": item["angle_deg"],
        "observed_world_from_camera": (
            item["world_from_camera"].astype(float).tolist()
        ),
        "reprojection_error_px": item["observed_error_px"],
    } for item in poses)
    return RotatingRigCalibrationResult(
        axis_origin_mm=origin,
        axis_direction=axis,
        zero_angle_deg=float(reference["angle_deg"]),
        angle_direction=angle_direction,
        world_from_camera_at_zero=reference["world_from_camera"],
        residual_mean_px=float(np.mean(residuals)),
        residual_max_px=float(np.max(residuals)),
        samples=samples,
    )


__all__ = [
    "RotatingRigCalibrationResult",
    "calibrate_rotating_rig_from_points",
]
