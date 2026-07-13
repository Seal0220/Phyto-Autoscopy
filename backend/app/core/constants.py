from __future__ import annotations

CAMERA_ROLES = ("top", "side", "rotating")

CAMERA_NAMES = {
    "top": "CHLOROCULUS EYE-TOP",
    "side": "CHLOROCULUS EYE-SIDE",
    "rotating": "CHLOROCULUS EYE-ARM",
}

METADATA_FIELDS = (
    "project_name",
    "project_name_zh",
    "device_name",
    "record_id",
    "cycle_id",
    "camera_id",
    "camera_name",
    "timestamp",
    "angle_deg",
    "motor_position_deg",
    "file_path",
    "status",
    "error_message",
)

MODE_CAPTURE_LOG_FIELDS = (
    "mode_id",
    "mode_type",
    "cycle_id",
    "motion_direction",
    "capture_index",
    "elapsed_seconds",
    "trigger_value",
    "target_angle_deg",
    "commanded_angle_deg",
    "actual_angle_deg",
    "angle_error_deg",
    "camera_id",
    "image_name",
    "file_path",
    "captured_at",
    "status",
    "error_message",
)
