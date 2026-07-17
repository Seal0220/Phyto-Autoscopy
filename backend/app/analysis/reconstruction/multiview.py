from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians, sin
from typing import Any, Sequence

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class MultiviewResult:
    point: np.ndarray
    reprojection_errors_px: tuple[float, ...]
    used_observations: tuple[bool, ...]


def _normalized_axis(axis: Sequence[float]) -> np.ndarray:
    value = np.asarray(axis, dtype=np.float64).reshape(3)
    length = float(np.linalg.norm(value))
    if not np.isfinite(value).all() or length <= 1e-12:
        raise ValueError("旋轉軸方向必須是有效的三維向量。")
    return value / length


def axis_rotation_matrix(
    axis: Sequence[float],
    angle_deg: float,
) -> np.ndarray:
    direction = _normalized_axis(axis)
    x, y, z = direction
    angle = radians(float(angle_deg))
    c = cos(angle)
    s = sin(angle)
    one_minus_c = 1.0 - c
    return np.asarray([
        [
            c + x * x * one_minus_c,
            x * y * one_minus_c - z * s,
            x * z * one_minus_c + y * s,
        ],
        [
            y * x * one_minus_c + z * s,
            c + y * y * one_minus_c,
            y * z * one_minus_c - x * s,
        ],
        [
            z * x * one_minus_c - y * s,
            z * y * one_minus_c + x * s,
            c + z * z * one_minus_c,
        ],
    ], dtype=np.float64)


def rotating_world_to_camera(
    profile: Any,
    angle_deg: float,
) -> np.ndarray:
    origin = np.asarray(profile.rotating_axis_origin_mm, dtype=np.float64).reshape(3)
    zero_pose = np.asarray(
        profile.rotating_axis_from_camera_matrix,
        dtype=np.float64,
    )
    if zero_pose.shape != (4, 4) or not np.isfinite(zero_pose).all():
        raise ValueError("環繞相機零度姿態必須是有限的 4×4 矩陣。")
    direction = int(profile.rotating_angle_direction or 0)
    if direction not in {-1, 1}:
        raise ValueError("環繞相機角度方向必須是 -1 或 1。")
    delta = direction * (float(angle_deg) - float(profile.rotating_zero_angle_deg))
    rotation = axis_rotation_matrix(profile.rotating_axis_direction, delta)
    zero_rotation = zero_pose[:3, :3]
    zero_position = zero_pose[:3, 3]
    world_from_camera = np.eye(4, dtype=np.float64)
    world_from_camera[:3, :3] = rotation @ zero_rotation
    world_from_camera[:3, 3] = origin + rotation @ (zero_position - origin)
    return np.linalg.inv(world_from_camera)


def rotating_projection_matrix(
    profile: Any,
    angle_deg: float,
) -> np.ndarray:
    intrinsic = np.asarray(profile.rotating_camera_matrix, dtype=np.float64)
    if intrinsic.shape != (3, 3) or not np.isfinite(intrinsic).all():
        raise ValueError("環繞相機內參矩陣無效。")
    return intrinsic @ rotating_world_to_camera(profile, angle_deg)[:3]


def project_rotating_point(
    profile: Any,
    angle_deg: float,
    world_point: Sequence[float],
) -> tuple[float, float]:
    world_to_camera = rotating_world_to_camera(profile, angle_deg)
    rotation_vector, _ = cv2.Rodrigues(world_to_camera[:3, :3])
    arguments = (
        np.asarray(world_point, dtype=np.float64).reshape(1, 1, 3),
        rotation_vector,
        world_to_camera[:3, 3].reshape(3, 1),
        np.asarray(profile.rotating_camera_matrix, dtype=np.float64),
        np.asarray(profile.rotating_distortion_coefficients, dtype=np.float64),
    )
    if profile.camera_projection_models.get("rotating") == "fisheye":
        projected, _ = cv2.fisheye.projectPoints(*arguments)
    else:
        projected, _ = cv2.projectPoints(*arguments)
    x, y = projected.reshape(2)
    return float(x), float(y)


