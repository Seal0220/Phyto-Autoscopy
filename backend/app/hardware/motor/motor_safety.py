from __future__ import annotations

from app.core.config import MotorSettings
from app.core.exceptions import MotorSafetyError


class MotorSafety:
    def __init__(self, settings: MotorSettings) -> None:
        self.settings = settings

    def validate_angle(self, angle_deg: float) -> None:
        if angle_deg < self.settings.minimum_angle_deg or angle_deg > self.settings.maximum_angle_deg:
            raise MotorSafetyError(
                f"目標角度 {angle_deg} 超出可用範圍 "
                f"{self.settings.minimum_angle_deg} 至 {self.settings.maximum_angle_deg} 度。"
            )

    def validate_current_limit(self, current_limit_amp: float) -> None:
        if current_limit_amp <= 0 or current_limit_amp > self.settings.maximum_current_limit_amp:
            raise MotorSafetyError(
                f"電流限制 {current_limit_amp} 安培超過最大值 "
                f"{self.settings.maximum_current_limit_amp} 安培。"
            )

    def validate_velocity(self, velocity_limit_deg_s: float) -> None:
        if (
            velocity_limit_deg_s <= 0
            or velocity_limit_deg_s > self.settings.maximum_velocity_limit_deg_s
        ):
            raise MotorSafetyError(
                f"速度限制 {velocity_limit_deg_s} 度/秒超過最大值 "
                f"{self.settings.maximum_velocity_limit_deg_s} 度/秒。"
            )

    def validate_acceleration(self, acceleration_deg_s2: float) -> None:
        if (
            acceleration_deg_s2 <= 0
            or acceleration_deg_s2 > self.settings.maximum_acceleration_deg_s2
        ):
            raise MotorSafetyError(
                f"加速度限制 {acceleration_deg_s2} 度/秒²超過最大值 "
                f"{self.settings.maximum_acceleration_deg_s2} 度/秒²。"
            )
