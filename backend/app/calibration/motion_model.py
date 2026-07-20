from __future__ import annotations

import cv2
import numpy as np

from app.models.calibration_models import CalibrationMotionModel


def rotating_camera_pose(
    motion_model: CalibrationMotionModel,
    motor_angle_deg: float,
    arm_height_mm: float | None = None,
) -> np.ndarray:
    """Evaluate the solved rotating-camera pose at one angle and height."""

    if motion_model.rotation_axis_origin_mm is None:
        raise ValueError("旋臂運動模型缺少旋轉軸原點。")
    if motion_model.rotation_axis_direction is None:
        raise ValueError("旋臂運動模型缺少旋轉軸方向。")
    if motion_model.motor_zero_offset_deg is None:
        raise ValueError("旋臂運動模型缺少馬達零點偏移。")
    if motion_model.mount_transform_from_camera is None:
        raise ValueError("旋臂運動模型缺少相機安裝姿態。")
    if motion_model.lift_axis_direction is None:
        raise ValueError("旋臂運動模型缺少升降軸方向。")

    angle = float(motor_angle_deg)
    height = float(
        motion_model.arm_height_mm
        if arm_height_mm is None
        else arm_height_mm
    )
    if not np.isfinite([angle, height]).all() or height < 0:
        raise ValueError("旋臂角度與高度必須是有效且非負的數值。")
    minimum_angle, maximum_angle = motion_model.usable_angle_range_deg
    if angle < minimum_angle or angle > maximum_angle:
        raise ValueError(
            f"旋臂角度必須介於 {minimum_angle:g}° 與 {maximum_angle:g}°。"
        )

    origin = np.asarray(
        motion_model.rotation_axis_origin_mm,
        dtype=np.float64,
    )
    axis = np.asarray(
        motion_model.rotation_axis_direction,
        dtype=np.float64,
    )
    lift_axis = np.asarray(
        motion_model.lift_axis_direction,
        dtype=np.float64,
    )
    mount = np.asarray(
        motion_model.mount_transform_from_camera,
        dtype=np.float64,
    )
    if mount.shape != (4, 4) or not np.isfinite(mount).all():
        raise ValueError("旋臂相機安裝姿態不是有效的 4×4 矩陣。")

    rotation, _ = cv2.Rodrigues(
        axis * np.deg2rad(angle + motion_model.motor_zero_offset_deg)
    )
    translate_to_axis = np.eye(4, dtype=np.float64)
    translate_to_axis[:3, 3] = origin
    translate_from_axis = np.eye(4, dtype=np.float64)
    translate_from_axis[:3, 3] = -origin
    rotate_about_axis = np.eye(4, dtype=np.float64)
    rotate_about_axis[:3, :3] = rotation
    height_translation = np.eye(4, dtype=np.float64)
    height_translation[:3, 3] = (
        lift_axis * (height - motion_model.height_reference_mm)
    )
    return (
        height_translation
        @ translate_to_axis
        @ rotate_about_axis
        @ translate_from_axis
        @ mount
    )