def undistort_rotating_point(
    profile: Any,
    point: Sequence[float],
) -> tuple[float, float]:
    arguments = (
        np.asarray(point, dtype=np.float64).reshape(1, 1, 2),
        np.asarray(profile.rotating_camera_matrix, dtype=np.float64),
        np.asarray(profile.rotating_distortion_coefficients, dtype=np.float64),
    )
    projection = np.asarray(
        profile.rotating_camera_matrix,
        dtype=np.float64,
    )
    if profile.camera_projection_models.get("rotating") == "fisheye":
        normalized = cv2.fisheye.undistortPoints(
            *arguments,
            P=projection,
        )
    else:
        normalized = cv2.undistortPoints(
            *arguments,
            P=projection,
        )
    x, y = normalized.reshape(2)
    return float(x), float(y)


def _triangulate(
    projections: Sequence[np.ndarray],
    observations: Sequence[Sequence[float]],
    weights: Sequence[float],
) -> np.ndarray:
    rows = []
    for projection, observation, weight in zip(
        projections,
        observations,
        weights,
    ):
        matrix = np.asarray(projection, dtype=np.float64)
        x, y = (float(value) for value in observation)
        scale = max(float(weight), 1e-9) ** 0.5
        rows.extend((
            scale * (x * matrix[2] - matrix[0]),
            scale * (y * matrix[2] - matrix[1]),
        ))
    _, _, right = np.linalg.svd(np.asarray(rows, dtype=np.float64))
    homogeneous = right[-1]
    if abs(homogeneous[3]) <= 1e-12:
        raise ValueError("多視角三角化得到無限遠點。")
    point = homogeneous[:3] / homogeneous[3]
    if not np.isfinite(point).all():
        raise ValueError("多視角三角化得到無效座標。")
    return point


def _errors(
    point: np.ndarray,
    projections: Sequence[np.ndarray],
    observations: Sequence[Sequence[float]],
) -> np.ndarray:
    homogeneous = np.append(point, 1.0)
    values = []
    for projection, observation in zip(projections, observations):
        projected = np.asarray(projection, dtype=np.float64) @ homogeneous
        if abs(projected[2]) <= 1e-12:
            values.append(float("inf"))
            continue
        pixel = projected[:2] / projected[2]
        values.append(
            float(np.linalg.norm(pixel - np.asarray(observation, dtype=np.float64)))
        )
    return np.asarray(values, dtype=np.float64)


def robust_multiview_triangulate(
    projections: Sequence[np.ndarray],
    observations: Sequence[Sequence[float]],
    *,
    confidence: Sequence[float] | None = None,
    rejection_threshold_px: float = 8.0,
) -> MultiviewResult:
    if len(projections) != len(observations) or len(projections) < 2:
        raise ValueError("多視角三角化至少需要兩組相同數量的投影與觀測。")
    weights = np.asarray(
        confidence if confidence is not None else np.ones(len(projections)),
        dtype=np.float64,
    )
    if weights.shape != (len(projections),) or not np.isfinite(weights).all():
        raise ValueError("多視角觀測信心格式無效。")
    used = np.ones(len(projections), dtype=bool)
    point = _triangulate(projections, observations, weights)
    errors = _errors(point, projections, observations)

    # top + side 是基準約束；額外觀測超過門檻時只排除該觀測。
    for index in range(2, len(projections)):
        if errors[index] <= rejection_threshold_px:
            continue
        used[index] = False
    if used.sum() >= 2 and not used.all():
        selected = np.flatnonzero(used)
        point = _triangulate(
            [projections[index] for index in selected],
            [observations[index] for index in selected],
            weights[selected],
        )
        errors = _errors(point, projections, observations)
    return MultiviewResult(
        point=point,
        reprojection_errors_px=tuple(float(value) for value in errors),
        used_observations=tuple(bool(value) for value in used),
    )


__all__ = [
    "MultiviewResult",
    "axis_rotation_matrix",
    "project_rotating_point",
    "robust_multiview_triangulate",
    "rotating_projection_matrix",
    "rotating_world_to_camera",
    "undistort_rotating_point",
]
