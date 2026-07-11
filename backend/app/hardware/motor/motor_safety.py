from __future__ import annotations

from app.core.config import MotorSettings
from app.core.exceptions import MotorSafetyError


class MotorSafety:
    def __init__(self, settings: MotorSettings) -> None:
        self.settings = settings

    def validate_angle(self, angle_deg: float) -> None:
        if angle_deg < self.settings.minimum_angle_deg or angle_deg > self.settings.maximum_angle_deg:
            raise MotorSafetyError(
                f"Target angle {angle_deg} is outside "
                f"{self.settings.minimum_angle_deg}..{self.settings.maximum_angle_deg} deg"
            )

    def validate_current_limit(self, current_limit_amp: float) -> None:
        if current_limit_amp <= 0 or current_limit_amp > self.settings.maximum_current_limit_amp:
            raise MotorSafetyError(
                f"Current limit {current_limit_amp}A exceeds maximum "
                f"{self.settings.maximum_current_limit_amp}A"
            )

    def validate_velocity(self, velocity_limit_deg_s: float) -> None:
        if (
            velocity_limit_deg_s <= 0
            or velocity_limit_deg_s > self.settings.maximum_velocity_limit_deg_s
        ):
            raise MotorSafetyError(
                f"Velocity {velocity_limit_deg_s}deg/s exceeds maximum "
                f"{self.settings.maximum_velocity_limit_deg_s}deg/s"
            )

    def validate_acceleration(self, acceleration_deg_s2: float) -> None:
        if (
            acceleration_deg_s2 <= 0
            or acceleration_deg_s2 > self.settings.maximum_acceleration_deg_s2
        ):
            raise MotorSafetyError(
                f"Acceleration {acceleration_deg_s2}deg/s^2 exceeds maximum "
                f"{self.settings.maximum_acceleration_deg_s2}deg/s^2"
            )
