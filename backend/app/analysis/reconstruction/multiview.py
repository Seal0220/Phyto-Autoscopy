from __future__ import annotations

from dataclasses import dataclass, field
from math import cos, radians, sin
from typing import Any, Sequence

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class MultiviewResult:
    point: np.ndarray
    reprojection_errors_px: tuple[float, ...]
    used_observations: tuple[bool, ...]
    quality: dict[str, Any] = field(default_factory=dict)


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
        if not np.isfinite(projected).all() or projected[2] <= 1e-12:
            values.append(float("inf"))
            continue
        pixel = projected[:2] / projected[2]
        values.append(
            float(np.linalg.norm(pixel - np.asarray(observation, dtype=np.float64)))
        )
    return np.asarray(values, dtype=np.float64)


def _refine_reprojection(point, projections, observations, weights, huber_delta):
    """IRLS Gauss-Newton in pixel space, rather than averaging 3-D seeds."""
    matrices = np.asarray(projections, dtype=np.float64)
    pixels = np.asarray(observations, dtype=np.float64)

    def evaluate(value):
        q = matrices @ np.append(value, 1.)
        if np.any(q[:, 2] <= 1e-9):
            return None
        residual = q[:, :2] / q[:, 2, None] - pixels
        norm = np.linalg.norm(residual, axis=1)
        cost = np.sum(weights * np.where(norm <= huber_delta, .5 * norm ** 2,
                                        huber_delta * (norm - .5 * huber_delta)))
        return q, residual, norm, cost

    point = np.asarray(point, dtype=np.float64).copy()
    for _ in range(15):
        evaluation = evaluate(point)
        if evaluation is None:
            raise ValueError("定位點深度不足，無法穩定計算重投影。")
        q, residual, norm, cost = evaluation
        jacobian = (matrices[:, :2, :3] * q[:, 2, None, None] - q[:, :2, None] * matrices[:, 2, None, :3]) / q[:, 2, None, None] ** 2
        robust_weights = weights * np.minimum(1., huber_delta / np.maximum(norm, 1e-12))
        lhs = jacobian.reshape(-1, 3) * np.repeat(np.sqrt(robust_weights), 2)[:, None]
        rhs = residual.ravel() * np.repeat(np.sqrt(robust_weights), 2)
        delta, _, rank, _ = np.linalg.lstsq(lhs, -rhs, rcond=None)
        if rank < 3:
            raise ValueError("觀測的視角不足，無法精確定位三維點。")
        if np.linalg.norm(delta) < 1e-8 * max(np.linalg.norm(point), 1.):
            break
        accepted = False
        for factor in (1., .5, .25, .125, .0625):
            candidate = point + factor * delta
            evaluation = evaluate(candidate)
            if evaluation is not None and evaluation[-1] <= cost:
                point, accepted = candidate, True
                break
        if not accepted:
            break
    return point


def robust_multiview_triangulate(
    projections: Sequence[np.ndarray],
    observations: Sequence[Sequence[float]],
    *,
    confidence: Sequence[float] | None = None,
    rejection_threshold_px: float = 8.0,
    camera_ids: Sequence[str] | None = None,
) -> MultiviewResult:
    if len(projections) != len(observations) or len(projections) < 2:
        raise ValueError("多視角三角化至少需要兩組相同數量的投影與觀測。")
    weights = np.asarray(
        confidence if confidence is not None else np.ones(len(projections)),
        dtype=np.float64,
    )
    if (
        weights.shape != (len(projections),)
        or not np.isfinite(weights).all()
        or np.any(weights < 0)
    ):
        raise ValueError("多視角觀測信心格式無效。")
    if not np.isfinite(rejection_threshold_px) or rejection_threshold_px <= 0:
        raise ValueError("多視角重投影門檻必須大於零。")
    matrices = np.asarray(projections, dtype=np.float64)
    pixels = np.asarray(observations, dtype=np.float64)
    if matrices.shape != (len(projections), 3, 4) or pixels.shape != (len(projections), 2) or not np.isfinite(matrices).all() or not np.isfinite(pixels).all():
        raise ValueError("多視角投影或像素座標格式無效。")
    if camera_ids is not None and len(camera_ids) != len(projections):
        raise ValueError("觀測鏡頭數量與投影不一致。")
    if np.count_nonzero(weights > 0) < 2 or np.any(weights[:2] <= 0):
        raise ValueError("多視角定位需要至少兩個具有信心的基準觀測。")

    # The first two observations form a measured two-view seed. Never let an
    # outlying additional view pull the initial solution away from that seed.
    point = _triangulate(projections[:2], observations[:2], weights[:2])
    errors = _errors(point, projections, observations)
    if not np.isfinite(errors[:2]).all():
        raise ValueError("雙鏡頭基準點位於相機後方或無法投影。")
    used = (weights > 0) & (errors <= rejection_threshold_px)
    if used.sum() < 2:
        raise ValueError("基準觀測未通過重投影檢查。")

    # Extra views are admitted against the seed, then checked again after
    # refinement. A rejected view cannot alter the seeded coordinates.
    for _ in range(min(8, max(1, len(projections) - 1))):
        selected = np.flatnonzero(used)
        active_weights = weights[selected].copy()
        if camera_ids is not None:
            # Repeated fixed frames must not outweigh a different viewpoint
            # simply because a camera happened to record more snapshots.
            active_cameras = np.asarray(camera_ids)[selected]
            for camera in set(active_cameras):
                group = active_cameras == camera
                active_weights[group] /= int(group.sum())
        point = _refine_reprojection(
            point, matrices[selected], pixels[selected], active_weights,
            huber_delta=max(1., rejection_threshold_px / 4.),
        )
        errors = _errors(point, projections, observations)
        outliers = used & (errors > rejection_threshold_px)
        if not outliers.any():
            break
        if (used & ~outliers).sum() < 2:
            raise ValueError("重投影內點不足，無法精確定位三維點。")
        used[outliers] = False
    else:
        raise ValueError("多視角定位的內點集合尚未收斂，請檢查錯配觀測。")
    return MultiviewResult(
        point=point,
        reprojection_errors_px=tuple(float(value) for value in errors),
        used_observations=tuple(bool(value) for value in used),
        quality={"aggregation_method": "camera_balanced_huber_reprojection",
                 "input_observation_count": len(projections), "accepted_observation_count": int(used.sum()),
                 "rejected_observation_count": int((~used).sum()),
                 "median_reprojection_error_px": float(np.median(errors[used])),
                 "p95_reprojection_error_px": float(np.percentile(errors[used], 95))},
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
