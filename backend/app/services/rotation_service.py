from __future__ import annotations

import time

from app.core.config import AppSettings
from app.core.exceptions import MotorSafetyError
from app.models.camera_models import CaptureResult
from app.services.capture_service import CaptureService
from app.services.session_service import SessionService


class RotationService:
    def __init__(
        self,
        settings: AppSettings,
        motor_controller,
        capture_service: CaptureService,
        sessions: SessionService,
    ) -> None:
        self.settings = settings
        self.motor_controller = motor_controller
        self.capture_service = capture_service
        self.sessions = sessions

    def angle_sequence(self, start_deg: float, end_deg: float, step_deg: float) -> list[float]:
        if step_deg <= 0:
            raise MotorSafetyError("旋轉步進角度必須大於 0。")
        if end_deg < start_deg:
            raise MotorSafetyError("旋轉結束角度不可小於起始角度。")
        values: list[float] = []
        current = start_deg
        while current < end_deg - 1e-9:
            values.append(round(current, 3))
            current += step_deg
        if not values or abs(values[-1] - end_deg) > 1e-9:
            values.append(round(end_deg, 3))
        return values

    def schedule_capture_sequence(
        self,
        start_deg: float,
        end_deg: float,
        step_deg: float,
        capture_on_return: bool,
    ) -> list[tuple[float, str]]:
        forward = self.angle_sequence(start_deg, end_deg, step_deg)
        sequence = [(angle, "forward") for angle in forward]
        if capture_on_return:
            return_angles = list(reversed(forward[:-1]))
            current = start_deg - step_deg
            while current > 1e-9:
                return_angles.append(round(current, 3))
                current -= step_deg
            if not return_angles or abs(return_angles[-1]) > 1e-9:
                return_angles.append(0.0)
            sequence.extend((angle, "return") for angle in return_angles)
        return sequence

    def capture_cycle(
        self,
        session_id: str | None = None,
        cycle_id: int = 1,
        start_deg: float | None = None,
        end_deg: float | None = None,
        step_deg: float | None = None,
    ) -> list[CaptureResult]:
        session = self.sessions.ensure_active_session() if session_id is None else self.sessions.get_session(session_id)
        start = self.settings.experiment.rotation_start_deg if start_deg is None else start_deg
        end = self.settings.experiment.rotation_end_deg if end_deg is None else end_deg
        step = self.settings.experiment.rotation_step_deg if step_deg is None else step_deg
        captures: list[CaptureResult] = []

        for angle in self.angle_sequence(start, end, step):
            self.motor_controller.move_to_angle(angle)
            time.sleep(self.settings.motor.stabilization_delay_ms / 1000)
            captures.append(
                self.capture_service.capture_camera(
                    "rotating_arm",
                    session_id=session.session_id,
                    cycle_id=cycle_id,
                    angle_deg=angle,
                )
            )

        self.motor_controller.move_to_angle(start)
        return captures
