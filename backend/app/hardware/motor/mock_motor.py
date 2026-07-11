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
        self.state = MotorRuntimeState(connected=True, command_position_deg=settings.origin_deg)
        self._lock = Lock()

    def connect(self) -> None:
        self.state.connected = True

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
            origin_deg=self.settings.origin_deg,
            minimum_angle_deg=self.settings.minimum_angle_deg,
            maximum_angle_deg=self.settings.maximum_angle_deg,
            velocity_limit_deg_s=self.settings.velocity_limit_deg_s,
            acceleration_deg_s2=self.settings.acceleration_deg_s2,
            current_limit_amp=self.settings.current_limit_amp,
            holding_current_amp=self.settings.holding_current_amp,
            last_error=self.state.last_error,
        )

    def engage(self) -> MotorStatus:
        with self._lock:
            if self.state.emergency_stopped:
                raise MotorError("Motor is emergency-stopped; clear by restarting the app")
            self.state.connected = True
            self.state.engaged = True
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
                raise MotorError("Cannot set origin while motor is moving")
            self.state.command_position_deg = self.settings.origin_deg
            return self.status()

    def move_to_angle(self, angle_deg: float) -> MotorStatus:
        with self._lock:
            self.safety.validate_angle(angle_deg)
            if self.state.emergency_stopped:
                raise MotorError("Motor is emergency-stopped")
            if not self.state.engaged:
                raise MotorError("Motor must be engaged before movement")
            self.state.moving = True
            self.state.command_position_deg = angle_deg
            self.state.moving = False
            self.state.last_error = None
            return self.status()

    def move_relative(self, delta_deg: float) -> MotorStatus:
        return self.move_to_angle(self.state.command_position_deg + delta_deg)

    def return_origin(self) -> MotorStatus:
        return self.move_to_angle(self.settings.origin_deg)

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
