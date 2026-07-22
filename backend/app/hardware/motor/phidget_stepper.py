from __future__ import annotations

import logging
import time
from threading import Event, Lock, RLock, Thread, current_thread

from app.core.config import MotorSettings
from app.core.exceptions import MotorError, OperationCancelledError
from app.hardware.motor.motor_profile import MotorProfile
from app.hardware.motor.motor_safety import MotorSafety
from app.hardware.motor.motor_state import MotorRuntimeState
from app.models.motor_models import MotorStatus

logger = logging.getLogger(__name__)

AUTO_CONNECT_RETRY_SECONDS = 2.0
AUTO_CONNECT_TIMEOUT_MS = 1000


class PhidgetStepperController:
    def __init__(self, settings: MotorSettings) -> None:
        self.settings = settings
        self.profile = MotorProfile(settings)
        self.safety = MotorSafety(settings)
        self.state = MotorRuntimeState(command_position_deg=0.0)
        self._stepper = None
        self._lock = RLock()
        self._connect_lock = Lock()
        self._auto_connect_stop = Event()
        self._auto_connect_thread: Thread | None = None
        self._movement_generation = 0
        self._active_movement_generation: int | None = None

    def start(self) -> None:
        with self._lock:
            if (
                self._auto_connect_thread is not None
                and self._auto_connect_thread.is_alive()
            ):
                return
            self._auto_connect_stop.clear()
            worker = Thread(
                target=self._auto_connect_loop,
                name="motor-auto-connect",
                daemon=True,
            )
            self._auto_connect_thread = worker
        worker.start()

    def _auto_connect_loop(self) -> None:
        while not self._auto_connect_stop.is_set():
            with self._lock:
                should_connect = self._stepper is None

            if should_connect:
                try:
                    self.connect(AUTO_CONNECT_TIMEOUT_MS)
                except MotorError as exc:
                    logger.debug("Motor auto-connect is waiting: %s", exc)

            self._auto_connect_stop.wait(AUTO_CONNECT_RETRY_SECONDS)

    def _handle_attach(self, stepper) -> None:
        with self._lock:
            if self._stepper is not stepper:
                return
            self.state.connected = True
            self.state.last_error = None
            try:
                self._apply_profile()
            except Exception as exc:
                self.state.last_error = "套用馬達設定失敗。"
                logger.warning("Failed to apply motor profile after attach: %s", exc)
        logger.info("Motor controller attached")

    def _handle_detach(self, stepper) -> None:
        with self._lock:
            if self._stepper is not stepper:
                return
            self._movement_generation += 1
            self._active_movement_generation = None
            self.state.connected = False
            self.state.engaged = False
            self.state.moving = False
            self.state.last_error = "馬達控制器連線已中斷。"
        logger.warning("Motor controller detached")

    def connect(self, attachment_timeout_ms: int = 5000) -> None:
        with self._connect_lock:
            with self._lock:
                if self._stepper is not None:
                    return
            try:
                from Phidget22.Devices.Stepper import Stepper  # type: ignore
            except ImportError as exc:
                with self._lock:
                    self.state.last_error = "尚未安裝 Phidget22 馬達驅動程式。"
                raise MotorError("尚未安裝 Phidget22 馬達驅動程式。") from exc

            stepper = None
            try:
                stepper = Stepper()
                stepper.setOnAttachHandler(self._handle_attach)
                stepper.setOnDetachHandler(self._handle_detach)
                stepper.openWaitForAttachment(attachment_timeout_ms)
                with self._lock:
                    self._stepper = stepper
                    self.state.connected = True
                    self.state.engaged = False
                    self.state.moving = False
                    self.state.last_error = None
                    self._apply_profile()
                logger.info("Motor controller connected")
            except Exception as exc:
                if stepper is not None:
                    try:
                        stepper.close()
                    except Exception:
                        logger.exception("Failed to close rejected Phidget connection")
                with self._lock:
                    self._stepper = None
                    self.state.connected = False
                    self.state.engaged = False
                    self.state.moving = False
                    self.state.last_error = "未偵測到可用的馬達控制器。"
                if isinstance(exc, MotorError):
                    raise
                raise MotorError("未偵測到可用的馬達控制器。") from exc

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
        self._auto_connect_stop.set()
        worker = self._auto_connect_thread
        if (
            worker is not None
            and worker.is_alive()
            and worker is not current_thread()
        ):
            worker.join(timeout=AUTO_CONNECT_RETRY_SECONDS + 1.0)

        with self._connect_lock:
            with self._lock:
                stepper = self._stepper
                self._stepper = None
                self._auto_connect_thread = None
                self._movement_generation += 1
                self._active_movement_generation = None
                self.state.connected = False
                self.state.engaged = False
                self.state.moving = False
            if stepper is not None:
                try:
                    stepper.close()
                except Exception as exc:
                    with self._lock:
                        self.state.last_error = "關閉馬達控制器失敗。"
                    raise MotorError("關閉馬達控制器失敗。") from exc

    def _require_connected(self) -> None:
        if not self.state.connected or self._stepper is None:
            raise MotorError("馬達控制器尚未連接，後端正在自動偵測。")

    def status(self) -> MotorStatus:
        with self._lock:
            if self._stepper is not None:
                try:
                    if not bool(self._stepper.getAttached()):
                        self.state.connected = False
                        self.state.engaged = False
                        self.state.moving = False
                        self.state.last_error = "馬達控制器尚未連接。"
                    else:
                        self.state.connected = True
                        self.state.command_position_deg = self.profile.steps_to_degrees(
                            float(self._stepper.getPosition())
                        )
                        hardware_moving = bool(self._stepper.getIsMoving())
                        if self._active_movement_generation is None:
                            self.state.moving = hardware_moving
                except Exception as exc:  # pragma: no cover - hardware dependent
                    logger.warning("Failed to refresh Phidget status: %s", exc)
                    self.state.connected = False
                    self.state.engaged = False
                    self.state.moving = False
                    self.state.last_error = "無法讀取馬達狀態。"
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
                holding_current_amp=self.settings.holding_current_amp,
                last_error=self.state.last_error,
            )

    def engage(self) -> MotorStatus:
        with self._lock:
            if self.state.moving:
                raise MotorError("馬達仍在停止中，請稍後再啟用。")
            try:
                self._require_connected()
                self._apply_profile()
                self._stepper.setEngaged(True)
            except MotorError:
                raise
            except Exception as exc:
                self.state.last_error = "啟用馬達失敗。"
                raise MotorError("啟用馬達失敗。") from exc
            self.state.engaged = True
            self.state.emergency_stopped = False
            self.state.last_error = None
            return self.status()

    def disengage(self) -> MotorStatus:
        with self._lock:
            self._require_connected()
            try:
                self._stepper.setEngaged(False)
            except Exception as exc:
                self.state.last_error = "釋放馬達失敗。"
                raise MotorError("釋放馬達失敗。") from exc
            self._movement_generation += 1
            self._active_movement_generation = None
            self.state.engaged = False
            self.state.moving = False
            return self.status()

    def set_origin(self) -> MotorStatus:
        with self._lock:
            self._require_connected()
            if self.state.moving:
                raise MotorError("馬達移動中，無法設定原點。")
            try:
                current_position_steps = float(self._stepper.getPosition())
                self._stepper.addPositionOffset(-current_position_steps)
            except Exception as exc:
                self.state.last_error = "設定馬達原點失敗。"
                raise MotorError("設定馬達原點失敗。") from exc
            self.state.command_position_deg = 0.0
            self.state.last_error = None
            return self.status()

    def move_to_angle(self, angle_deg: float) -> MotorStatus:
        with self._lock:
            self.safety.validate_angle(angle_deg)
            self._require_connected()
            if self.state.emergency_stopped:
                raise MotorError("馬達已緊急停止，請先重新啟用馬達。")
            if not self.state.engaged:
                raise MotorError("移動前請先啟用馬達。")
            if self.state.moving:
                raise MotorError("馬達正在移動中。")
            target_steps = self.profile.degrees_to_steps(angle_deg)
            try:
                self._stepper.setTargetPosition(target_steps)
            except Exception as exc:
                self.state.last_error = "無法送出馬達移動命令。"
                raise MotorError("無法送出馬達移動命令。") from exc
            self._movement_generation += 1
            generation = self._movement_generation
            self._active_movement_generation = generation
            stepper = self._stepper
            self.state.moving = True
        started = time.monotonic()
        try:
            while stepper.getIsMoving():
                if time.monotonic() - started > self.settings.movement_timeout_seconds:
                    with self._lock:
                        if generation == self._movement_generation:
                            self._movement_generation += 1
                            stepper.setTargetPosition(stepper.getPosition())
                            self.state.last_error = "馬達移動逾時。"
                    raise MotorError("馬達移動逾時。")
                time.sleep(0.05)
            with self._lock:
                if generation != self._movement_generation:
                    raise OperationCancelledError("馬達移動已停止。")
                self.state.command_position_deg = angle_deg
                self.state.moving = False
                self._active_movement_generation = None
                self.state.last_error = None
                return self.status()
        except (MotorError, OperationCancelledError):
            raise
        except Exception as exc:
            with self._lock:
                try:
                    stepper.setTargetPosition(stepper.getPosition())
                except Exception:
                    logger.exception("Failed to stop motor after movement failure")
                self.state.last_error = "馬達移動失敗。"
            raise MotorError("馬達移動失敗。") from exc
        finally:
            with self._lock:
                if self._active_movement_generation == generation:
                    self.state.moving = False
                    self._active_movement_generation = None

    def move_relative(self, delta_deg: float) -> MotorStatus:
        return self.move_to_angle(self.status().command_position_deg + delta_deg)

    def return_origin(self) -> MotorStatus:
        return self.move_to_angle(0.0)

    def stop(self) -> MotorStatus:
        with self._lock:
            self._require_connected()
            try:
                self._stepper.setTargetPosition(self._stepper.getPosition())
            except Exception as exc:
                self.state.last_error = "停止馬達失敗。"
                raise MotorError("停止馬達失敗。") from exc
            self._movement_generation += 1
            self._active_movement_generation = None
            self.state.moving = False
            return self.status()

    def emergency_stop(self) -> MotorStatus:
        with self._lock:
            self._require_connected()
            try:
                self._stepper.setTargetPosition(self._stepper.getPosition())
                self._stepper.setEngaged(False)
            except Exception as exc:
                self.state.last_error = "緊急停止馬達失敗。"
                raise MotorError("緊急停止馬達失敗。") from exc
            self._movement_generation += 1
            self._active_movement_generation = None
            self.state.moving = False
            self.state.engaged = False
            self.state.emergency_stopped = True
            return self.status()
