from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np


def camera_pose_from_detection(
    detection: dict,
    intrinsics: object,
) -> np.ndarray:
    object_points = np.asarray(detection.get("object_points"), dtype=np.float64).reshape(-1, 3)
    image_points = np.asarray(detection.get("image_points"), dtype=np.float64).reshape(-1, 1, 2)
    if len(object_points) < 6 or len(object_points) != len(image_points):
        raise ValueError("旋臂校正觀測缺少足夠的校正板角點。")
    matrix = np.asarray(
        intrinsics.camera_matrix,
        dtype=np.float64,
    ).copy()
    width = int(detection.get("image_width") or intrinsics.width)
    height = int(detection.get("image_height") or intrinsics.height)
    if width <= 0 or height <= 0:
        raise ValueError("旋臂校正觀測的影像解析度無效。")
    matrix[0, :] *= width / float(intrinsics.width)
    matrix[1, :] *= height / float(intrinsics.height)
    matrix[2, :] = [0.0, 0.0, 1.0]
    distortion = np.asarray(intrinsics.distortion_coefficients, dtype=np.float64)
    if intrinsics.camera_model == "opencv_fisheye":
        image_points = cv2.fisheye.undistortPoints(
            image_points,
            matrix,
            distortion,
            P=matrix,
        )
        effective_distortion = None
    else:
        effective_distortion = distortion
    success, rotation_vector, translation = cv2.solvePnP(
        object_points,
        image_points,
        matrix,
        effective_distortion,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not success:
        raise ValueError("旋臂相機姿態求解失敗。")
    rotation, _ = cv2.Rodrigues(rotation_vector)
    camera_from_board = np.eye(4, dtype=np.float64)
    camera_from_board[:3, :3] = rotation
    camera_from_board[:3, 3] = translation.reshape(3)
    return np.linalg.inv(camera_from_board)


def _fit_circle_axis(positions: np.ndarray) -> tuple[np.ndarray, np.ndarray, float, float]:
    center = np.mean(positions, axis=0)
    centered = positions - center
    _, singular, right = np.linalg.svd(centered)
    if len(singular) < 2 or singular[1] <= 1e-6:
        raise ValueError("旋臂校正角度分布不足，無法估計旋轉軸。")
    axis = right[-1]
    axis /= np.linalg.norm(axis)
    basis_x = right[0]
    basis_y = np.cross(axis, basis_x)
    plane = np.column_stack((centered @ basis_x, centered @ basis_y))
    system = np.column_stack((2 * plane, np.ones(len(plane))))
    target = np.sum(plane * plane, axis=1)
    solution, *_ = np.linalg.lstsq(system, target, rcond=None)
    circle_center = center + solution[0] * basis_x + solution[1] * basis_y
    radii = np.linalg.norm(plane - solution[:2], axis=1)
    radius = float(np.mean(radii))
    residual = float(np.sqrt(np.mean((radii - radius) ** 2)))
    return circle_center, axis, radius, residual


def fit_rotation_axis(
    observations: Sequence[object],
    intrinsics: object,
) -> dict:
    samples: list[dict] = []
    for observation in observations:
        angle = getattr(observation, "motor_angle_deg", None)
        detection = getattr(observation, "detections", {}).get("rotating")
        if angle is None or not detection or not detection.get("board_detected"):
            continue
        pose = camera_pose_from_detection(detection, intrinsics)
        samples.append({
            "observation_id": observation.observation_id,
            "angle_deg": float(angle),
            "world_from_camera": pose,
        })
    if len(samples) < 3 or len({item["angle_deg"] for item in samples}) < 3:
        raise ValueError("旋臂外參至少需要三個不同馬達角度的有效觀測。")
    samples.sort(key=lambda item: item["angle_deg"])
    positions = np.asarray(
        [item["world_from_camera"][:3, 3] for item in samples],
        dtype=np.float64,
    )
    origin, axis, radius, residual = _fit_circle_axis(positions)
    reference = min(samples, key=lambda item: abs(item["angle_deg"]))
    direction_votes: list[float] = []
    reference_rotation = reference["world_from_camera"][:3, :3]
    for sample in samples:
        delta = sample["angle_deg"] - reference["angle_deg"]
        if abs(delta) <= 1e-9:
            continue
        relative = sample["world_from_camera"][:3, :3] @ reference_rotation.T
        rotation_vector, _ = cv2.Rodrigues(relative)
        direction_votes.append(float(np.dot(rotation_vector.reshape(3), axis) / delta))
    direction = 1 if sum(direction_votes) >= 0 else -1
    if direction < 0:
        axis = -axis
    return {
        "rotation_axis_origin_mm": origin.astype(float).tolist(),
        "rotation_axis_direction": axis.astype(float).tolist(),
        "motor_zero_offset_deg": float(-reference["angle_deg"]),
        "arm_radius_mm": radius,
        "axis_fit_residual_mm": residual,
        "mount_transform_from_camera": reference["world_from_camera"].astype(float).tolist(),
        "fitted_angles_deg": [item["angle_deg"] for item in samples],
        "samples": [
            {
                "observation_id": item["observation_id"],
                "angle_deg": item["angle_deg"],
                "observed_world_from_camera": item["world_from_camera"].astype(float).tolist(),
            }
            for item in samples
        ],
    }
