from __future__ import annotations


class PhytoAutoscopyError(Exception):
    """Base exception for expected CHLOROCULUS application errors."""


class ConfigError(PhytoAutoscopyError):
    pass


class HardwareError(PhytoAutoscopyError):
    pass


class CameraError(HardwareError):
    pass


class MotorError(HardwareError):
    pass


class MotorSafetyError(MotorError):
    pass


class SessionError(PhytoAutoscopyError):
    pass
