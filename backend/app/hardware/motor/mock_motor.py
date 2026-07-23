from __future__ import annotations

from threading import Lock

from app.core.config import MotorSettings
from app.core.exceptions import MotorError
from app.hardware.motor.motor_safety import MotorSafety
from app.hardware.motor.motor_state import MotorRuntimeState
from app.models.motor_models import MotorStatus


class MockMotorController:
    def __init__(self, settings: MotorSettings) -> None:
        self.settings = settings
        self.safety = MotorSafety(settings)
        self.state = MotorRuntimeState(connected=True, command_position_deg=0.0)
        self._lock = Lock()

    def connect(self) -> None:
        self.state.connected = True

    def start(self) -> None:
        self.connect()

    def close(self) -> None:
        self.state.connected = False
        self.state.engaged = False
        self.state.moving = False

    def status(self) -> MotorStatus:
        return MotorStatus(
            name=self.settings.name,
            controller=self.settings.controller,
            connected=self.state.connected,
            engaged=self.state.engaged,
            moving=self.state.moving,
            emergency_stopped=self.state.emergency_stopped,
            command_position_deg=self.state.command_position_deg,
            minimum_angle_deg=self.settings.minimum_angle_deg,
            maximum_angle_deg=self.settings.maximum_angle_deg,
            velocity_limit_deg_s=self.settings.velocity_limit_deg_s,
            acceleration_deg_s2=self.settings.acceleration_deg_s2,
            current_limit_amp=self.settings.current_limit_amp,
            last_error=self.state.last_error,
        )

    def engage(self) -> MotorStatus:
        with self._lock:
            self.state.connected = True
            self.state.engaged = True
            self.state.emergency_stopped = False
            self.state.last_error = None
            return self.status()

    def disengage(self) -> MotorStatus:
        with self._lock:
            self.state.engaged = False
            self.state.moving = False
            return self.status()

    def set_origin(self) -> MotorStatus:
        with self._lock:
            if self.state.moving:
                raise MotorError("馬達移動中，無法設定原點。")
            self.state.command_position_deg = 0.0
            return self.status()

    def move_to_angle(self, angle_deg: float) -> MotorStatus:
        with self._lock:
            self.safety.validate_angle(angle_deg)
            if self.state.emergency_stopped:
                raise MotorError("馬達已緊急停止，請先重新啟用馬達。")
            if not self.state.engaged:
                raise MotorError("移動前請先啟用馬達。")
            self.state.moving = True
            self.state.command_position_deg = angle_deg
            self.state.moving = False
            self.state.last_error = None
            return self.status()

    def move_relative(self, delta_deg: float) -> MotorStatus:
        return self.move_to_angle(self.state.command_position_deg + delta_deg)

    def return_origin(self) -> MotorStatus:
        return self.move_to_angle(0.0)

    def stop(self) -> MotorStatus:
        with self._lock:
            self.state.moving = False
            return self.status()

    def emergency_stop(self) -> MotorStatus:
        with self._lock:
            self.state.moving = False
            self.state.engaged = False
            self.state.emergency_stopped = True
            return self.status()
