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
            raise MotorSafetyError("rotation_step_deg must be greater than 0")
        if end_deg < start_deg:
            raise MotorSafetyError("rotation_end_deg must be greater than or equal to rotation_start_deg")
        values: list[float] = []
        current = start_deg
        while current <= end_deg + 1e-9:
            values.append(round(current, 3))
            current += step_deg
        return values

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

        if self.settings.motor.return_to_origin_after_cycle:
            self.motor_controller.return_origin()
        if self.settings.motor.disengage_after_cycle:
            self.motor_controller.disengage()
        return captures
