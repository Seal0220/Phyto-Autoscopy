from __future__ import annotations

import cv2
import numpy as np

from app.analysis.calibration.camera_calibration import (
    create_chessboard_object_points,
)
from app.analysis.calibration.rotating_calibration import (
    calibrate_rotating_rig_from_points,
)


def _world_from_camera(
    angle_deg: float,
    *,
    radius: float = 420.0,
) -> np.ndarray:
    angle = np.deg2rad(angle_deg)
    target = np.asarray([54.0, 36.0, 0.0])
    center = np.asarray([
        target[0] + radius * np.cos(angle),
        target[1] + radius * np.sin(angle),
        520.0,
    ])
    forward = target - center
    forward /= np.linalg.norm(forward)
    right = np.cross(np.asarray([0.0, 0.0, 1.0]), forward)
    right /= np.linalg.norm(right)
    down = np.cross(forward, right)
    pose = np.eye(4)
    pose[:3, :3] = np.column_stack((right, down, forward))
    pose[:3, 3] = center
    return pose


def test_rotating_calibration_recovers_axis_and_dynamic_pose_samples() -> None:
    pattern = (10, 7)
    square_size = (12.0, 12.0)
    object_points = create_chessboard_object_points(
        pattern,
        square_size,
    )
    camera_matrix = np.asarray([
        [700.0, 0.0, 640.0],
        [0.0, 700.0, 480.0],
        [0.0, 0.0, 1.0],
    ])
    distortion = np.zeros(5)
    detections = []
    for angle in (0.0, 60.0, 120.0, 180.0, 240.0, 300.0):
        world_from_camera = _world_from_camera(angle)
        camera_from_world = np.linalg.inv(world_from_camera)
        rotation_vector, _ = cv2.Rodrigues(camera_from_world[:3, :3])
        projected, _ = cv2.projectPoints(
            object_points,
            rotation_vector,
            camera_from_world[:3, 3],
            camera_matrix,
            distortion,
        )
        detections.append({
            "image_id": f"rotating-{angle:g}",
            "angle_deg": angle,
            "corners": projected.reshape(-1, 2).tolist(),
        })

    result = calibrate_rotating_rig_from_points(
        detections,
        camera_matrix=camera_matrix,
        distortion_coefficients=distortion,
        pattern_size=pattern,
        square_size_mm=square_size,
    )

    assert len(result.samples) == 6
    assert result.zero_angle_deg == 0.0
    assert abs(float(result.axis_direction[2])) > 0.999
    assert np.allclose(result.axis_origin_mm[:2], [54.0, 36.0], atol=0.1)
    assert result.residual_mean_px < 0.001
