from __future__ import annotations

CAMERA_ROLES = ("top", "side", "rotating")

CAPTURE_IMAGE_EXTENSION = ".png"
CAPTURE_IMAGE_SUFFIXES = frozenset({
    CAPTURE_IMAGE_EXTENSION,
    ".jpg",
    ".jpeg",
})

CAMERA_NAMES = {
    "top": "CHLOROCULUS EYE-TOP",
    "side": "CHLOROCULUS EYE-SIDE",
    "rotating": "CHLOROCULUS EYE-ARM",
}

CAPTURE_MODE_NAMES = {
    "continuous_interval": "ContinuousInterval",
    "time_interval": "TimeInterval",
    "angle_interval": "AngleInterval",
    "specific_angles": "SpecificAngles",
    "equal_divisions": "EqualDivisions",
}

CAPTURE_MODE_ABBREVIATIONS = {
    "continuous_interval": "CI",
    "time_interval": "TI",
    "angle_interval": "AI",
    "specific_angles": "SA",
    "equal_divisions": "ED",
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
