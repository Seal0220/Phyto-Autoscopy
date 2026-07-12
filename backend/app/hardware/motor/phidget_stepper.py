from __future__ import annotations

import logging
import time
from threading import Lock

from app.core.config import MotorSettings
from app.core.exceptions import MotorError
from app.hardware.motor.motor_profile import MotorProfile
from app.hardware.motor.motor_safety import MotorSafety
from app.hardware.motor.motor_state import MotorRuntimeState
from app.models.motor_models import MotorStatus

logger = logging.getLogger(__name__)


class PhidgetStepperController:
    def __init__(self, settings: MotorSettings) -> None:
        self.settings = settings
        self.profile = MotorProfile(settings)
        self.safety = MotorSafety(settings)
        self.state = MotorRuntimeState(command_position_deg=settings.origin_deg)
        self._stepper = None
        self._lock = Lock()

    def connect(self) -> None:
        if self._stepper is not None:
            return
        try:
            from Phidget22.Devices.Stepper import Stepper  # type: ignore
        except ImportError as exc:
            self.state.last_error = str(exc)
            raise MotorError("尚未安裝 Phidget22 馬達驅動程式。") from exc

        stepper = Stepper()
        stepper.openWaitForAttachment(5000)
        self._stepper = stepper
        self.state.connected = True
        self._apply_profile()

    def _apply_profile(self) -> None:
        if self._stepper is None:
            return
        self.safety.validate_current_limit(self.settings.current_limit_amp)
        self.safety.validate_velocity(self.settings.velocity_limit_deg_s)
        self.safety.validate_acceleration(self.settings.acceleration_deg_s2)
        self._stepper.setCurrentLimit(self.settings.current_limit_amp)
        if hasattr(self._stepper, "setHoldingCurrentLimit"):
            self._stepper.setHoldingCurrentLimit(self.settings.holding_current_amp)
        self._stepper.setVelocityLimit(self.profile.degrees_to_steps(self.settings.velocity_limit_deg_s))
        self._stepper.setAcceleration(self.profile.degrees_to_steps(self.settings.acceleration_deg_s2))

    def close(self) -> None:
        if self._stepper is not None:
            self._stepper.close()
            self._stepper = None
        self.state.connected = False
        self.state.engaged = False
        self.state.moving = False

    def status(self) -> MotorStatus:
        if self._stepper is not None:
            try:
                self.state.command_position_deg = self.profile.steps_to_degrees(
                    float(self._stepper.getPosition())
                )
                self.state.moving = bool(self._stepper.getIsMoving())
            except Exception as exc:  # pragma: no cover - depends on hardware state
                logger.warning("Failed to refresh Phidget status: %s", exc)
                self.state.last_error = str(exc)
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
            self.connect()
            self._apply_profile()
            self._stepper.setEngaged(True)
            self.state.engaged = True
            self.state.emergency_stopped = False
            self.state.last_error = None
            return self.status()

    def disengage(self) -> MotorStatus:
        with self._lock:
            if self._stepper is not None:
                self._stepper.setEngaged(False)
            self.state.engaged = False
            self.state.moving = False
            return self.status()

    def set_origin(self) -> MotorStatus:
        with self._lock:
            if self.state.moving:
                raise MotorError("馬達移動中，無法設定原點。")
            if self._stepper is not None and hasattr(self._stepper, "setPosition"):
                self._stepper.setPosition(self.profile.degrees_to_steps(self.settings.origin_deg))
            self.state.command_position_deg = self.settings.origin_deg
            return self.status()

    def move_to_angle(self, angle_deg: float) -> MotorStatus:
        with self._lock:
            self.safety.validate_angle(angle_deg)
            if self.state.emergency_stopped:
                raise MotorError("馬達已緊急停止，請先重新啟用馬達。")
            if not self.state.engaged:
                raise MotorError("移動前請先啟用馬達。")
            self.connect()
            target_steps = self.profile.degrees_to_steps(angle_deg)
            self._stepper.setTargetPosition(target_steps)
            started = time.monotonic()
            self.state.moving = True
            while self._stepper.getIsMoving():
                if time.monotonic() - started > self.settings.movement_timeout_seconds:
                    self.stop()
                    raise MotorError("馬達移動逾時。")
                time.sleep(0.05)
            self.state.command_position_deg = angle_deg
            self.state.moving = False
            self.state.last_error = None
            return self.status()

    def move_relative(self, delta_deg: float) -> MotorStatus:
        return self.move_to_angle(self.status().command_position_deg + delta_deg)

    def return_origin(self) -> MotorStatus:
        return self.move_to_angle(self.settings.origin_deg)

    def stop(self) -> MotorStatus:
        with self._lock:
            if self._stepper is not None:
                self._stepper.setTargetPosition(self._stepper.getPosition())
            self.state.moving = False
            return self.status()

    def emergency_stop(self) -> MotorStatus:
        with self._lock:
            if self._stepper is not None:
                self._stepper.setTargetPosition(self._stepper.getPosition())
                self._stepper.setEngaged(False)
            self.state.moving = False
            self.state.engaged = False
            self.state.emergency_stopped = True
            return self.status()
