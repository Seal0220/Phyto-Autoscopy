from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, RLock, Thread

from app.core.config import AppSettings
from app.core.exceptions import PhytoAutoscopyError
from app.models.experiment_models import (
    AngleIntervalMode,
    CaptureMode,
    EqualDivisionsMode,
    ExperimentPlan,
    ExperimentStartRequest,
    ExperimentStatus,
    SecondsIntervalMode,
    SpecificAnglesMode,
)
from app.services.capture_service import CaptureService
from app.services.rotation_service import RotationService
from app.services.session_service import SessionService
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)


@dataclass
class ModeRuntime:
    mode: CaptureMode
    folder: str
    targets: list[float] = field(default_factory=list)
    captured_targets: set[float] = field(default_factory=set)
    next_due_seconds: float = 0.0
    capture_index: int = 0


class ExperimentService:
    def __init__(
        self,
        settings: AppSettings,
        sessions: SessionService,
        motor_controller,
        capture_service: CaptureService,
        rotation_service: RotationService,
        storage: StorageService,
    ) -> None:
        self.settings = settings
        self.sessions = sessions
        self.motor_controller = motor_controller
        self.capture_service = capture_service
        self.rotation_service = rotation_service
        self.storage = storage
        self.status = "idle"
        self.session_id: str | None = None
        self.cycle_count = 0
        self.last_error: str | None = None
        self.elapsed_seconds = 0.0
        self.duration_seconds: float | None = None
        self.current_angle_deg: float | None = None
        self.current_step_index = 0
        self.total_steps = 0
        self._runtimes: list[ModeRuntime] = []
        self._lock = RLock()
        self._stop_event = Event()
        self._pause_event = Event()
        self._worker: Thread | None = None

    def get_status(self) -> ExperimentStatus:
        with self._lock:
            return ExperimentStatus(
                status=self.status,
                session_id=self.session_id,
                cycle_count=self.cycle_count,
                last_error=self.last_error,
                elapsed_seconds=round(self.elapsed_seconds, 3),
                duration_seconds=self.duration_seconds,
                current_angle_deg=self.current_angle_deg,
                current_step_index=self.current_step_index,
                total_steps=self.total_steps,
                capture_count=sum(runtime.capture_index for runtime in self._runtimes),
                mode_progress=[
                    {
                        "id": runtime.mode.id,
                        "type": runtime.mode.type,
                        "capture_count": runtime.capture_index,
                    }
                    for runtime in self._runtimes
                ],
            )

    def _resolve_plan(self, request: ExperimentStartRequest | None) -> ExperimentPlan:
        request = request or ExperimentStartRequest()
        defaults = self.settings.experiment
        modes = request.modes or [
            SecondsIntervalMode(
                id="mode-1",
                type="seconds_interval",
                interval_seconds=defaults.capture_interval_seconds,
            )
        ]
        plan = ExperimentPlan(
            duration_seconds=(
                defaults.duration_minutes * 60
                if request.duration_seconds is None
                else request.duration_seconds
            ),
            rotation_start_deg=(
                defaults.rotation_start_deg
                if request.rotation_start_deg is None
                else request.rotation_start_deg
            ),
            rotation_end_deg=(
                defaults.rotation_end_deg
                if request.rotation_end_deg is None
                else request.rotation_end_deg
            ),
            rotation_step_deg=(
                defaults.rotation_step_deg
                if request.rotation_step_deg is None
                else request.rotation_step_deg
            ),
            angle_tolerance_deg=(
                defaults.angle_tolerance_deg
                if request.angle_tolerance_deg is None
                else request.angle_tolerance_deg
            ),
            capture_on_return=(
                defaults.capture_on_return
                if request.capture_on_return is None
                else request.capture_on_return
            ),
            modes=modes,
        )
        motor = self.settings.motor
        if (
            plan.rotation_start_deg < motor.minimum_angle_deg
            or plan.rotation_end_deg > motor.maximum_angle_deg
        ):
            raise PhytoAutoscopyError(
                "排程角度必須位於馬達設定的可用範圍內。"
            )
        return plan

    def _mode_folder(self, index: int, mode: CaptureMode) -> str:
        return f"{index:02d}_{mode.type}_{mode.id}"

    def _targets_for_mode(self, mode: CaptureMode, plan: ExperimentPlan) -> list[float]:
        start = plan.rotation_start_deg
        end = plan.rotation_end_deg
        if isinstance(mode, AngleIntervalMode):
            targets: list[float] = []
            current = start
            while current <= end + 1e-9:
                targets.append(round(current, 6))
                current += mode.interval_degrees
            return targets
        if isinstance(mode, SpecificAnglesMode):
            return sorted({round(angle, 6) for angle in mode.angles})
        if isinstance(mode, EqualDivisionsMode):
            if mode.points == 2:
                return [round(start, 6), round(end, 6)]
            spacing = (end - start) / (mode.points - 1)
            return [round(start + spacing * index, 6) for index in range(mode.points)]
        return []

    def _build_runtimes(self, plan: ExperimentPlan) -> list[ModeRuntime]:
        return [
            ModeRuntime(
                mode=mode,
                folder=self._mode_folder(index, mode),
                targets=self._targets_for_mode(mode, plan),
            )
            for index, mode in enumerate(plan.modes, start=1)
        ]

    def start(self, request: ExperimentStartRequest | None = None) -> ExperimentStatus:
        plan = self._resolve_plan(request)
        runtimes = self._build_runtimes(plan)
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                raise PhytoAutoscopyError("排程正在執行或停止中。")

            experiment_payload = plan.model_dump(mode="json")
            for payload, runtime in zip(experiment_payload["modes"], runtimes, strict=True):
                payload["output_folder"] = f"modes/{runtime.folder}"
                payload["log_file"] = f"modes/{runtime.folder}/capture_log.csv"

            session = self.sessions.create_session(
                status="running",
                experiment=experiment_payload,
            )
            for runtime in runtimes:
                self.storage.create_mode_layout(session.session_id, runtime.folder)

            self.status = "running"
            self.session_id = session.session_id
            self.cycle_count = 0
            self.last_error = None
            self.elapsed_seconds = 0.0
            self.duration_seconds = plan.duration_seconds
            self.current_angle_deg = None
            self.current_step_index = 0
            self.total_steps = len(
                self.rotation_service.schedule_capture_sequence(
                    plan.rotation_start_deg,
                    plan.rotation_end_deg,
                    plan.rotation_step_deg,
                    plan.capture_on_return,
                )
            )
            self._runtimes = runtimes
            self._stop_event.clear()
            self._pause_event.clear()
            self._worker = Thread(
                target=self._run,
                args=(session.session_id, plan, runtimes),
                name=f"experiment-{session.session_id}",
                daemon=True,
            )
            self._worker.start()
            return self.get_status()

    def pause(self) -> ExperimentStatus:
        with self._lock:
            if self.status != "running":
                raise PhytoAutoscopyError("只有執行中的排程可以暫停。")
            self._pause_event.set()
            self.status = "paused"
            if self.session_id:
                self.sessions.update_status(self.session_id, "paused")
            return self.get_status()

    def resume(self) -> ExperimentStatus:
        with self._lock:
            if self.status != "paused":
                raise PhytoAutoscopyError("只有已暫停的排程可以繼續。")
            self._pause_event.clear()
            self.status = "running"
            if self.session_id:
                self.sessions.update_status(self.session_id, "running")
            return self.get_status()

    def stop(self) -> ExperimentStatus:
        with self._lock:
            if self.status in {"idle", "completed", "failed"}:
                return self.get_status()
            self._stop_event.set()
            self._pause_event.clear()
            self.status = "stopping"
            session_id = self.session_id
            if session_id:
                self.sessions.update_status(session_id, "stopping")
            return self.get_status()

    def close(self) -> None:
        self._stop_event.set()
        self._pause_event.clear()
        worker = self._worker
        if worker is not None and worker.is_alive():
            worker.join(timeout=5)

    def _wait_while_paused(self) -> float:
        if not self._pause_event.is_set():
            return 0.0
        paused_at = time.monotonic()
        while self._pause_event.is_set() and not self._stop_event.wait(0.1):
            pass
        return time.monotonic() - paused_at

    def _selected_cameras(self) -> list[str]:
        experiment = self.settings.experiment
        selected = []
        if experiment.capture_top:
            selected.append("top")
        if experiment.capture_fixed_side:
            selected.append("fixed_side")
        if experiment.capture_rotating_arm:
            selected.append("rotating_arm")
        if not selected:
            raise PhytoAutoscopyError("請至少啟用一台擷取相機。")
        return selected

    def _due_targets(
        self,
        runtime: ModeRuntime,
        elapsed_seconds: float,
        actual_angle: float,
        tolerance: float,
    ) -> tuple[bool, list[float], str]:
        mode = runtime.mode
        if isinstance(mode, SecondsIntervalMode):
            if elapsed_seconds + 1e-9 < runtime.next_due_seconds:
                return False, [], ""
            due_at = runtime.next_due_seconds
            while runtime.next_due_seconds <= elapsed_seconds + 1e-9:
                runtime.next_due_seconds += mode.interval_seconds
            return True, [], f"{due_at:.3f}s"

        matched = [
            target
            for target in runtime.targets
            if target not in runtime.captured_targets
            and abs(actual_angle - target) <= tolerance + 1e-9
        ]
        if not matched:
            return False, [], ""
        runtime.captured_targets.update(matched)
        return True, matched, ",".join(f"{target:g}°" for target in matched)

    def _capture_modes(
        self,
        session_id: str,
        due_modes: list[tuple[ModeRuntime, list[float], str]],
        cycle_id: int,
        elapsed_seconds: float,
        commanded_angle: float,
        actual_angle: float,
        motion_direction: str,
        camera_ids: list[str],
    ) -> None:
        for runtime, _, _ in due_modes:
            runtime.capture_index += 1

        mode_outputs = [
            (runtime.folder, runtime.capture_index)
            for runtime, _, _ in due_modes
        ]

        for camera_id in camera_ids:
            results = {}
            capture_error = ""
            try:
                results = self.capture_service.capture_camera_for_modes(
                    camera_id,
                    session_id=session_id,
                    cycle_id=cycle_id,
                    angle_deg=actual_angle,
                    mode_outputs=mode_outputs,
                )
            except Exception as exc:
                capture_error = str(exc)
                logger.exception(
                    "Capture failed for session=%s camera=%s due_modes=%s",
                    session_id,
                    camera_id,
                    [runtime.mode.id for runtime, _, _ in due_modes],
                )

            for runtime, targets, trigger_value in due_modes:
                target_text = ",".join(f"{target:g}" for target in targets)
                reference_angle = (
                    min(targets, key=lambda target: abs(actual_angle - target))
                    if targets
                    else commanded_angle
                )
                result = results.get(runtime.folder)
                log_record = {
                    "mode_id": runtime.mode.id,
                    "mode_type": runtime.mode.type,
                    "cycle_id": cycle_id,
                    "motion_direction": motion_direction,
                    "capture_index": runtime.capture_index,
                    "elapsed_seconds": round(elapsed_seconds, 3),
                    "trigger_value": trigger_value,
                    "target_angle_deg": target_text,
                    "commanded_angle_deg": round(commanded_angle, 6),
                    "actual_angle_deg": round(actual_angle, 6),
                    "angle_error_deg": round(abs(actual_angle - reference_angle), 6),
                    "camera_id": camera_id,
                    "image_name": Path(result.file_path).name if result else "",
                    "file_path": result.file_path if result else "",
                    "captured_at": (
                        result.timestamp
                        if result
                        else datetime.now(timezone.utc).isoformat()
                    ),
                    "status": "success" if result else "error",
                    "error_message": "" if result else capture_error,
                }
                self.storage.append_mode_log(session_id, runtime.folder, log_record)

    def _run(
        self,
        session_id: str,
        plan: ExperimentPlan,
        runtimes: list[ModeRuntime],
    ) -> None:
        started_at = time.monotonic()
        paused_seconds = 0.0
        duration_seconds = plan.duration_seconds
        camera_ids: list[str] = []
        final_status = "completed"
        try:
            camera_ids = self._selected_cameras()
            self.motor_controller.engage()
            cycle_steps = self.rotation_service.schedule_capture_sequence(
                plan.rotation_start_deg,
                plan.rotation_end_deg,
                plan.rotation_step_deg,
                plan.capture_on_return,
            )
            cycle_id = 0

            while not self._stop_event.is_set():
                cycle_id += 1
                for runtime in runtimes:
                    runtime.captured_targets.clear()
                previous_direction: str | None = None
                with self._lock:
                    self.cycle_count = cycle_id

                for step_index, (commanded_angle, motion_direction) in enumerate(
                    cycle_steps,
                    start=1,
                ):
                    if self._stop_event.is_set():
                        break
                    paused_seconds += self._wait_while_paused()
                    if self._stop_event.is_set():
                        break

                    if motion_direction != previous_direction:
                        if motion_direction == "return":
                            for runtime in runtimes:
                                runtime.captured_targets.clear()
                        previous_direction = motion_direction

                    elapsed_seconds = time.monotonic() - started_at - paused_seconds
                    with self._lock:
                        self.elapsed_seconds = elapsed_seconds
                        self.current_angle_deg = commanded_angle
                        self.current_step_index = step_index
                    if elapsed_seconds > duration_seconds:
                        break

                    self.motor_controller.move_to_angle(commanded_angle)
                    delay_seconds = self.settings.experiment.stabilization_delay_ms / 1000
                    if delay_seconds > 0 and self._stop_event.wait(delay_seconds):
                        break

                    elapsed_seconds = time.monotonic() - started_at - paused_seconds
                    with self._lock:
                        self.elapsed_seconds = elapsed_seconds
                    if elapsed_seconds > duration_seconds:
                        break
                    actual_angle = float(self.motor_controller.status().command_position_deg)
                    if abs(actual_angle - commanded_angle) > plan.angle_tolerance_deg + 1e-9:
                        continue

                    due_modes: list[tuple[ModeRuntime, list[float], str]] = []
                    for runtime in runtimes:
                        due, targets, trigger_value = self._due_targets(
                            runtime,
                            elapsed_seconds,
                            actual_angle,
                            plan.angle_tolerance_deg,
                        )
                        if due:
                            due_modes.append((runtime, targets, trigger_value))
                    if due_modes:
                        self._capture_modes(
                            session_id,
                            due_modes,
                            cycle_id,
                            elapsed_seconds,
                            commanded_angle,
                            actual_angle,
                            motion_direction,
                            camera_ids,
                        )
                else:
                    self.motor_controller.return_origin()
                    with self._lock:
                        self.current_angle_deg = 0.0

                elapsed_seconds = time.monotonic() - started_at - paused_seconds
                if elapsed_seconds >= duration_seconds:
                    break

            if self._stop_event.is_set():
                final_status = "stopped"
        except Exception as exc:
            final_status = "failed"
            with self._lock:
                self.last_error = str(exc)
            logger.exception("Experiment schedule failed: %s", session_id)
        finally:
            try:
                if self.settings.experiment.return_to_origin and self.motor_controller.status().engaged:
                    self.motor_controller.return_origin()
            except Exception:
                logger.exception("Failed to return motor to origin after schedule")
            self.sessions.update_status(session_id, final_status)
            with self._lock:
                self.elapsed_seconds = min(
                    duration_seconds,
                    max(0.0, time.monotonic() - started_at - paused_seconds),
                )
                self.status = final_status
                self._worker = None
