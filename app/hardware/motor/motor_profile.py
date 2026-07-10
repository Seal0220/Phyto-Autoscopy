from __future__ import annotations

from app.core.config import MotorSettings


class MotorProfile:
    def __init__(self, settings: MotorSettings) -> None:
        self.settings = settings

    @property
    def steps_per_degree(self) -> float:
        return self.settings.microstep_division / self.settings.full_step_angle_deg

    def degrees_to_steps(self, angle_deg: float) -> float:
        return angle_deg * self.steps_per_degree

    def steps_to_degrees(self, steps: float) -> float:
        return steps / self.steps_per_degree
