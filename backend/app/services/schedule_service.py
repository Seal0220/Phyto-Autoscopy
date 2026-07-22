from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, RLock, Thread

from app.core.config import AppSettings
from app.core.constants import (
    CAPTURE_MODE_ABBREVIATIONS,
    CAPTURE_MODE_NAMES,
)
from app.core.exceptions import (
    CameraError,
    MotorError,
    OperationCancelledError,
    PhytoAutoscopyError,
    public_error_detail,
)
from app.models.schedule_models import (
    AngleIntervalMode,
    CaptureMode,
    ContinuousIntervalMode,
    EqualDivisionsMode,
    SchedulePlan,
    ScheduleStartRequest,
    ScheduleStatus,
    TimeIntervalMode,
    SpecificAnglesMode,
)
from app.services.capture_service import CaptureService
from app.services.rotation_service import RotationService
from app.services.record_service import RecordService
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
    scope_capture_index: int = 0


class ScheduleService:
    def __init__(
        self,
        settings: AppSettings,
        records: RecordService,
        motor_controller,
        capture_service: CaptureService,
        rotation_service: RotationService,
        storage: StorageService,
    ) -> None:
        self.settings = settings
        self.records = records
        self.motor_controller = motor_controller
        self.capture_service = capture_service
        self.rotation_service = rotation_service
        self.storage = storage
        self.status = "idle"
        self.rotation_enabled = False
        self.record_id: str | None = None
        self.cycle_count = 0
        self.total_cycles: int | None = None
        self.cycle_duration_seconds: float | None = None
        self.rotation_step_deg: float | None = None
        self.last_error: str | None = None
        self.elapsed_seconds = 0.0
        self.duration_seconds: float | None = None
        self.current_angle_deg: float | None = None
        self.current_step_index = 0
        self.total_steps = 0
        self._runtimes: list[ModeRuntime] = []
        self._lock = RLock()
        self._capture_lock = RLock()
        self._stop_event = Event()
        self._pause_event = Event()
        self._worker: Thread | None = None
        self.error_reporter = None

    def _reset_runtime_locked(self) -> None:
        self.status = "idle"
        self.rotation_enabled = False
        self.record_id = None
        self.cycle_count = 0
        self.total_cycles = None
        self.cycle_duration_seconds = None
        self.rotation_step_deg = None
        self.last_error = None
        self.elapsed_seconds = 0.0
        self.duration_seconds = None
        self.current_angle_deg = None
        self.current_step_index = 0
        self.total_steps = 0
        self._runtimes = []
        self._stop_event.clear()
        self._pause_event.clear()
        self._worker = None

    def get_status(self) -> ScheduleStatus:
        with self._lock:
            return ScheduleStatus(
                status=self.status,
                rotation_enabled=self.rotation_enabled,
                record_id=self.record_id,
                cycle_count=self.cycle_count,
                total_cycles=self.total_cycles,
                cycle_duration_seconds=self.cycle_duration_seconds,
                rotation_step_deg=self.rotation_step_deg,
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

    def _resolve_plan(self, request: ScheduleStartRequest | None) -> SchedulePlan:
        request = request or ScheduleStartRequest()
        defaults = self.settings.schedule
        rotation_enabled = (
            defaults.rotation_enabled
            if request.rotation_enabled is None
            else request.rotation_enabled
        )
        modes = request.modes or [
            (
                TimeIntervalMode(
                    id="mode-1",
                    type="time_interval",
                    interval_seconds=defaults.capture_interval_seconds,
                )
                if rotation_enabled
                else ContinuousIntervalMode(
                    id="mode-1",
                    type="continuous_interval",
                    interval_seconds=defaults.capture_interval_seconds,
                )
            )
        ]
        cycle_interval_seconds = (
            defaults.cycle_interval_seconds
            if request.cycle_interval_seconds is None
            else request.cycle_interval_seconds
        )
        rotation_start_deg = (
            defaults.rotation_start_deg
            if request.rotation_start_deg is None
            else request.rotation_start_deg
        )
        rotation_end_deg = (
            defaults.rotation_end_deg
            if request.rotation_end_deg is None
            else request.rotation_end_deg
        )
        motor = self.settings.motor
        if rotation_end_deg < rotation_start_deg:
            raise PhytoAutoscopyError("結束角度不可小於起始角度。")
        if (
            rotation_start_deg < motor.minimum_angle_deg
            or rotation_end_deg > motor.maximum_angle_deg
        ):
            raise PhytoAutoscopyError(
                "排程角度必須位於馬達設定的可用範圍內。"
            )
        capture_on_return = (
            defaults.capture_on_return
            if request.capture_on_return is None
            else request.capture_on_return
        )
        stabilization_delay_ms = (
            defaults.stabilization_delay_ms
            if request.stabilization_delay_ms is None
            else request.stabilization_delay_ms
        )
        return_to_origin = (
            defaults.return_to_origin
            if request.return_to_origin is None
            else request.return_to_origin
        )
        total_cycles = None
        cycle_duration_seconds = None
        if rotation_enabled:
            total_cycles = request.total_cycles or defaults.total_cycles
            cycle_duration_seconds = (
                request.cycle_duration_seconds
                or defaults.cycle_duration_seconds
            )
            duration_seconds = (
                total_cycles * cycle_duration_seconds
                + max(0, total_cycles - 1) * cycle_interval_seconds
            )
            rotation_step_deg = self._automatic_rotation_step(
                rotation_start_deg,
                rotation_end_deg,
                cycle_duration_seconds,
                capture_on_return,
                stabilization_delay_ms,
            )
        else:
            duration_seconds = (
                defaults.duration_seconds
                if request.duration_seconds is None
                else request.duration_seconds
            )
            cycle_interval_seconds = 0.0
            rotation_step_deg = defaults.rotation_step_deg

        plan = SchedulePlan(
            rotation_enabled=rotation_enabled,
            duration_seconds=duration_seconds,
            total_cycles=total_cycles,
            cycle_duration_seconds=cycle_duration_seconds,
            cycle_interval_seconds=cycle_interval_seconds,
            rotation_start_deg=rotation_start_deg,
            rotation_end_deg=rotation_end_deg,
            rotation_step_deg=rotation_step_deg,
            angle_tolerance_deg=(
                defaults.angle_tolerance_deg
                if request.angle_tolerance_deg is None
                else request.angle_tolerance_deg
            ),
            stabilization_delay_ms=stabilization_delay_ms,
            capture_on_return=capture_on_return,
            return_to_origin=return_to_origin,
            modes=modes,
        )
        return plan

    def _estimated_cycle_seconds(
        self,
        start_deg: float,
        end_deg: float,
        step_deg: float,
        capture_on_return: bool,
        stabilization_delay_ms: int,
    ) -> float:
        sequence = self.rotation_service.schedule_capture_sequence(
            start_deg,
            end_deg,
            step_deg,
            capture_on_return,
        )
        velocity = self.settings.motor.velocity_limit_deg_s
        if velocity <= 0:
            raise PhytoAutoscopyError(
                "馬達速度限制必須大於 0，才能自動計算步進度數。"
            )
        stabilization_seconds = stabilization_delay_ms / 1000
        current_angle = 0.0
        travel_degrees = 0.0
        for target_angle, _ in sequence:
            travel_degrees += abs(target_angle - current_angle)
            current_angle = target_angle
        travel_degrees += abs(current_angle)
        return (
            travel_degrees / velocity
            + len(sequence) * stabilization_seconds
        )

    def _automatic_rotation_step(
        self,
        start_deg: float,
        end_deg: float,
        cycle_duration_seconds: float,
        capture_on_return: bool,
        stabilization_delay_ms: int,
    ) -> float:
        angle_range = end_deg - start_deg
        maximum_step = max(0.1, angle_range)
        minimum_duration = self._estimated_cycle_seconds(
            start_deg,
            end_deg,
            maximum_step,
            capture_on_return,
            stabilization_delay_ms,
        )
        if cycle_duration_seconds + 1e-9 < minimum_duration:
            raise PhytoAutoscopyError(
                "每輪時長太短；依目前旋轉範圍、速度與穩定等待設定，"
                f"至少需要 {minimum_duration:.1f} 秒。"
            )
        minimum_step = min(0.1, maximum_step)
        if self._estimated_cycle_seconds(
            start_deg,
            end_deg,
            minimum_step,
            capture_on_return,
            stabilization_delay_ms,
        ) <= cycle_duration_seconds + 1e-9:
            return minimum_step

        lower = minimum_step
        upper = maximum_step
        for _ in range(50):
            candidate = (lower + upper) / 2
            if self._estimated_cycle_seconds(
                start_deg,
                end_deg,
                candidate,
                capture_on_return,
                stabilization_delay_ms,
            ) <= cycle_duration_seconds + 1e-9:
                upper = candidate
            else:
                lower = candidate
        return round(upper, 6)

    @staticmethod
    def _mode_folder(mode: CaptureMode, number: int) -> str:
        return f"{CAPTURE_MODE_NAMES[mode.type]}.{number:02d}"

    def _targets_for_mode(self, mode: CaptureMode, plan: SchedulePlan) -> list[float]:
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

    def _build_runtimes(self, plan: SchedulePlan) -> list[ModeRuntime]:
        mode_counts: dict[str, int] = {}
        runtimes = []
        for mode in plan.modes:
            mode_counts[mode.type] = mode_counts.get(mode.type, 0) + 1
            runtimes.append(
                ModeRuntime(
                    mode=mode,
                    folder=self._mode_folder(
                        mode,
                        mode_counts[mode.type],
                    ),
                    targets=self._targets_for_mode(mode, plan),
                )
            )
        return runtimes

    def start(self, request: ScheduleStartRequest | None = None) -> ScheduleStatus:
        plan = self._resolve_plan(request)
        if (
            plan.rotation_enabled
            and not self.motor_controller.status().connected
        ):
            raise PhytoAutoscopyError(
                "馬達控制器尚未連接，無法開始旋臂排程。"
            )
        runtimes = self._build_runtimes(plan)
        self._selected_cameras(plan)
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                raise PhytoAutoscopyError("排程正在執行或停止中。")

            schedule_payload = plan.model_dump(mode="json")
            for payload, runtime in zip(schedule_payload["modes"], runtimes, strict=True):
                continuous = isinstance(runtime.mode, ContinuousIntervalMode)
                payload["folder"] = runtime.folder
                payload["name"] = runtime.folder
                payload["abbreviation"] = CAPTURE_MODE_ABBREVIATIONS[
                    runtime.mode.type
                ]
                payload["storage_scope"] = (
                    "rounds/round.00"
                    if continuous
                    else "rounds"
                )
                payload["output_pattern"] = (
                    f"modes/{runtime.folder}/"
                    "rounds/round.00/snapshot.{snapshot}_"
                    "{YYYY.MM.DD-hh.mm.ss.xxxxxx}"
                    if continuous
                    else f"modes/{runtime.folder}/"
                    "rounds/round.{round}/snapshot.{snapshot}_"
                    "{YYYY.MM.DD-hh.mm.ss.xxxxxx}"
                )
                payload["image_pattern"] = (
                    "{camera}-"
                    f"{payload['abbreviation']}."
                    f"{runtime.folder.rsplit('.', 1)[1]}_"
                    "r.{round}_s.{snapshot}_"
                    "{YYYY.MM.DD-hh.mm.ss.xxxxxx}.jpg"
                )
                payload["log_pattern"] = (
                    f"modes/{runtime.folder}/mode.log.csv"
                )
                payload["metadata_pattern"] = (
                    f"modes/{runtime.folder}/metadata.csv"
                )
                payload["config_pattern"] = (
                    f"modes/{runtime.folder}/config.json"
                )

            record = None
            try:
                record = self.records.create_record(
                    status="running",
                    schedule=schedule_payload,
                )
            except Exception:
                if record is not None:
                    try:
                        self.records.update_status(record.record_id, "failed")
                    except Exception:
                        logger.exception(
                            "Failed to close partially created schedule record: %s",
                            record.record_id,
                        )
                self._reset_runtime_locked()
                raise

            self.status = "running"
            self.rotation_enabled = plan.rotation_enabled
            self.record_id = record.record_id
            self.cycle_count = 0
            self.total_cycles = plan.total_cycles
            self.cycle_duration_seconds = plan.cycle_duration_seconds
            self.rotation_step_deg = (
                plan.rotation_step_deg
                if plan.rotation_enabled
                else None
            )
            self.last_error = None
            self.elapsed_seconds = 0.0
            self.duration_seconds = plan.duration_seconds
            self.current_angle_deg = None
            self.current_step_index = 0
            self.total_steps = (
                len(
                    self.rotation_service.schedule_capture_sequence(
                        plan.rotation_start_deg,
                        plan.rotation_end_deg,
                        plan.rotation_step_deg,
                        plan.capture_on_return,
                    )
                )
                if plan.rotation_enabled
                else 0
            )
            self._runtimes = runtimes
            self._stop_event.clear()
            self._pause_event.clear()
            self._worker = Thread(
                target=self._run,
                args=(record.record_id, plan, runtimes),
                name=f"schedule-{record.record_id}",
                daemon=True,
            )
            try:
                self._worker.start()
            except Exception:
                try:
                    self.records.update_status(record.record_id, "failed")
                except Exception:
                    logger.exception(
                        "Failed to close schedule record after worker start failure: %s",
                        record.record_id,
                    )
                self._reset_runtime_locked()
                raise
            return self.get_status()

    def pause(self) -> ScheduleStatus:
        with self._lock:
            if self.status != "running":
                raise PhytoAutoscopyError("只有執行中的排程可以暫停。")
            self._pause_event.set()
            try:
                if self.record_id:
                    self.records.update_status(self.record_id, "paused")
            except Exception:
                self._pause_event.clear()
                raise
            self.status = "paused"
            return self.get_status()

    def resume(self) -> ScheduleStatus:
        with self._lock:
            if self.status != "paused":
                raise PhytoAutoscopyError("只有已暫停的排程可以繼續。")
            if self.record_id:
                self.records.update_status(self.record_id, "running")
            self._pause_event.clear()
            self.status = "running"
            return self.get_status()

    def stop(self) -> ScheduleStatus:
        with self._lock:
            if self.status in {"idle", "completed", "stopped", "failed", "stopping"}:
                return self.get_status()
            self._stop_event.set()
            self._pause_event.clear()
            self.status = "stopping"
            record_id = self.record_id
            if record_id:
                try:
                    self.records.update_status(record_id, "stopping")
                except Exception:
                    logger.exception("Failed to persist stopping state: %s", record_id)
        if self.rotation_enabled:
            self.motor_controller.stop()
        return self.get_status()

    def reset(self) -> ScheduleStatus:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                raise PhytoAutoscopyError("排程仍在執行或停止中，無法重設狀態。")
            self._reset_runtime_locked()
            return self.get_status()

    def close(self) -> None:
        self._stop_event.set()
        self._pause_event.clear()
        try:
            self.motor_controller.stop()
        except Exception:
            logger.exception("Failed to stop motor while closing schedule service")
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

    def _wait_without_capture(
        self,
        interval_seconds: float,
        started_at: float,
        paused_seconds: float,
        maximum_elapsed_seconds: float | None = None,
    ) -> tuple[float, bool]:
        remaining_seconds = interval_seconds
        while remaining_seconds > 1e-9:
            paused_seconds += self._wait_while_paused()
            if self._stop_event.is_set():
                return paused_seconds, False

            elapsed_seconds = time.monotonic() - started_at - paused_seconds
            with self._lock:
                self.elapsed_seconds = elapsed_seconds
            if (
                maximum_elapsed_seconds is not None
                and elapsed_seconds >= maximum_elapsed_seconds
            ):
                return paused_seconds, False

            wait_seconds = min(0.1, remaining_seconds)
            if maximum_elapsed_seconds is not None:
                wait_seconds = min(
                    wait_seconds,
                    maximum_elapsed_seconds - elapsed_seconds,
                )
            wait_started_at = time.monotonic()
            if self._stop_event.wait(wait_seconds):
                return paused_seconds, False
            remaining_seconds -= time.monotonic() - wait_started_at

        return paused_seconds, True

    def _selected_cameras(self, plan: SchedulePlan) -> list[str]:
        selected = ["top", "side"]
        if plan.rotation_enabled:
            selected.append("rotating")
        disabled = [
            camera_id
            for camera_id in selected
            if (
                self.settings.cameras.get(camera_id) is None
                or not self.settings.cameras[camera_id].enabled
            )
        ]
        if disabled:
            raise CameraError(
                f"排程選用的相機尚未啟用：{', '.join(disabled)}"
            )
        return selected

    def _due_targets(
        self,
        runtime: ModeRuntime,
        elapsed_seconds: float,
        actual_angle: float,
        tolerance: float,
    ) -> tuple[bool, list[float], str]:
        mode = runtime.mode
        if isinstance(mode, (ContinuousIntervalMode, TimeIntervalMode)):
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
        record_id: str,
        due_modes: list[tuple[ModeRuntime, list[float], str]],
        cycle_id: int,
        elapsed_seconds: float,
        commanded_angle: float,
        actual_angle: float,
        motion_direction: str,
        camera_ids: list[str],
    ) -> None:
        with self._capture_lock:
            self._capture_modes_locked(
                record_id,
                due_modes,
                cycle_id,
                elapsed_seconds,
                commanded_angle,
                actual_angle,
                motion_direction,
                camera_ids,
            )

    def _capture_modes_locked(
        self,
        record_id: str,
        due_modes: list[tuple[ModeRuntime, list[float], str]],
        cycle_id: int,
        elapsed_seconds: float,
        commanded_angle: float,
        actual_angle: float,
        motion_direction: str,
        camera_ids: list[str],
    ) -> None:
        snapshot_at = datetime.now(timezone.utc)
        for runtime, _, _ in due_modes:
            runtime.capture_index += 1
            runtime.scope_capture_index += 1

        mode_outputs = [
            (
                runtime.folder,
                runtime.scope_capture_index,
                isinstance(runtime.mode, ContinuousIntervalMode),
            )
            for runtime, _, _ in due_modes
        ]

        failed_cameras: list[str] = []
        for camera_id in camera_ids:
            results = {}
            capture_error = ""
            try:
                results = self.capture_service.capture_camera_for_modes(
                    camera_id,
                    record_id=record_id,
                    cycle_id=cycle_id,
                    angle_deg=actual_angle,
                    mode_outputs=mode_outputs,
                    snapshot_at=snapshot_at,
                )
            except Exception as exc:
                capture_error = public_error_detail(exc)
                failed_cameras.append(camera_id)
                logger.exception(
                    "Capture failed for record=%s camera=%s due_modes=%s",
                    record_id,
                    camera_id,
                    [runtime.mode.id for runtime, _, _ in due_modes],
                )

            for runtime, targets, trigger_value in due_modes:
                continuous = isinstance(
                    runtime.mode,
                    ContinuousIntervalMode,
                )
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
                    "cycle_id": 0 if continuous else cycle_id,
                    "motion_direction": motion_direction,
                    "capture_index": runtime.scope_capture_index,
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
                self.storage.append_mode_log(
                    record_id,
                    runtime.folder,
                    log_record,
                )

        if failed_cameras:
            raise CameraError(
                f"排程擷取失敗，相機：{', '.join(failed_cameras)}"
            )

    def _run_continuous_capture(
        self,
        record_id: str,
        plan: SchedulePlan,
        runtimes: list[ModeRuntime],
        camera_ids: list[str],
        started_at: float,
        done_event: Event,
        errors: list[Exception],
    ) -> None:
        paused_seconds = 0.0
        for runtime in runtimes:
            runtime.next_due_seconds = 0.0

        try:
            while (
                not done_event.is_set()
                and not self._stop_event.is_set()
            ):
                paused_seconds += self._wait_while_paused()
                if done_event.is_set() or self._stop_event.is_set():
                    break

                elapsed_seconds = time.monotonic() - started_at - paused_seconds
                if elapsed_seconds >= plan.duration_seconds:
                    break

                due_modes: list[tuple[ModeRuntime, list[float], str]] = []
                for runtime in runtimes:
                    due, targets, trigger_value = self._due_targets(
                        runtime,
                        elapsed_seconds,
                        0.0,
                        plan.angle_tolerance_deg,
                    )
                    if due:
                        due_modes.append((runtime, targets, trigger_value))

                if due_modes:
                    with self._lock:
                        cycle_id = max(1, self.cycle_count)
                        current_angle = self.current_angle_deg
                    actual_angle = (
                        float(current_angle)
                        if current_angle is not None
                        else float(
                            self.motor_controller.status().command_position_deg
                        )
                    )
                    self._capture_modes(
                        record_id,
                        due_modes,
                        cycle_id,
                        elapsed_seconds,
                        actual_angle,
                        actual_angle,
                        "continuous",
                        camera_ids,
                    )

                done_event.wait(0.05)
        except Exception as exc:
            errors.append(exc)
            self._stop_event.set()

    def _run_stationary_capture(
        self,
        record_id: str,
        plan: SchedulePlan,
        runtimes: list[ModeRuntime],
        camera_ids: list[str],
        started_at: float,
    ) -> float:
        paused_seconds = 0.0
        for runtime in runtimes:
            runtime.next_due_seconds = 0.0

        while not self._stop_event.is_set():
            paused_seconds += self._wait_while_paused()
            if self._stop_event.is_set():
                break

            elapsed_seconds = time.monotonic() - started_at - paused_seconds
            with self._lock:
                self.elapsed_seconds = elapsed_seconds
                self.current_angle_deg = None
            if elapsed_seconds >= plan.duration_seconds:
                break

            due_modes: list[tuple[ModeRuntime, list[float], str]] = []
            for runtime in runtimes:
                due, targets, trigger_value = self._due_targets(
                    runtime,
                    elapsed_seconds,
                    0.0,
                    plan.angle_tolerance_deg,
                )
                if due:
                    due_modes.append((runtime, targets, trigger_value))
            if due_modes:
                self._capture_modes(
                    record_id,
                    due_modes,
                    1,
                    elapsed_seconds,
                    0.0,
                    0.0,
                    "stationary",
                    camera_ids,
                )
            if self._stop_event.wait(0.1):
                break

        return paused_seconds

    def _run_rotation_cycles(
        self,
        record_id: str,
        plan: SchedulePlan,
        runtimes: list[ModeRuntime],
        camera_ids: list[str],
        started_at: float,
    ) -> float:
        paused_seconds = 0.0
        total_cycles = plan.total_cycles or 1
        cycle_duration_seconds = plan.cycle_duration_seconds or 0.0
        cycle_steps = self.rotation_service.schedule_capture_sequence(
            plan.rotation_start_deg,
            plan.rotation_end_deg,
            plan.rotation_step_deg,
            plan.capture_on_return,
        )

        for cycle_id in range(1, total_cycles + 1):
            if self._stop_event.is_set():
                break
            paused_seconds += self._wait_while_paused()
            if self._stop_event.is_set():
                break

            cycle_started_seconds = (
                time.monotonic() - started_at - paused_seconds
            )
            for runtime in runtimes:
                runtime.captured_targets.clear()
                runtime.scope_capture_index = 0
                if isinstance(runtime.mode, TimeIntervalMode):
                    runtime.next_due_seconds = cycle_started_seconds
            previous_direction: str | None = None
            completed_cycle = True
            with self._lock:
                self.cycle_count = cycle_id

            for step_index, (commanded_angle, motion_direction) in enumerate(
                cycle_steps,
                start=1,
            ):
                if self._stop_event.is_set():
                    completed_cycle = False
                    break
                paused_seconds += self._wait_while_paused()
                if self._stop_event.is_set():
                    completed_cycle = False
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

                self.motor_controller.move_to_angle(commanded_angle)
                stabilization_seconds = plan.stabilization_delay_ms / 1000
                if (
                    stabilization_seconds > 0
                    and self._stop_event.wait(stabilization_seconds)
                ):
                    completed_cycle = False
                    break

                elapsed_seconds = time.monotonic() - started_at - paused_seconds
                with self._lock:
                    self.elapsed_seconds = elapsed_seconds
                actual_angle = float(
                    self.motor_controller.status().command_position_deg
                )
                if (
                    abs(actual_angle - commanded_angle)
                    > plan.angle_tolerance_deg + 1e-9
                ):
                    raise MotorError(
                        f"馬達實際角度 {actual_angle:g} 度超出目標角度 "
                        f"{commanded_angle:g} 度的允許誤差。"
                    )

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
                        record_id,
                        due_modes,
                        cycle_id,
                        elapsed_seconds,
                        commanded_angle,
                        actual_angle,
                        motion_direction,
                        camera_ids,
                    )

            if not completed_cycle:
                break

            self.motor_controller.return_origin()
            with self._lock:
                self.current_angle_deg = 0.0

            elapsed_seconds = time.monotonic() - started_at - paused_seconds
            cycle_elapsed_seconds = elapsed_seconds - cycle_started_seconds
            remaining_cycle_seconds = max(
                0.0,
                cycle_duration_seconds - cycle_elapsed_seconds,
            )
            paused_seconds, continue_schedule = self._wait_without_capture(
                remaining_cycle_seconds,
                started_at,
                paused_seconds,
            )
            if not continue_schedule or cycle_id >= total_cycles:
                break

            paused_seconds, continue_schedule = self._wait_without_capture(
                plan.cycle_interval_seconds,
                started_at,
                paused_seconds,
            )
            if not continue_schedule:
                break

        return paused_seconds

    def _run(
        self,
        record_id: str,
        plan: SchedulePlan,
        runtimes: list[ModeRuntime],
    ) -> None:
        started_at = time.monotonic()
        paused_seconds = 0.0
        duration_seconds = plan.duration_seconds
        camera_ids: list[str] = []
        continuous_runtimes = [
            runtime
            for runtime in runtimes
            if isinstance(runtime.mode, ContinuousIntervalMode)
        ]
        cycle_runtimes = [
            runtime
            for runtime in runtimes
            if not isinstance(runtime.mode, ContinuousIntervalMode)
        ]
        continuous_done = Event()
        continuous_errors: list[Exception] = []
        continuous_worker: Thread | None = None
        final_status = "completed"
        background_error: BaseException | None = None
        try:
            camera_ids = self._selected_cameras(plan)
            if continuous_runtimes:
                continuous_worker = Thread(
                    target=self._run_continuous_capture,
                    args=(
                        record_id,
                        plan,
                        continuous_runtimes,
                        camera_ids,
                        started_at,
                        continuous_done,
                        continuous_errors,
                    ),
                    name=f"continuous-capture-{record_id}",
                    daemon=True,
                )
                continuous_worker.start()
            if plan.rotation_enabled:
                self.motor_controller.engage()
                paused_seconds = self._run_rotation_cycles(
                    record_id,
                    plan,
                    cycle_runtimes,
                    camera_ids,
                    started_at,
                )
            else:
                paused_seconds = self._run_stationary_capture(
                    record_id,
                    plan,
                    cycle_runtimes,
                    camera_ids,
                    started_at,
                )

            continuous_done.set()
            if continuous_worker is not None:
                continuous_worker.join(timeout=5)
            if continuous_errors:
                raise continuous_errors[0]
            if self._stop_event.is_set():
                final_status = "stopped"
        except OperationCancelledError as exc:
            if self._stop_event.is_set():
                final_status = "stopped"
            else:
                final_status = "failed"
                background_error = exc
                with self._lock:
                    self.last_error = public_error_detail(exc)
        except Exception as exc:
            final_status = "failed"
            background_error = exc
            with self._lock:
                self.last_error = public_error_detail(exc)
            logger.exception("Schedule failed: %s", record_id)
        finally:
            continuous_done.set()
            if (
                continuous_worker is not None
                and continuous_worker.is_alive()
            ):
                continuous_worker.join(timeout=5)
            cleanup_error: BaseException | None = None
            try:
                if (
                    plan.rotation_enabled
                    and plan.return_to_origin
                    and self.motor_controller.status().engaged
                ):
                    self.motor_controller.return_origin()
            except Exception as exc:
                cleanup_error = exc
                background_error = background_error or exc
                final_status = "failed"
                logger.exception("Failed to return motor to origin after schedule")
            try:
                self.records.update_status(record_id, final_status)
            except Exception as exc:
                cleanup_error = cleanup_error or exc
                background_error = background_error or exc
                final_status = "failed"
                logger.exception("Failed to persist final schedule state: %s", record_id)
                self.records.release_active_record(record_id)
            finally:
                with self._lock:
                    if final_status == "failed":
                        self.elapsed_seconds = min(
                            duration_seconds,
                            max(0.0, time.monotonic() - started_at - paused_seconds),
                        )
                        self.status = "failed"
                        if cleanup_error is not None:
                            self.last_error = public_error_detail(cleanup_error)
                        self._stop_event.clear()
                        self._pause_event.clear()
                        self._worker = None
                    else:
                        self._reset_runtime_locked()
                if (
                    final_status == "failed"
                    and background_error is not None
                    and not isinstance(background_error, OperationCancelledError)
                    and self.error_reporter is not None
                ):
                    self.error_reporter(public_error_detail(background_error))
