from __future__ import annotations


INTERNAL_ERROR_DETAIL = "伺服器處理請求時發生錯誤，請稍後再試。"


class PhytoAutoscopyError(Exception):
    """Base exception for expected CHLOROCULUS application errors."""

    error_code = "application_error"


class ConfigError(PhytoAutoscopyError):
    error_code = "config_error"


class HardwareError(PhytoAutoscopyError):
    error_code = "hardware_error"


class CameraError(HardwareError):
    error_code = "camera_error"


class MotorError(HardwareError):
    error_code = "motor_error"


class MotorSafetyError(MotorError):
    error_code = "motor_safety_error"


class RecordError(PhytoAutoscopyError):
    error_code = "record_error"


class StorageError(PhytoAutoscopyError):
    error_code = "storage_error"


class AnalysisError(PhytoAutoscopyError):
    error_code = "analysis_error"


class CalibrationError(PhytoAutoscopyError):
    error_code = "calibration_error"


class OperationCancelledError(PhytoAutoscopyError):
    error_code = "operation_cancelled"


def public_error_detail(exc: BaseException) -> str:
    """Return only messages that are safe to expose to API clients."""
    if isinstance(exc, PhytoAutoscopyError):
        return str(exc)
    return INTERNAL_ERROR_DETAIL


def public_error_code(exc: BaseException) -> str:
    if isinstance(exc, PhytoAutoscopyError):
        return exc.error_code
    return "internal_error"
