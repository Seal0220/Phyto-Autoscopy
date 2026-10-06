from __future__ import annotations

import csv
import json
import hashlib
import logging
import shutil
import traceback
import zipfile
from collections.abc import Callable, Iterable, Mapping
from copy import deepcopy
from pathlib import Path
from threading import Event, RLock
from time import monotonic
from typing import Any
from uuid import uuid4

import cv2
import numpy as np
from pydantic import ValidationError

from app.analysis import analysis_method
from app.analysis.analysis_runner import AnalysisJobManager
from app.analysis.artifacts import AnalysisArtifacts
from app.analysis.export.json_export import write_json_atomic
from app.analysis.intrinsics import (
    build_intrinsics_snapshot,
    undistort_analysis_views,
)
from app.analysis.image_probe import AnalysisImageProbe
from app.analysis.checkpoints import StepJournal, checkpoint_summary, step_signature
from app.analysis.intrinsics.undistortion_pipeline import ParallelUndistortionProcessor as UndistortionProcessor
from app.analysis.rounds import (
    RoundGroupingResult,
    evaluate_round_quality,
    group_analysis_rounds,
    select_round_reconstruction_views,
)
from app.analysis.rounds.paths import (
    round_artifact_directory,
    safe_artifact_name,
)
from app.analysis.reconstruction.backend import (
    unsupported_reconstruction_outputs,
)
from app.analysis.reconstruction import ReconstructionBackendRegistry
from app.analysis.reconstruction.reconstruction_worker import (
    run_reconstruction_worker,
)
from app.analysis.review import create_tip_correction
from app.analysis.pose_alignment import (
    align_dataset_camera_poses,
    evaluate_fixed_camera_pose_consistency,
)
from app.analysis.pose_alignment.markerless_pose import (
    align_markerless_camera_poses,
    estimate_fixed_stereo_pose,
    estimate_manual_stereo_pose,
    StereoPoseEstimationError,
)
from app.analysis.pose_alignment.model_reference import (
    aggregate_fixed_camera_poses, align_model_camera_poses, metric_model_registration, model_camera_pose,
    reference_space_fixed_poses,
)
from app.analysis.pose_alignment.model_review import model_review_reference, model_review_objects
from app.analysis.reconstruction.gsplat_trainer import PLANT_TRAINING_VERSION
from app.analysis.run_metadata import (
    next_dated_identifier,
    repository_commit,
    runtime_versions,
    utc_now_iso,
)
from app.analysis.source_scan import SourceScanManager
from app.analysis.record_validator import (
    ACTIVE_RECORD_STATUSES,
    BLOCKING_VALIDATION_ISSUE_CODES,
    CaptureRecordValidation,
    CaptureRecordValidator,
    ImageProbe,
)
from app.analysis.tip.pipeline import analyze_round_tip
from app.analysis.tip.trajectory_linker import (
    link_tip_trajectory,
    order_analysis_rounds,
)
from app.core.config import (
    AppSettings,
    BACKEND_ROOT,
    PoseAlignmentSettings,
)
from app.core.constants import CAPTURE_MODE_NAMES
from app.core.exceptions import (
    AnalysisError,
    AnalysisPausedError,
    AnalysisReviewRequiredError,
    OperationCancelledError,
    public_error_detail,
)
from app.models.analysis_models import (
    AnalysisCreateRequest,
    AnalysisRound,
    CameraPoseResult as AnalysisCameraPoseResult,
    AnalysisProgress,
    AnalysisProcessingPreview,
    AnalysisView,
    AnalysisRun,
    AnalysisSourceSummary,
    AnalysisSourceMode,
    AnalysisSourcePreview,
    AnalysisSourcePreviewRequest,
    AnalysisSourceScanStatus,
    MarkerlessPoseSettings,
    MINIMUM_MANUAL_STEREO_PAIRS,
    StereoPoseReviewRequest,
    ModelPoseReviewRequest,
    RoundModelResult,
    TipCorrection,
    TipCorrectionRequest,
    TipLandmark,
)
from app.models.calibration_models import CameraIntrinsics
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.capture_repository import CaptureRepository
from app.repositories.record_repository import RecordRepository


logger = logging.getLogger(__name__)


PROCESSING_STATUSES = frozenset({
    "validating",
    "processing",
    "reconstructing",
    "pausing",
})
TERMINAL_STATUSES = frozenset({
    "completed",
    "partially_completed",
    "failed",
    "cancelled",
})
SUPPORTED_ANALYSIS_METHODS = frozenset({
    "fixed",
    "rotating",
})
STATUS_LABELS = {
    "draft": "草稿",
    "validating": "驗證中",
    "pausing": "正在保存並暫停",
    "paused": "已暫停",
    "ready": "就緒",
    "processing": "處理中",
    "needs_review": "待人工檢查",
    "reviewing": "人工檢查中",
    "reconstructing": "三維重建中",
    "completed": "已完成",
    "partially_completed": "部分完成",
    "failed": "失敗",
    "cancelled": "已取消",
}

CAPTURE_MODE_LABELS = {
    "continuous_interval": "連續間隔擷取",
    "time_interval": "時間間隔擷取",
    "seconds_interval": "時間間隔擷取",
    "angle_interval": "角度間隔擷取",
    "specific_angles": "特定角度擷取",
    "equal_divisions": "等分擷取",
}

CAPTURE_MODE_CONFIGURATION_FIELDS = {
    "continuous_interval": ("interval_seconds",),
    "time_interval": ("interval_seconds",),
    "angle_interval": ("interval_degrees",),
    "specific_angles": ("angles",),
    "equal_divisions": ("points",),
}

CAPTURE_CONFIGURATION_FIELDS = (
    "rotation_enabled",
    "duration_seconds",
    "total_cycles",
    "cycle_interval_seconds",
    "rotation_start_deg",
    "rotation_end_deg",
    "angle_tolerance_deg",
    "stabilization_delay_ms",
    "capture_on_return",
    "return_to_origin",
    "arm_height_mm",
)


def _model_failed_round_keys(
    rounds: Iterable[AnalysisRound],
    models_by_round: Mapping[str, RoundModelResult],
    method_name: str,
) -> set[str]:
    if method_name != "rotating":
        return set()
    return {
        item.round_key
        for item in rounds
        if item.round_id != "round.00"
        and (
            item.round_key not in models_by_round
            or models_by_round[item.round_key].status != "completed"
        )
    }


def _deep_merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _status_label(status: str) -> str:
    return STATUS_LABELS.get(status, "未知狀態")


class AnalysisService:
    """Read-only capture analysis with a bounded, cooperative worker.

    All writes are restricted to the Analysis Run directory and SQLite analysis
    tables. The service never calls RecordService, because its legacy metadata
    recovery path is intentionally write-capable.
    """

    def __init__(
        self,
        settings: AppSettings,
        repository: AnalysisRepository,
        record_repository: RecordRepository,
        capture_repository: CaptureRepository,
        intrinsic_calibration_service: Any,
        progress_callback: Callable[[AnalysisProgress], None] | None = None,
        error_reporter: Callable[[str], None] | None = None,
        *,
        maximum_workers: int = 1,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.record_repository = record_repository
        self.capture_repository = capture_repository
        self.progress_callback = progress_callback
        self.error_reporter = error_reporter
        self.intrinsic_calibration_service = intrinsic_calibration_service
        self._lock = RLock()
        self._preview_lock = RLock()
        self._processing_previews: dict[str, AnalysisProcessingPreview | None] = {}
        self._validation_progress: dict[str, AnalysisProgress] = {}
        self._validation_progress_times: dict[str, float] = {}
        self._live_progress: dict[str, AnalysisProgress] = {}
        self._validator = CaptureRecordValidator()
        self._reconstruction_backends = ReconstructionBackendRegistry()
        self._runner = AnalysisJobManager(
            self._run_job,
            maximum_workers=maximum_workers,
        )
        self._source_scans = SourceScanManager(self._scan_sources)

    def _require_run(self, analysis_id: str) -> AnalysisRun:
        run = self.repository.get(analysis_id)
        if run is None:
            raise AnalysisError(f"找不到分析：{analysis_id}")
        return run

    def _require_completed_run(self, analysis_id: str) -> AnalysisRun:
        run = self._require_run(analysis_id)
        if run.status not in {"completed", "partially_completed"}:
            raise AnalysisError("分析完成後才能讀取重建結果。")
        return run

    def _require_record(self, record_id: str):
        record = self.record_repository.get(record_id)
        if record is None:
            raise AnalysisError(f"找不到紀錄：{record_id}")
        return record

    @staticmethod
    def _required_camera_ids(method: str) -> tuple[str, ...]:
        return (
            ("top", "side", "rotating")
            if method == "rotating"
            else ("top", "side")
        )

    def _snapshot_intrinsics(
        self,
        method: str,
        camera_resolutions: Mapping[str, tuple[int, int]],
    ) -> dict[str, dict[str, Any]]:
        try:
            available = {
                intrinsics.camera_id: intrinsics
                for intrinsics in self.intrinsic_calibration_service.list_intrinsics()
            }
        except Exception as error:
            raise AnalysisError(f"無法讀取相機內參：{error}") from error
        required = self._required_camera_ids(method)
        missing = [camera_id for camera_id in required if camera_id not in available]
        if missing:
            raise AnalysisError("分析缺少相機內參：" + ", ".join(missing))
        invalid = [
            camera_id
            for camera_id in required
            if available[camera_id].status != "valid"
            or available[camera_id].invalidation_reasons
        ]
        if invalid:
            raise AnalysisError(
                "下列相機內參已失效，請先重新校正：" + ", ".join(invalid)
            )
        snapshots = {}
        for camera_id in required:
            resolution = camera_resolutions.get(camera_id)
            if resolution is None:
                raise AnalysisError(f"紀錄缺少 {camera_id} 影像解析度。")
            try:
                snapshots[camera_id] = build_intrinsics_snapshot(
                    available[camera_id],
                    resolution,
                )
            except (TypeError, ValueError, cv2.error) as error:
                raise AnalysisError(
                    f"{camera_id} 影像解析度與內參不相容：{error}"
                ) from error
        return snapshots

    def _intrinsics_for_run(
        self,
        run: AnalysisRun,
    ) -> dict[str, CameraIntrinsics]:
        payload = run.intrinsics_snapshot
        if not payload:
            try:
                payload = self._artifacts(run).read_intrinsics_snapshot()
            except (OSError, ValueError) as error:
                raise AnalysisError("分析建立時固化的內參快照遺失。") from error
        try:
            intrinsics = {
                camera_id: CameraIntrinsics.model_validate({
                    key: item
                    for key, item in value.items()
                    if key in CameraIntrinsics.model_fields
                })
                for camera_id, value in payload.items()
            }
        except (TypeError, ValidationError) as error:
            raise AnalysisError(f"分析內參快照格式無效：{error}") from error
        missing = [
            camera_id
            for camera_id in self._required_camera_ids(run.method_name)
            if camera_id not in intrinsics
        ]
        if missing:
            raise AnalysisError("分析內參快照缺少：" + ", ".join(missing))
        return intrinsics

    @staticmethod
    def _pose_settings_for_run(run: AnalysisRun) -> PoseAlignmentSettings:
        try:
            return PoseAlignmentSettings.model_validate(
                run.parameters["pose_alignment"]
            )
        except (KeyError, ValidationError) as error:
            raise AnalysisError(f"分析姿態對齊設定無效：{error}") from error

    def _output_dir(self, run: AnalysisRun) -> Path:
        path = Path(run.output_path).resolve()
        root = self.settings.paths.analysis_dir.resolve()
        if (
            path.name != run.analysis_id
            or path.parent.name != (run.record_id or "custom")
            or path.parent.parent != root
        ):
            raise AnalysisError("分析紀錄的儲存位置無效。")
        return path

    def _artifacts(self, run: AnalysisRun) -> AnalysisArtifacts:
        return AnalysisArtifacts.create(self._output_dir(run))

    def _record_payload(self, record_id: str, record=None) -> dict[str, Any]:
        record = record if record is not None else self._require_record(record_id)
        record_path = Path(record.record_path)
        metadata_path = record_path / "config.json"
        if not metadata_path.exists():
            metadata_path = record_path / "record.json"
        if not metadata_path.exists():
            metadata_path = record_path / "session.json"
        if not metadata_path.exists():
            return {}
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, json.JSONDecodeError) as error:
            logger.warning(
                "Unable to read capture metadata for %s: %s",
                record_id,
                error,
            )
            return {}

    @staticmethod
    def _capture_configuration(payload: Mapping[str, Any]) -> dict[str, Any]:
        schedule = payload.get("schedule") or payload.get("experiment") or {}
        if not isinstance(schedule, Mapping):
            return {}
        return {
            key: schedule[key]
            for key in CAPTURE_CONFIGURATION_FIELDS
            if key in schedule
        }

    @staticmethod
    def _capture_image_count(payload: Mapping[str, Any]) -> int:
        summary = payload.get("capture_summary")
        if isinstance(summary, Mapping):
            try:
                count = max(0, int(summary.get("capture_count", 0)))
                if count > 0:
                    return count
            except (TypeError, ValueError):
                pass
        mode_summaries = payload.get("mode_summaries")
        if not isinstance(mode_summaries, list):
            return 0
        total = 0
        for mode_summary in mode_summaries:
            if not isinstance(mode_summary, Mapping):
                continue
            try:
                total += max(0, int(mode_summary.get("capture_count", 0)))
            except (TypeError, ValueError):
                continue
        return total

    @staticmethod
    def _capture_camera_counts(
        payload: Mapping[str, Any],
    ) -> dict[str, int] | None:
        def counts_from_summary(summary: Mapping[str, Any]) -> dict[str, int] | None:
            if summary.get("error"):
                return None
            status_counts = summary.get("status_counts")
            if isinstance(status_counts, Mapping):
                try:
                    if any(
                        int(count) > 0
                        for status, count in status_counts.items()
                        if status != "success"
                    ):
                        return None
                except (TypeError, ValueError):
                    return None
            raw_counts = summary.get("camera_counts")
            if not isinstance(raw_counts, Mapping):
                return None
            counts = {}
            for camera_id in ("top", "side", "rotating"):
                try:
                    counts[camera_id] = max(0, int(raw_counts.get(camera_id, 0)))
                except (TypeError, ValueError):
                    counts[camera_id] = 0
            return counts

        summary = payload.get("capture_summary")
        if isinstance(summary, Mapping):
            counts = counts_from_summary(summary)
            if counts is not None:
                return counts

        mode_summaries = payload.get("mode_summaries")
        if not isinstance(mode_summaries, list) or not mode_summaries:
            return None
        totals = {camera_id: 0 for camera_id in ("top", "side", "rotating")}
        for mode_summary in mode_summaries:
            if not isinstance(mode_summary, Mapping):
                return None
            counts = counts_from_summary(mode_summary)
            if counts is None:
                return None
            for camera_id in totals:
                totals[camera_id] += counts[camera_id]
        return totals

    def _record_modes(
        self,
        record_id: str,
        payload: Mapping[str, Any] | None = None,
    ) -> list[AnalysisSourceMode]:
        record_payload = payload if payload is not None else self._record_payload(record_id)
        schedule = (
            record_payload.get("schedule")
            or record_payload.get("experiment")
            or {}
        )
        raw_modes = schedule.get("modes", []) if isinstance(schedule, dict) else []
        raw_summaries = record_payload.get("mode_summaries", [])
        summaries_by_folder = {
            str(summary.get("folder") or "").strip(): summary
            for summary in raw_summaries
            if isinstance(summary, dict)
            and str(summary.get("folder") or "").strip()
        } if isinstance(raw_summaries, list) else {}
        modes = []
        seen_ids = set()
        mode_counts: dict[str, int] = {}
        for index, raw_mode in enumerate(raw_modes, start=1):
            if not isinstance(raw_mode, dict):
                continue
            mode_id = str(raw_mode.get("id") or f"capture-{index:02d}").strip()
            mode_type = str(raw_mode.get("type") or "unknown").strip()
            if not mode_id or mode_id in seen_ids:
                continue
            mode_counts[mode_type] = mode_counts.get(mode_type, 0) + 1
            folder = str(raw_mode.get("folder") or "").strip()
            if not folder and raw_mode.get("output_folder"):
                folder = Path(str(raw_mode["output_folder"])).name
            if not folder:
                mode_name = CAPTURE_MODE_NAMES.get(mode_type, "CaptureMode")
                folder = f"{mode_name}.{mode_counts[mode_type]:02d}"
            storage_scope = str(raw_mode.get("storage_scope") or "").strip()
            if not storage_scope:
                storage_scope = (
                    "rounds/round.00"
                    if mode_type == "continuous_interval"
                    else "rounds"
                )
            configuration = {
                key: raw_mode[key]
                for key in CAPTURE_MODE_CONFIGURATION_FIELDS.get(mode_type, ())
                if key in raw_mode
            }
            summary = summaries_by_folder.get(folder, {})
            try:
                image_count = max(0, int(summary.get("capture_count", 0)))
            except (TypeError, ValueError):
                image_count = 0
            modes.append(
                AnalysisSourceMode(
                    id=mode_id,
                    type=mode_type,
                    label=CAPTURE_MODE_LABELS.get(mode_type, "擷取模式"),
                    folder=folder,
                    storage_scope=storage_scope,
                    configuration=configuration,
                    image_count=image_count,
                )
            )
            seen_ids.add(mode_id)
        return modes

    def _selected_mode_folders(
        self,
        record_id: str,
        mode_ids: Iterable[str],
    ) -> tuple[str, ...]:
        selected_ids = tuple(mode_ids)
        if not selected_ids:
            return ()
        available = {mode.id: mode for mode in self._record_modes(record_id)}
        unknown = [mode_id for mode_id in selected_ids if mode_id not in available]
        if unknown:
            raise AnalysisError(
                "選取的擷取模式不存在：" + "、".join(unknown)
            )
        return tuple(available[mode_id].folder for mode_id in selected_ids)

    def _validation_for_record(
        self,
        record_id: str,
        *,
        method: str = "fixed",
        mode_ids: Iterable[str] = (),
        progress_callback: Callable[[int, int], None] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
        image_probe: ImageProbe | None = None,
    ) -> CaptureRecordValidation:
        record = self._require_record(record_id)
        captures = self.capture_repository.list_by_record(record_id)
        validator = (
            CaptureRecordValidator(image_probe=image_probe)
            if image_probe is not None
            else self._validator
        )
        return validator.validate(
            record,
            captures,
            required_camera_ids=(
                ("top", "side", "rotating")
                if method == "rotating"
                else ("top", "side")
            ),
            selected_mode_folders=self._selected_mode_folders(
                record_id,
                mode_ids,
            ),
            progress_callback=progress_callback,
            cancel_requested=cancel_requested,
        )

    def _round_grouping(
        self,
        validation: CaptureRecordValidation,
        *,
        analysis_id: str,
        record_id: str,
        mode_ids: Iterable[str],
        method: str,
        enabled_camera_ids: Iterable[str],
        input_manifest: Iterable[Mapping[str, Any]] = (),
    ) -> RoundGroupingResult:
        selected_ids = tuple(mode_ids)
        available = {mode.id: mode for mode in self._record_modes(record_id)}
        mode_ids_by_folder = {
            available[mode_id].folder: mode_id
            for mode_id in selected_ids
            if mode_id in available
        }
        image_hashes = {
            int(item["input_id"]): str(item.get("sha256") or "")
            for item in input_manifest
            if isinstance(item, Mapping) and item.get("input_id") is not None
        }
        return group_analysis_rounds(
            analysis_id=analysis_id,
            record_id=record_id,
            frames=validation.frames,
            mode_ids_by_folder=mode_ids_by_folder,
            method=method,
            enabled_camera_ids=tuple(enabled_camera_ids),
            image_hashes=image_hashes,
        )

    def _validation_for_run(
        self,
        run: AnalysisRun,
        *,
        progress_callback: Callable[[int, int], None] | None = None,
        image_probe: ImageProbe | None = None,
    ) -> CaptureRecordValidation:
        if run.method_name not in SUPPORTED_ANALYSIS_METHODS:
            raise AnalysisError("找不到分析紀錄。")
        if not run.record_id:
            raise AnalysisError("分析紀錄缺少捕捉紀錄 ID。")
        mode_ids = run.parameters.get("mode_ids", [])
        if not isinstance(mode_ids, list):
            raise AnalysisError("分析擷取模式清單格式無效。")
        probe = image_probe or AnalysisImageProbe(self._artifacts(run).root / "image_cache")
        try:
            return self._validation_for_record(
                run.record_id,
                method=run.method_name,
                mode_ids=mode_ids,
                progress_callback=progress_callback,
                image_probe=probe,
            )
        finally:
            if image_probe is None:
                probe.close()

    @staticmethod
    def _manifest(
        validation: CaptureRecordValidation,
        *,
        progress_callback: Callable[[int, int], None] | None = None,
        hashes: Mapping[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        result = []
        total = len(validation.frames)
        if progress_callback is not None:
            progress_callback(0, total)
        for index, frame in enumerate(validation.frames, start=1):
            stat = frame.file_path.stat()
            result.append({
                "input_id": frame.capture_id,
                "camera_id": frame.camera_id,
                "original_camera_id": frame.original_camera_id,
                "timestamp": frame.timestamp,
                "cycle_id": frame.cycle_id,
                "angle_deg": frame.angle_deg,
                "motor_position_deg": frame.motor_position_deg,
                "capture_group": frame.capture_group,
                "relative_path": frame.relative_path,
                "absolute_path": str(frame.file_path),
                "resolution": list(frame.resolution or ()),
                "size_bytes": stat.st_size,
                "modified_ns": stat.st_mtime_ns,
                "sha256": hashes[str(frame.file_path)] if hashes is not None else _sha256(frame.file_path),
            })
            if progress_callback is not None and (index % 32 == 0 or index == total):
                progress_callback(index, total)
        return result

    @staticmethod
    def _blocking_validation_messages(
        validation: CaptureRecordValidation,
    ) -> list[str]:
        return list(dict.fromkeys(
            issue.message
            for issue in validation.issues
            if issue.code in BLOCKING_VALIDATION_ISSUE_CODES
        ))

    @staticmethod
    def _validation_issue_payloads(
        validation: CaptureRecordValidation,
    ) -> list[dict[str, Any]]:
        return [
            {
                "code": issue.code,
                "message": issue.message,
                "blocking": (
                    issue.code in BLOCKING_VALIDATION_ISSUE_CODES
                ),
                "camera_id": issue.camera_id,
                "capture_id": issue.capture_id,
                "file_path": issue.file_path,
            }
            for issue in validation.issues
        ]

    def list_sources(self) -> list[AnalysisSourceSummary]:
        results = []
        for record in self.record_repository.list():
            record_payload = self._record_payload(record.record_id, record=record)
            available_modes = self._record_modes(
                record.record_id,
                record_payload,
            )
            capture_configuration = self._capture_configuration(record_payload)
            total_image_count = self._capture_image_count(record_payload)
            counts = self._capture_camera_counts(record_payload)
            if counts is None:
                counts = self.capture_repository.successful_camera_counts(
                    record.record_id,
                )
            top_count = counts.get("top", 0)
            side_count = counts.get("side", 0)
            rotating_count = counts.get("rotating", 0)
            if not total_image_count:
                total_image_count = top_count + side_count + rotating_count
            reasons = []
            if record.status in ACTIVE_RECORD_STATUSES:
                reasons.append("紀錄仍在擷取中。")
            if not Path(record.record_path).is_dir():
                reasons.append("找不到紀錄目錄。")
            if not top_count:
                reasons.append("缺少俯視角影像。")
            if not side_count:
                reasons.append("缺少側視角影像。")
            results.append(
                AnalysisSourceSummary(
                    record_id=record.record_id,
                    created_at=record.created_at,
                    ended_at=record.ended_at,
                    status=record.status,
                    record_path=record.record_path,
                    top_frame_count=top_count,
                    side_frame_count=side_count,
                    rotating_frame_count=rotating_count,
                    total_image_count=total_image_count,
                    camera_resolutions={},
                    camera_directories={},
                    capture_configuration=capture_configuration,
                    ready=not reasons,
                    not_ready_reasons=reasons,
                    available_modes=available_modes,
                    analysis_runs=[],
                )
            )
        return results

    def preview_sources(
        self,
        request: AnalysisSourcePreviewRequest,
        *,
        progress_callback: Callable[[int, int], None] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
        image_probe: ImageProbe | None = None,
    ) -> AnalysisSourcePreview:
        validation = self._validation_for_record(
            request.record_id,
            method=request.method,
            mode_ids=request.mode_ids,
            progress_callback=progress_callback,
            cancel_requested=cancel_requested,
            image_probe=image_probe,
        )
        if cancel_requested is not None and cancel_requested():
            raise InterruptedError("影像掃描已取消。")
        enabled_camera_ids = tuple(
            camera_id
            for camera_id, source in request.camera_sources.items()
            if source.enabled
        )
        grouping = self._round_grouping(
            validation,
            analysis_id="preview",
            record_id=request.record_id,
            mode_ids=request.mode_ids,
            method=request.method,
            enabled_camera_ids=enabled_camera_ids,
        )
        validation_errors = list(validation.not_ready_reasons)
        validation_warnings = [
            issue.message
            for issue in validation.issues
            if issue.code not in BLOCKING_VALIDATION_ISSUE_CODES
        ]
        all_errors = list(dict.fromkeys([*validation_errors, *grouping.errors]))
        errors = all_errors[:10]
        if len(all_errors) > len(errors):
            errors.append(f"另有 {len(all_errors) - len(errors)} 項錯誤未逐項顯示。")
        ready_rounds = grouping.ready_round_count
        intrinsics_readiness: dict[str, dict[str, Any]] = {}
        try:
            available_intrinsics = {
                item.camera_id: item
                for item in self.intrinsic_calibration_service.list_intrinsics()
            }
        except Exception as error:
            available_intrinsics = {}
            errors.append(f"無法讀取相機內參：{error}")
        for camera_id in enabled_camera_ids:
            intrinsics = available_intrinsics.get(camera_id)
            intrinsics_readiness[camera_id] = {
                "ready": bool(
                    intrinsics
                    and intrinsics.status == "valid"
                    and not intrinsics.invalidation_reasons
                ),
                "camera_model": intrinsics.camera_model if intrinsics else None,
                "width": intrinsics.width if intrinsics else None,
                "height": intrinsics.height if intrinsics else None,
                "reprojection_error_px": (
                    intrinsics.reprojection_error_px if intrinsics else None
                ),
                "updated_at": intrinsics.updated_at if intrinsics else None,
                "reasons": (
                    list(intrinsics.invalidation_reasons)
                    if intrinsics
                    else ["尚未建立有效內參。"]
                ),
            }
        pose_readiness = {
            "intrinsics_ready": all(
                item["ready"] for item in intrinsics_readiness.values()
            ),
            "scale_source": "measured_stereo_baseline",
            "stereo_pose_estimated": False,
            "note": "雙鏡頭姿態會在分析時由共同影像特徵估算；毫米尺度須輸入實測基線。",
        }
        backend_readiness = self._reconstruction_backends.check(
            self.settings.reconstruction.backend
        )
        detail_limit = 100
        incomplete_details = [
            item for item in grouping.readiness if item.status == "incomplete"
        ]
        round_readiness = incomplete_details[:detail_limit]
        if len(round_readiness) < detail_limit:
            for item in grouping.readiness:
                if len(round_readiness) >= detail_limit:
                    break
                if item.status != "incomplete":
                    round_readiness.append(item)
        omitted_round_count = max(0, len(grouping.readiness) - len(round_readiness))
        warnings = list(dict.fromkeys([
            *validation_warnings,
            *grouping.warnings,
        ]))
        if len(warnings) > 5:
            omitted_warning_count = len(warnings) - 5
            warnings = [*warnings[:5], f"另有 {omitted_warning_count} 項警告未逐項顯示。"]
        return AnalysisSourcePreview(
            ready=not errors and ready_rounds > 0,
            camera_frame_counts={
                "top": validation.top_frame_count,
                "side": validation.side_frame_count,
                "rotating": validation.rotating_frame_count,
            },
            camera_resolutions=dict(validation.camera_resolutions),
            camera_directories=dict(validation.camera_directories),
            errors=errors,
            warnings=warnings,
            round_count=len(grouping.rounds),
            ready_round_count=ready_rounds,
            incomplete_round_count=grouping.incomplete_round_count,
            total_view_count=len(grouping.views),
            round_readiness=round_readiness,
            omitted_round_count=omitted_round_count,
            intrinsics_readiness=intrinsics_readiness,
            pose_readiness=pose_readiness,
            backend_readiness=backend_readiness,
        )

    def _scan_sources(
        self,
        request: AnalysisSourcePreviewRequest,
        progress_callback: Callable[[int, int], None],
        cancel_requested: Callable[[], bool],
    ) -> AnalysisSourcePreview:
        image_probe = AnalysisImageProbe(
            self.settings.paths.analysis_dir.parent / "temp" / "analysis_images" / request.record_id
        )
        preview = self.preview_sources(
            request,
            progress_callback=progress_callback,
            cancel_requested=cancel_requested,
            image_probe=image_probe,
        )
        preview.image_probe_backends = image_probe.backend_counts
        return preview

    def start_source_scan(
        self,
        request: AnalysisSourcePreviewRequest,
    ) -> AnalysisSourceScanStatus:
        return self._source_scans.start(request)

    def get_source_scan(self, scan_id: str) -> AnalysisSourceScanStatus:
        return self._source_scans.get(scan_id)

    def cancel_source_scan(self, scan_id: str) -> AnalysisSourceScanStatus:
        return self._source_scans.cancel(scan_id)

    def list_runs(self, record_id: str | None = None) -> list[AnalysisRun]:
        return self.repository.list(record_id)

    def list_reconstruction_backends(self) -> list[dict[str, Any]]:
        return self._reconstruction_backends.list_readiness()

    def _new_analysis_parameters(
        self,
        incoming: Mapping[str, Any],
        *,
        method: str,
    ) -> dict[str, Any]:
        defaults = {
            "reconstruction": {
                **self.settings.reconstruction.model_dump(mode="json"),
                "export_gaussians": True,
                "export_plant_gaussians": True,
                "export_background_gaussians": False,
                "export_point_cloud": True,
                "export_plant_point_cloud": True,
                "export_render_preview": True,
            },
            "pose_strategy": {},
            "background": {
                "generate_plant_mask": True,
                "use_plant_mask_in_loss": True,
                "preserve_scene_model": True,
                "export_plant_model": True,
                "save_background_model": False,
            },
            "tip_analysis": {
                "minimum_confidence": 0.7,
                "minimum_supporting_views": 2,
                "maximum_reprojection_error_px": 5.0,
                "use_skeleton_refinement": True,
                "use_temporal_prior": True,
                "wait_for_low_confidence_review": True,
                "export_all_2d_candidates": False,
                "save_reprojection_overlays": True,
            },
            "outputs": {
                "save_gaussian_model": True,
                "export_scene_point_cloud": True,
                "export_plant_point_cloud": True,
                "export_skeleton": True,
                "export_tip_markers": True,
                "export_trajectory_csv": True,
                "save_model_previews": True,
                "save_diagnostics": True,
                "save_checkpoints": True,
            },
            "advanced": {},
        }
        merged = _deep_merge(defaults, dict(incoming))
        try:
            markerless = MarkerlessPoseSettings.model_validate(
                merged.get("pose_strategy")
            )
        except ValidationError as error:
            raise AnalysisError(
                "無標記姿態設定無效；請確認實測距離、高度與姿態門檻。"
            ) from error
        merged["pose_strategy"] = markerless.model_dump(mode="json")
        raw_reconstruction = merged.get("reconstruction")
        if not isinstance(raw_reconstruction, Mapping):
            raise AnalysisError("三維模型設定格式無效。")
        background = merged.get("background")
        if not isinstance(background, Mapping):
            raise AnalysisError("背景處理設定格式無效。")
        outputs = merged.get("outputs")
        if not isinstance(outputs, Mapping):
            raise AnalysisError("分析輸出設定格式無效。")
        builds_round_models = method == "rotating"
        saves_gaussian_model = bool(
            outputs.get("save_gaussian_model", True)
        )
        reconstruction = {
            **dict(raw_reconstruction),
            "export_gaussians": (
                builds_round_models
                and saves_gaussian_model
                and bool(background.get("preserve_scene_model", True))
            ),
            "export_plant_gaussians": (
                builds_round_models
                and saves_gaussian_model
                and bool(background.get("export_plant_model", True))
            ),
            "export_background_gaussians": (
                builds_round_models
                and saves_gaussian_model
                and bool(background.get("save_background_model", False))
            ),
            "export_point_cloud": builds_round_models,
            "retain_scene_point_cloud": (
                builds_round_models
                and bool(outputs.get("export_scene_point_cloud", True))
            ),
            "export_plant_point_cloud": (
                builds_round_models
                and bool(outputs.get("export_plant_point_cloud", True))
            ),
            "export_render_preview": (
                builds_round_models
                and bool(outputs.get("save_model_previews", True))
            ),
            "save_checkpoint": (
                builds_round_models
                and bool(outputs.get("save_checkpoints", True))
            ),
            "use_plant_mask": (
                builds_round_models
                and bool(background.get("use_plant_mask_in_loss", True))
            ),
        }
        merged["reconstruction"] = reconstruction
        backend = str(reconstruction.get("backend") or "")
        if backend not in self.settings.reconstruction.available_backends:
            raise AnalysisError(f"不支援的三維模型後端：{backend}")
        quality = str(reconstruction.get("quality_preset") or "")
        if quality not in {"preview", "standard", "high"}:
            raise AnalysisError("模型品質只能使用預覽、標準或高品質。")
        preset_steps = {"preview": 3000, "standard": 10000, "high": 30000}
        preset_factors = {"preview": 4, "standard": 2, "high": 1}
        iterations = reconstruction.get("training_iterations", preset_steps[quality])
        image_factor = reconstruction.get("image_factor", preset_factors[quality])
        if (
            isinstance(iterations, bool)
            or not isinstance(iterations, int)
            or not 500 <= iterations <= 100000
        ):
            raise AnalysisError("模型訓練步數必須介於 500 與 100000。")
        if isinstance(image_factor, bool) or image_factor not in {1, 2, 4, 8}:
            raise AnalysisError("訓練影像縮小倍率只能是 1、2、4 或 8。")
        reconstruction["training_iterations"] = iterations
        reconstruction["image_factor"] = image_factor
        capabilities = self._reconstruction_backends.get(
            backend
        ).capabilities
        requested_capabilities = {
            "scene_gaussian_export": bool(
                reconstruction.get("export_gaussians", True)
            ),
            "plant_gaussian_export": bool(
                reconstruction.get("export_plant_gaussians", True)
            ),
            "background_gaussian_export": bool(
                reconstruction.get(
                    "export_background_gaussians",
                    False,
                )
            ),
            "scene_point_cloud_export": bool(
                reconstruction.get("export_point_cloud", True)
            ),
            "render_preview_export": bool(
                reconstruction.get("export_render_preview", True)
            ),
        }
        unsupported_outputs = unsupported_reconstruction_outputs(
            capabilities,
            requested_capabilities,
        )
        if unsupported_outputs:
            raise AnalysisError(
                "所選模型後端不支援要求的輸出："
                + "、".join(unsupported_outputs)
            )
        requires_plant_masks = any((
            bool(reconstruction.get("export_plant_gaussians", False)),
            bool(
                reconstruction.get(
                    "export_background_gaussians",
                    False,
                )
            ),
            bool(reconstruction.get("export_plant_point_cloud", False)),
            builds_round_models,
        ))
        if (
            requires_plant_masks
            and not bool(background.get("generate_plant_mask", True))
        ):
            raise AnalysisError(
                "純植物或背景輸出必須先啟用植物遮罩。"
            )
        tip = merged.get("tip_analysis")
        if not isinstance(tip, Mapping):
            raise AnalysisError("尖端標記設定格式無效。")
        try:
            confidence = float(tip["minimum_confidence"])
            support = int(tip["minimum_supporting_views"])
            reprojection = float(tip["maximum_reprojection_error_px"])
        except (KeyError, TypeError, ValueError) as error:
            raise AnalysisError("尖端標記門檻必須是有效數值。") from error
        if not 0 <= confidence <= 1:
            raise AnalysisError("最低尖端標記信心必須介於 0 與 1。")
        if support < 2:
            raise AnalysisError("尖端標記至少需要兩個支持視角。")
        if reprojection <= 0:
            raise AnalysisError("最大尖端標記重投影誤差必須大於 0。")
        return merged

    def get_run(self, analysis_id: str) -> AnalysisRun:
        return self._require_run(analysis_id)

    def list_rounds(self, analysis_id: str):
        self._require_run(analysis_id)
        return self.repository.list_rounds(analysis_id)

    def list_views(
        self,
        analysis_id: str,
        round_key: str | None = None,
    ):
        self._require_run(analysis_id)
        return self.repository.list_views(analysis_id, round_key)

    def list_round_models(self, analysis_id: str) -> list[RoundModelResult]:
        self._require_run(analysis_id)
        return self.repository.list_round_models(analysis_id)

    def list_tip_landmarks(self, analysis_id: str) -> list[TipLandmark]:
        self._require_run(analysis_id)
        return self.repository.list_tip_landmarks(analysis_id)

    def list_tip_observations(
        self,
        analysis_id: str,
        round_key: str | None = None,
    ):
        self._require_run(analysis_id)
        return self.repository.list_tip_observations(
            analysis_id,
            round_key,
        )

    def list_tip_trajectory(
        self,
        analysis_id: str,
        mode_id: str | None = None,
    ):
        self._require_run(analysis_id)
        return self.repository.list_tip_trajectory(
            analysis_id,
            mode_id,
        )

    def get_tip_trajectory_quality(
        self,
        analysis_id: str,
    ) -> dict[str, Any]:
        path = self.get_artifact_path(
            analysis_id,
            "trajectory/trajectory_quality.json",
        )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise AnalysisError(f"尖端標記軌跡品質無法讀取：{error}") from error
        if not isinstance(payload, dict):
            raise AnalysisError("尖端標記軌跡品質格式無效。")
        return payload

    def get_artifact_path(
        self,
        analysis_id: str,
        artifact_path: str,
    ) -> Path:
        run = self._require_image_context(analysis_id)
        root = self._artifacts(run).root.resolve()
        candidate = (root / artifact_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as error:
            raise AnalysisError("分析輸出路徑超出允許範圍。") from error
        if not candidate.is_file():
            raise AnalysisError("找不到指定的分析輸出檔案。")
        return candidate

    def get_view_image_path(
        self,
        analysis_id: str,
        view_id: str,
        coordinate_space: str = "undistorted",
    ) -> Path:
        run = self._require_image_context(analysis_id)
        view = self.repository.get_view(analysis_id, view_id)
        if view is None:
            raise AnalysisError(f"找不到分析視角：{view_id}")
        artifacts = self._artifacts(run)
        if coordinate_space == "source":
            if not run.record_id:
                raise AnalysisError("分析紀錄缺少來源 Record。")
            record_root = Path(
                self._require_record(run.record_id).record_path
            ).resolve()
            candidate = Path(view.absolute_path).resolve()
            try:
                candidate.relative_to(record_root)
            except ValueError as error:
                raise AnalysisError("來源影像路徑超出捕捉紀錄。") from error
        elif coordinate_space == "undistorted":
            # A view becomes readable as soon as it is written; the complete
            # manifest is published only after the undistortion loop finishes.
            candidate = (
                round_artifact_directory(artifacts.root, view.round_key)
                / "undistortion" / "images" / f"{safe_artifact_name(view.view_id)}.jpg"
            ).resolve()
            if not candidate.is_file():
                candidate = candidate.with_suffix(".png")
            # Current outputs have a deterministic path. Only legacy outputs
            # need the large manifest, never a live image preview.
            manifest = []
            if not candidate.is_file():
                try:
                    manifest = artifacts.read_undistortion_manifest()
                except FileNotFoundError:
                    pass
            item = next(
                (
                    row
                    for row in manifest
                    if str(row.get("view_id")) == view_id
                ),
                None,
            )
            if item is not None:
                candidate = self.get_artifact_path(
                    analysis_id,
                    str(item.get("preview_path") or item.get("undistorted_path") or ""),
                )
        elif coordinate_space == "reprojection":
            candidate = (
                round_artifact_directory(artifacts.root, view.round_key)
                / "tip"
                / "reprojections"
                / f"{safe_artifact_name(view.view_id)}.jpg"
            ).resolve()
        else:
            raise AnalysisError("影像座標空間只支援原始、去畸變或重投影。")
        if not candidate.is_file():
            raise AnalysisError("找不到指定的分析影像。")
        return candidate

    def _require_image_context(self, analysis_id: str) -> AnalysisRun:
        run = self.repository.get_image_context(analysis_id)
        if run is None:
            raise AnalysisError(f"找不到分析紀錄：{analysis_id}")
        return run

    def create(
        self,
        request: AnalysisCreateRequest,
        actor_id: str,
    ) -> AnalysisRun:
        with self._lock:
            analysis_parameters = self._new_analysis_parameters(
                request.parameters,
                method=request.method,
            )
            selected_sources = {
                camera_id: {
                    "enabled": bool(source.enabled),
                    "path": source.path.strip(),
                }
                for camera_id, source in request.camera_sources.items()
            }
            self._selected_mode_folders(
                request.record_id,
                request.mode_ids,
            )
            validation = self._validation_for_record(
                request.record_id,
                method=request.method,
                mode_ids=request.mode_ids,
            )
            record_path = self._require_record(request.record_id).record_path
            for source in selected_sources.values():
                if source["enabled"]:
                    source["path"] = record_path
            validation_errors = self._blocking_validation_messages(
                validation
            )
            if validation_errors:
                raise AnalysisError(
                    "捕捉紀錄不可分析：" + "；".join(
                        dict.fromkeys(validation_errors)
                    )
                )
            intrinsics_snapshot = self._snapshot_intrinsics(
                request.method,
                validation.camera_resolutions,
            )
            layout_snapshot: dict[str, Any] = {}

            try:
                source_manifest = self._manifest(validation)
            except OSError as error:
                raise AnalysisError(
                    f"無法固化捕捉資料輸入的 SHA-256：{error}"
                ) from error

            root = self.settings.paths.analysis_dir.resolve()
            analysis_id = next_dated_identifier(root, "analysis")
            output_group = request.record_id or "custom"
            output_dir = root / output_group / analysis_id
            while self.repository.get(analysis_id) is not None or output_dir.exists():
                prefix, suffix = analysis_id.rsplit("_", 1)
                analysis_id = f"{prefix}_{int(suffix) + 1:03d}"
                output_dir = root / output_group / analysis_id
            now = utc_now_iso()
            grouping = self._round_grouping(
                validation,
                analysis_id=analysis_id,
                record_id=request.record_id,
                mode_ids=request.mode_ids,
                method=request.method,
                enabled_camera_ids=(
                    camera_id
                    for camera_id, source in selected_sources.items()
                    if source["enabled"]
                ),
                input_manifest=source_manifest,
            )
            if grouping.errors:
                raise AnalysisError(
                    "捕捉紀錄無法建立分析輪次："
                    + "；".join(grouping.errors)
                )
            included_capture_ids = {
                view.capture_id
                for view in grouping.views
            }
            input_manifest = [
                item
                for item in source_manifest
                if int(item["input_id"]) in included_capture_ids
            ]
            reconstruction = analysis_parameters["reconstruction"]
            backend_readiness = self._reconstruction_backends.check(
                reconstruction["backend"]
            )
            if (
                request.method == "rotating"
                and not backend_readiness.get("available")
            ):
                raise AnalysisError(
                    "；".join(
                        backend_readiness.get("errors")
                        or ["目前沒有可用的三維模型建立後端。"]
                    )
                )
            free_gpu_memory = (
                backend_readiness.get("environment", {})
                .get("gpu_free_memory_bytes")
            )
            recommended_gpu_memory = {
                "preview": 4 * 1024 ** 3,
                "standard": 8 * 1024 ** 3,
                "high": 12 * 1024 ** 3,
            }[str(reconstruction["quality_preset"])]
            if (
                free_gpu_memory is not None
                and int(free_gpu_memory) < recommended_gpu_memory
            ):
                backend_readiness = {
                    **backend_readiness,
                    "warnings": [
                        *backend_readiness.get("warnings", []),
                        "目前可用 GPU 記憶體低於所選品質的建議值，"
                        "部分 Round 可能只能產生低品質模型。",
                    ],
                }
            source_bytes = sum(
                int(item.get("size_bytes") or 0)
                for item in input_manifest
            )
            quality_multiplier = {
                "preview": 4,
                "standard": 8,
                "high": 12,
            }[str(reconstruction["quality_preset"])]
            required_storage_bytes = max(
                source_bytes * quality_multiplier,
                1024 ** 3,
            )
            try:
                free_storage_bytes = shutil.disk_usage(root).free
            except OSError as error:
                raise AnalysisError(
                    f"無法檢查分析輸出儲存空間：{error}"
                ) from error
            if free_storage_bytes < required_storage_bytes:
                raise AnalysisError(
                    "分析輸出儲存空間不足；至少需要約 "
                    f"{required_storage_bytes / 1024 ** 3:.1f} GB。"
                )
            parameters = {
                **analysis_parameters,
                "manual_review_required": request.manual_review_required,
                "mode_ids": list(request.mode_ids),
                "camera_sources": selected_sources,
                "source_manifest": source_manifest,
                "input_manifest": input_manifest,
                "source_validation": {
                    "ready_at_creation": validation.ready,
                    "not_ready_reasons": validation_errors,
                    "issues": self._validation_issue_payloads(validation),
                    "source_frame_count": validation.source_frame_count,
                    "rejected_frame_count": validation.rejected_frame_count,
                    "camera_resolutions": {
                        camera_id: list(resolution)
                        for camera_id, resolution
                        in validation.camera_resolutions.items()
                    },
                    "round_count": len(grouping.rounds),
                    "ready_round_count": grouping.ready_round_count,
                    "incomplete_round_count": grouping.incomplete_round_count,
                    "warnings": list(dict.fromkeys([
                        *grouping.warnings,
                    ])),
                },
                "coordinate_space": "undistorted",
                "pose_reference_at_creation": {
                    "scale_source": "measured_stereo_baseline",
                    "baseline_mm": analysis_parameters["pose_strategy"]["baseline_mm"],
                    "top_height_mm": analysis_parameters["pose_strategy"]["top_height_mm"],
                    "side_height_mm": analysis_parameters["pose_strategy"]["side_height_mm"],
                    "side_horizontal_distance_mm": analysis_parameters["pose_strategy"]["side_horizontal_distance_mm"],
                },
                "backend_readiness_at_creation": backend_readiness,
                "storage_readiness_at_creation": {
                    "available_bytes": free_storage_bytes,
                    "estimated_required_bytes": required_storage_bytes,
                    "writable": True,
                },
                "runtime_versions": runtime_versions(),
            }
            run = AnalysisRun(
                analysis_id=analysis_id,
                record_id=request.record_id,
                intrinsics_snapshot=intrinsics_snapshot,
                aruco_layout_snapshot=layout_snapshot,
                method_name=analysis_method(request.method)["name"],
                method_version=analysis_method(request.method)["version"],
                git_commit=repository_commit(BACKEND_ROOT.parent),
                parameters=parameters,
                created_at=now,
                updated_at=now,
                created_by=actor_id,
                output_path=str(output_dir),
                status="draft",
                reconstruction_backend=backend_readiness["backend"],
                reconstruction_backend_version=backend_readiness[
                    "backend_version"
                ],
                reconstruction_environment=backend_readiness,
                round_count=len(grouping.rounds),
            )
            artifacts = AnalysisArtifacts.create(output_dir)
            try:
                artifacts.write_parameters(parameters)
                artifacts.write_source_manifest(source_manifest)
                artifacts.write_input_manifest(input_manifest)
                artifacts.write_round_index(grouping.rounds, grouping.views)
                artifacts.write_reconstruction_environment(backend_readiness)
                artifacts.write_run(run)
                artifacts.write_intrinsics_snapshot(intrinsics_snapshot)
                self.repository.create(run)
                self.repository.replace_rounds_and_views(
                    analysis_id,
                    grouping.rounds,
                    grouping.views,
                )
            except Exception:
                shutil.rmtree(output_dir, ignore_errors=True)
                raise
            self._log(run, "INFO", "分析紀錄已建立；輸入清單與參數已固化。")
            return run

    @staticmethod
    def _verify_frozen_manifest(
        run: AnalysisRun,
        validation: CaptureRecordValidation,
        *,
        progress_callback: Callable[[int, int], None] | None = None,
        hashes: Mapping[str, str] | None = None,
    ) -> None:
        current = AnalysisService._manifest(validation, progress_callback=progress_callback, hashes=hashes)
        frozen = run.parameters.get(
            "source_manifest",
            run.parameters.get("input_manifest", []),
        )
        if current != frozen:
            raise AnalysisError(
                "捕捉資料輸入在分析紀錄建立後已變更；"
                "請建立新的分析，原始資料未被修改。"
            )

    def _validate_round_analysis(self, run: AnalysisRun, cancel_event: Event | None = None) -> AnalysisRun:
        views = self.repository.list_views(run.analysis_id)
        image_probe = UndistortionProcessor(
            views, run.intrinsics_snapshot, self._artifacts(run).root,
            cancel_check=(lambda: self._check_cancel(cancel_event)) if cancel_event is not None else None,
            source_manifest=run.parameters.get("source_manifest", run.parameters.get("input_manifest", [])),
        )
        views_by_path = {str(Path(view.absolute_path)): view for view in views}

        def probe(path: Path):
            resolution = image_probe(path)
            view = views_by_path.get(str(path))
            if view is not None and resolution is not None:
                self._write_processing_preview(run, [view], message="轉檔、核對來源並套用內參去畸變")
            return resolution

        try:
            image_probe.prefetch(
                Path(item["absolute_path"]) for item in run.parameters.get(
                    "source_manifest", run.parameters.get("input_manifest", []),
                )
            )
            validation = self._validation_for_run(
                run,
                progress_callback=lambda current, total: self._update_validation_progress(
                    run, "undistorting_images", current, total,
                    0.45 * current / max(total, 1),
                    image_probe_backends=image_probe.backend_counts,
                ),
                image_probe=probe,
            )
            if all(view.view_id in image_probe.results for view in views):
                image_probe.manifest(views)
        finally:
            image_probe.close()
        if cancel_event is not None:
            self._check_cancel(cancel_event)
        errors = self._blocking_validation_messages(validation)
        if errors:
            raise AnalysisError(
                "紀錄不可分析：" + "；".join(dict.fromkeys(errors))
            )
        self._verify_frozen_manifest(
            run,
            validation,
            hashes=image_probe.hashes,
            progress_callback=lambda current, total: self._update_validation_progress(
                run, "verifying_input_files", current, total,
                0.45 + 0.50 * current / max(total, 1),
            ),
        )
        intrinsics = self._intrinsics_for_run(run)
        for camera_id in self._required_camera_ids(run.method_name):
            resolution = validation.camera_resolutions.get(camera_id)
            calibration = intrinsics[camera_id]
            if resolution is None:
                raise AnalysisError(f"紀錄缺少 {camera_id} 影像解析度。")
            width, height = resolution
            if width * calibration.height != height * calibration.width:
                raise AnalysisError(
                    f"{camera_id} 影像解析度 {width} × {height} 與內參 "
                    f"{calibration.width} × {calibration.height} 的長寬比不相容。"
                )
        if run.aruco_layout_snapshot:
            try:
                stored_layout = self._artifacts(run).read_aruco_layout_snapshot()
            except (OSError, ValueError) as error:
                raise AnalysisError("分析建立時固化的 ArUco 基準快照遺失。") from error
            if stored_layout != run.aruco_layout_snapshot:
                raise AnalysisError("分析的 ArUco 基準快照與資料庫紀錄不一致。")
        else:
            try:
                MarkerlessPoseSettings.model_validate(
                    run.parameters["pose_strategy"]
                )
            except (KeyError, ValidationError) as error:
                raise AnalysisError("分析缺少有效的無標記姿態與實測尺度設定。") from error

        rounds = self.repository.list_rounds(run.analysis_id)
        views = self.repository.list_views(run.analysis_id)
        processable_statuses = {
            "ready",
            "ready_tip_only",
            "preprocessed",
            "reconstructing",
            "model_completed",
            "model_failed",
            "failed",
            "cancelled",
        }
        ready_rounds = [
            item
            for item in rounds
            if item.status in processable_statuses
        ]
        if not ready_rounds:
            raise AnalysisError("分析沒有任何可執行的 Round。")
        if len(views) != len(run.parameters.get("input_manifest", [])):
            raise AnalysisError("分析 View 清單與固化輸入清單數量不一致。")

        reconstruction = run.parameters.get("reconstruction", {})
        backend_name = str(reconstruction.get("backend") or "")
        self._update_validation_progress(
            run, "checking_reconstruction_environment", 0, 1, 0.95,
        )
        backend_readiness = self._reconstruction_backends.probe_runtime(
            backend_name
        )
        if cancel_event is not None:
            self._check_cancel(cancel_event)
        if (
            run.method_name == "rotating"
            and not backend_readiness["available"]
        ):
            raise AnalysisError("；".join(backend_readiness["errors"]))
        parameters = {
            **run.parameters,
            "backend_readiness_at_validation": backend_readiness,
            "validation_image_probe_backends": image_probe.backend_counts,
        }
        self.repository.update_parameters(
            run.analysis_id,
            parameters,
            utc_now_iso(),
        )
        self._artifacts(run).write_parameters(parameters)
        if cancel_event is not None:
            self._check_cancel(cancel_event)
        updated = self._set_state(
            run,
            status="ready",
            stage="validation_completed",
            current_frame=len(views),
            total_frames=len(views),
            progress=1.0,
            clear_error=True,
        )
        self._log(
            updated,
            "INFO",
            f"驗證完成，共 {len(ready_rounds)} 個可分析 Round、{len(views)} 個 View。",
        )
        return updated

    def validate(self, analysis_id: str) -> AnalysisRun:
        with self._lock:
            run = self._require_run(analysis_id)
            if self._runner.is_active(analysis_id):
                raise AnalysisError("分析工作執行中，不能重複驗證。")
            if run.status not in {"draft", "failed", "cancelled", "ready"}:
                raise AnalysisError(
                    f"目前狀態「{_status_label(run.status)}」不可重新驗證。"
                )
            run = self._set_state(
                run,
                status="validating",
                stage="validating",
                current_frame=0,
                progress=0.0,
                clear_error=True,
            )
            with StepJournal(self._artifacts(run).root) as journal:
                journal.save("control", "mode", "", {"mode": "validating"})
            if not self._runner.start(analysis_id):
                raise AnalysisError("分析工作已在執行。")
            return run

    def _update_validation_progress(
        self,
        run: AnalysisRun,
        stage: str,
        current: int,
        total: int,
        fraction: float,
        *,
        image_probe_backends: Mapping[str, int] | None = None,
    ) -> None:
        now = monotonic()
        with self._preview_lock:
            previous = self._validation_progress.get(run.analysis_id)
            if (
                previous is not None
                and previous.stage == stage
                and current < total
                and now - self._validation_progress_times[run.analysis_id] < 0.5
            ):
                return
            progress = AnalysisProgress(
                analysis_id=run.analysis_id,
                status="validating",
                stage=stage,
                current_frame=current,
                total_frames=total,
                progress=fraction,
                image_probe_backends=(
                    dict(image_probe_backends)
                    if image_probe_backends is not None
                    else previous.image_probe_backends if previous is not None else {}
                ),
                processing_preview=self._processing_previews.get(run.analysis_id),
                checkpoints=checkpoint_summary(self._artifacts(run).root),
            )
            # Frequent updates must not deserialize or rewrite the frozen image manifests.
            self._validation_progress[run.analysis_id] = progress
            self._validation_progress_times[run.analysis_id] = now
        self.repository.update_state(
            run.analysis_id, updated_at=utc_now_iso(), stage=stage,
            current_frame=current, total_frames=total, progress=fraction,
        )
        write_json_atomic(self._artifacts(run).root / "progress.json", progress.model_dump(mode="json"))
        if self.progress_callback is not None:
            try:
                self.progress_callback(progress)
            except Exception:
                logger.exception("Analysis validation progress callback failed")

    def _write_processing_preview(
        self,
        run: AnalysisRun,
        views: Iterable[AnalysisView],
        *,
        coordinate_space: str = "undistorted",
        artifact_path: str | None = None,
        message: str | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        selected = {}
        for view in views:
            selected.setdefault(view.camera_id, view)
        preview = AnalysisProcessingPreview(
            round_key=next(iter(selected.values())).round_key if selected else None,
            views=[{
                "view_id": view.view_id,
                "camera_id": view.camera_id,
                "snapshot_id": view.snapshot_id,
                "timestamp": view.timestamp,
            } for view in selected.values()],
            coordinate_space=coordinate_space,
            artifact_path=artifact_path,
            message=message,
            diagnostics=diagnostics or {},
            updated_at=utc_now_iso(),
        )
        with self._preview_lock:
            self._processing_previews[run.analysis_id] = preview
            try:
                write_json_atomic(
                    self._artifacts(run).root / "processing_preview.json",
                    preview.model_dump(mode="json"),
                )
            except OSError:
                # Preview persistence is optional; image processing must continue.
                logger.warning(
                    "Could not persist processing preview for %s; live preview remains available",
                    run.analysis_id,
                    exc_info=True,
                )

    def _clear_processing_preview(self, run: AnalysisRun) -> None:
        with self._preview_lock:
            self._processing_previews[run.analysis_id] = None
            try:
                (self._artifacts(run).root / "processing_preview.json").unlink(missing_ok=True)
            except OSError:
                logger.warning(
                    "Could not remove processing preview for %s",
                    run.analysis_id,
                    exc_info=True,
                )

    def _progress_for_run(self, run: AnalysisRun) -> AnalysisProgress:
        with self._preview_lock:
            if run.analysis_id in self._processing_previews:
                preview = self._processing_previews[run.analysis_id]
            else:
                preview_path = self._artifacts(run).root / "processing_preview.json"
                try:
                    preview = AnalysisProcessingPreview.model_validate_json(
                        preview_path.read_text(encoding="utf-8")
                    )
                except (OSError, ValueError):
                    preview = None
                else:
                    self._processing_previews[run.analysis_id] = preview
        return AnalysisProgress(
            analysis_id=run.analysis_id,
            status=run.status,
            stage=run.stage,
            current_frame=run.current_frame,
            total_frames=run.total_frames,
            progress=run.progress,
            last_error=run.last_error,
            processing_preview=preview,
            image_probe_backends=run.parameters.get("validation_image_probe_backends", {}),
            checkpoints=checkpoint_summary(self._artifacts(run).root),
        )

    def _emit_progress(self, run: AnalysisRun, progress: AnalysisProgress | None = None) -> None:
        if self.progress_callback is None:
            return
        try:
            self.progress_callback(
                progress if progress is not None else self._progress_for_run(run)
            )
        except Exception:
            logger.exception("Analysis progress callback failed")

    def _set_state(
        self,
        run: AnalysisRun,
        *,
        status: str | None = None,
        stage: str | None = None,
        current_frame: int | None = None,
        total_frames: int | None = None,
        progress: float | None = None,
        manual_review_completed: bool | None = None,
        last_error: str | None = None,
        clear_error: bool = False,
        image_probe_backends: Mapping[str, int] | None = None,
    ) -> AnalysisRun:
        self.repository.update_state(
            run.analysis_id,
            updated_at=utc_now_iso(),
            status=status,
            stage=stage,
            current_frame=current_frame,
            total_frames=total_frames,
            progress=progress,
            manual_review_completed=manual_review_completed,
            last_error=last_error,
            clear_error=clear_error,
        )
        with self._preview_lock:
            previous = self._validation_progress.get(run.analysis_id) or self._live_progress.get(run.analysis_id)
        changes = {
            key: getattr(previous, key) for key in ("status", "stage", "current_frame", "total_frames", "progress", "last_error")
        } if previous is not None else {}
        changes.update({
            key: value for key, value in {
                "status": status, "stage": stage, "current_frame": current_frame,
                "total_frames": total_frames, "progress": progress,
                "manual_review_completed": manual_review_completed, "last_error": last_error,
            }.items() if value is not None
        })
        changes["updated_at"] = utc_now_iso()
        if clear_error:
            changes["last_error"] = None
        updated = run.model_copy(update=changes)
        live = self._progress_for_run(updated)
        if image_probe_backends is not None or previous is not None:
            live = live.model_copy(update={"image_probe_backends": dict(
                image_probe_backends if image_probe_backends is not None else previous.image_probe_backends,
            )})
        with self._preview_lock:
            self._live_progress[run.analysis_id] = live
        write_json_atomic(self._artifacts(updated).root / "progress.json", live.model_dump(mode="json"))
        if updated.status in TERMINAL_STATUSES | {"ready", "paused", "needs_review"}:
            updated = self._require_run(run.analysis_id)
            self._artifacts(updated).write_run(updated)
        self._emit_progress(updated, live)
        return updated

    def _log(
        self,
        run: AnalysisRun,
        level: str,
        message: str,
    ) -> None:
        timestamp = utc_now_iso()
        path = self._artifacts(run).log_path
        with self._lock:
            write_header = not path.is_file() or path.stat().st_size == 0
            with path.open(
                "a",
                encoding="utf-8",
                newline="",
            ) as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=(
                        "timestamp",
                        "level",
                        "analysis_id",
                        "message",
                    ),
                )
                if write_header:
                    writer.writeheader()
                writer.writerow({
                    "timestamp": timestamp,
                    "level": level,
                    "analysis_id": run.analysis_id,
                    "message": message,
                })
        getattr(logger, level.lower(), logger.info)(
            "Analysis %s: %s",
            run.analysis_id,
            message,
        )

    def _record_failure(
        self,
        run: AnalysisRun,
        error: BaseException,
        *,
        context: str,
        report_error: bool = False,
    ) -> AnalysisRun:
        message = f"{context}：{error}"
        trace = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )
        self._log(run, "ERROR", f"{message}\n{trace}")
        if report_error and self.error_reporter is not None:
            safe_detail = public_error_detail(error)
            try:
                self.error_reporter(
                    f"分析 {run.analysis_id} 執行失敗：{safe_detail}"
                )
            except Exception:
                logger.exception("Analysis error reporter failed")
        return self._set_state(
            run,
            status="failed",
            last_error=message,
        )

    def get_progress(self, analysis_id: str | None = None) -> AnalysisProgress:
        with self._preview_lock:
            if analysis_id is not None:
                live = self._validation_progress.get(analysis_id) or self._live_progress.get(analysis_id)
            else:
                live = next(iter(self._validation_progress.values()), None)
                if live is None:
                    live = next((item for item in self._live_progress.values() if item.status in PROCESSING_STATUSES), None)
        if live is not None:
            return live
        if analysis_id is not None:
            run = self._require_run(analysis_id)
        else:
            processing = {
                run.analysis_id: run
                for run in self.repository.list()
                if run.status in PROCESSING_STATUSES
            }
            preferred_ids = (
                self._runner.running_analysis_ids()
                + self._runner.active_analysis_ids()
            )
            run = next(
                (
                    processing[active_id]
                    for active_id in preferred_ids
                    if active_id in processing
                ),
                None,
            )
            if run is None and processing:
                # A processing row without an in-process worker can exist briefly
                # during startup recovery. Keep it observable until recovery marks
                # it failed instead of reporting a false idle state.
                run = next(iter(processing.values()))
            if run is None:
                return AnalysisProgress()
        return self._progress_for_run(run)

    def start(self, analysis_id: str) -> AnalysisRun:
        with self._lock:
            run = self._require_run(analysis_id)
            if run.status != "ready":
                raise AnalysisError("只有狀態為「就緒」的分析紀錄可以開始。")
            if self._runner.is_active(analysis_id):
                raise AnalysisError("分析工作已在執行。")
            try:
                self.repository.clear_results(analysis_id)
                self._artifacts(run).clear_pose_alignment()
            except OSError as error:
                raise AnalysisError(
                    f"無法清除前次相機姿態輸出：{error}"
                ) from error
            run = self._set_state(
                run,
                status="processing",
                stage=(
                    "detecting_aruco"
                    if run.aruco_layout_snapshot
                    else "estimating_camera_poses"
                ),
                current_frame=0,
                progress=0.0,
                clear_error=True,
            )
            try:
                with StepJournal(self._artifacts(run).root) as journal:
                    journal.save("control", "mode", "", {"mode": "processing"})
                if not self._runner.start(analysis_id):
                    raise AnalysisError("分析工作已在執行。")
            except Exception as error:
                self._record_failure(run, error, context="無法啟動分析背景工作")
                if isinstance(error, AnalysisError):
                    raise
                raise AnalysisError(f"無法啟動分析背景工作：{error}") from error
            self._log(run, "INFO", "分析已排入背景執行。")
            return run

    def cancel(
        self,
        analysis_id: str,
        actor_id: str = "system",
    ) -> AnalysisRun:
        run = self._require_run(analysis_id)
        worker_cancelled = self._runner.cancel(analysis_id)
        if worker_cancelled or run.status in PROCESSING_STATUSES:
            requested_at = utc_now_iso()
            self.repository.update_cancellation_metadata(
                analysis_id,
                requested_at=requested_at,
                requested_by=actor_id,
                updated_at=requested_at,
            )
            run = self._require_run(analysis_id)
            self._artifacts(run).write_run(run)
        if worker_cancelled:
            self._log(run, "INFO", "已要求取消分析，背景工作將於下一個檢查點停止。")
            return run
        if run.status in PROCESSING_STATUSES:
            self._log(run, "WARNING", "分析背景工作已不存在，將殘留工作標記為已取消。")
            return self._set_state(
                run,
                status="cancelled",
                last_error="分析背景工作中止，工作已重設為可重試狀態。",
            )
        raise AnalysisError("目前沒有可取消的分析工作。")

    def retry(self, analysis_id: str) -> AnalysisRun:
        with self._lock:
            return self._retry(analysis_id)

    def _retry(self, analysis_id: str) -> AnalysisRun:
        run = self._require_run(analysis_id)
        rebuild_preview = (run.method_name == "rotating" and run.stage == "waiting_for_model_review"
                           and run.status in {"needs_review", "reviewing"})
        if run.status not in {"failed", "cancelled"} and not rebuild_preview:
            raise AnalysisError("只有狀態為「失敗」或「已取消」的分析紀錄可以重試。")
        if self._runner.is_active(analysis_id) and not self._runner.wait_until_idle(
            analysis_id
        ):
            raise AnalysisError("前一個分析背景工作尚未停止，請稍後重試。")
        resumed = self._set_state(
            run,
            status="processing",
            stage=(
                "estimating_reference_poses"
                if rebuild_preview
                else "detecting_aruco"
                if run.aruco_layout_snapshot
                else "estimating_camera_poses"
            ),
            current_frame=0,
            progress=.18 if rebuild_preview else 0.0,
            clear_error=True,
        )
        try:
            if not self._runner.start(analysis_id):
                raise AnalysisError("分析工作已在執行。")
        except Exception as error:
            self._record_failure(
                resumed,
                error,
                context="無法重新啟動分析背景工作",
            )
            if isinstance(error, AnalysisError):
                raise
            raise AnalysisError(f"無法重新啟動分析背景工作：{error}") from error
        self._log(resumed, "INFO", "重新準備選點預覽，完成後仍需人工對齊相機。" if rebuild_preview
                  else "分析已從既有 Round checkpoint 繼續執行。")
        return resumed

    def resume(self, analysis_id: str) -> AnalysisRun:
        run = self._require_run(analysis_id)
        if run.status == "paused":
            if not self._runner.wait_until_idle(analysis_id):
                raise AnalysisError("背景工作尚在保存，請稍後恢復。")
            with StepJournal(self._artifacts(run).root) as journal:
                control = journal.get("control", "mode") or {}
            mode = "validating" if control.get("mode") == "validating" else "processing"
            resumed = self._set_state(run, status=mode, clear_error=True)
            if not self._runner.start(analysis_id):
                raise AnalysisError("分析背景工作尚未停止。")
            return resumed
        if run.status == "ready":
            return self.start(analysis_id)
        if run.status in {"needs_review", "reviewing"}:
            if run.stage in {"waiting_for_stereo_review", "waiting_for_model_review"}:
                raise AnalysisError("請先完成人工雙鏡頭配對，才能繼續分析。")
            return self.reconstruct(analysis_id, manual_review_completed=True)
        if run.status in {"failed", "cancelled"}:
            return self.retry(analysis_id)
        raise AnalysisError(
            f"目前狀態「{_status_label(run.status)}」沒有可繼續的工作。"
        )

    def pause(self, analysis_id: str) -> AnalysisRun:
        run = self._require_run(analysis_id)
        if run.status == "paused":
            return run
        if run.status not in PROCESSING_STATUSES:
            raise AnalysisError("目前沒有可暫停的分析工作。")
        if run.status == "pausing":
            return run
        with StepJournal(self._artifacts(run).root) as journal:
            journal.save("control", "mode", "", {"mode": "validating" if run.status == "validating" else "processing"})
        # Publish the request before signalling the worker, so its final paused
        # state cannot be overwritten by the HTTP request.
        requested = self._set_state(run, status="pausing")
        with self._preview_lock:
            self._validation_progress.pop(analysis_id, None)
        if not self._runner.pause(analysis_id):
            return self._set_state(requested, status="paused")
        return requested

    def reconstruct(
        self,
        analysis_id: str,
        manual_review_completed: bool = True,
    ) -> AnalysisRun:
        with self._lock:
            run = self._require_run(analysis_id)
            if run.stage in {"waiting_for_stereo_review", "waiting_for_model_review"}:
                raise AnalysisError("雙鏡頭姿態尚未確認，請先完成人工配對。")
            if run.status not in {
                "needs_review",
                "reviewing",
                "completed",
                "partially_completed",
            }:
                raise AnalysisError("目前狀態不可執行三維重建。")
            if self._runner.is_active(analysis_id):
                raise AnalysisError("分析工作已在執行。")
            self._refresh_tip_correction_artifacts(run)
            resolved = self._resolved_tip_landmarks(analysis_id)
            if not any(item.valid for item in resolved):
                raise AnalysisError("沒有有效尖端標記，無法完成分析。")
            rounds = self.repository.list_rounds(analysis_id)
            incomplete = sum(
                item.status not in {"tip_completed"}
                for item in rounds
            )
            final_status = (
                "partially_completed"
                if incomplete > 0
                else "completed"
            )
            completed = self._set_state(
                self._require_run(analysis_id),
                status=final_status,
                stage="completed",
                current_frame=len(rounds),
                total_frames=len(rounds),
                progress=1.0,
                manual_review_completed=manual_review_completed,
                clear_error=True,
            )
            self._log(completed, "INFO", "尖端標記人工確認已完成。")
            return completed

    def reset(self, analysis_id: str) -> AnalysisRun:
        with self._lock:
            run = self._require_run(analysis_id)
            if (
                self._runner.is_active(analysis_id)
                and not self._runner.wait_until_idle(analysis_id)
            ) or run.status in PROCESSING_STATUSES:
                raise AnalysisError("分析紀錄中，請先取消並等待背景工作停止。")
            self.repository.clear_results(analysis_id)
            artifacts = self._artifacts(run)
            self._clear_processing_preview(run)
            for relative in (
                "summaries",
                "rounds",
                "trajectory",
                "checkpoints",
            ):
                shutil.rmtree(artifacts.root / relative, ignore_errors=True)
            for file_name in (
                "undistortion_manifest.json",
                "round_quality.json",
                "round_models.json",
                "reconstruction_environment.json",
                "tip_corrections.json",
            ):
                (artifacts.root / file_name).unlink(missing_ok=True)
            rounds = self.repository.list_rounds(analysis_id)
            reset_rounds = []
            for item in rounds:
                if item.status == "incomplete":
                    status = "incomplete"
                elif (
                    run.method_name == "fixed"
                    or item.round_id == "round.00"
                ):
                    status = "ready_tip_only"
                else:
                    status = "ready"
                reset_item = item.model_copy(
                    update={
                        "status": status,
                        "static_scene_score": None,
                        "model_result_id": None,
                        "tip_landmark_id": None,
                        "failure_reason": None,
                    }
                )
                self.repository.update_round(reset_item)
                reset_rounds.append(reset_item)
            reset_views = [
                item.model_copy(
                    update={
                        "selected_for_reconstruction": False,
                        "exclusion_reason": None,
                        "pose_status": None,
                        "pose_reprojection_error_px": None,
                    }
                )
                for item in self.repository.list_views(analysis_id)
            ]
            self.repository.update_views(reset_views)
            artifacts.write_round_index(reset_rounds, reset_views)
            updated = self._set_state(
                run,
                status="draft",
                stage="validating",
                current_frame=0,
                total_frames=0,
                progress=0.0,
                manual_review_completed=False,
                clear_error=True,
            )
            self._log(updated, "INFO", "分析衍生結果已重設；輸入清單、參數與紀錄保留。")
            return updated

    def delete(self, analysis_id: str) -> None:
        with self._lock:
            run = self._require_run(analysis_id)
            if self._runner.is_active(analysis_id) or run.status in PROCESSING_STATUSES:
                raise AnalysisError("分析紀錄中，不能刪除。")
            directory = self._output_dir(run)
            tombstone = directory.with_name(
                f".{directory.name}.{uuid4().hex}.deleting"
            )
            if directory.exists():
                directory.replace(tombstone)
            try:
                self.repository.delete(analysis_id)
            except Exception:
                if tombstone.exists():
                    tombstone.replace(directory)
                raise
            shutil.rmtree(tombstone, ignore_errors=True)
            with self._preview_lock:
                self._processing_previews.pop(analysis_id, None)
                self._live_progress.pop(analysis_id, None)
                self._validation_progress.pop(analysis_id, None)
                self._validation_progress_times.pop(analysis_id, None)

    def recover_interrupted_runs(self) -> None:
        for run in self.repository.list():
            if (run.method_name == "rotating" and run.stage == "waiting_for_model_review"
                    and run.status in {"needs_review", "reviewing"}):
                context_path = self._artifacts(run).root / "pose_debug/model_reference/context.json"
                try:
                    context = json.loads(context_path.read_text(encoding="utf-8"))
                    version = context.get("model", {}).get("model_quality", {}).get("training_version")
                except (OSError, ValueError, AttributeError):
                    version = None
                if version is not None and version != PLANT_TRAINING_VERSION:
                    # Keep old artifacts/drafts, but require the user to resume
                    # before rebuilding a reference with the new training rules.
                    updated = self._set_state(run, status="paused", stage="estimating_reference_poses", clear_error=True)
                    self._log(updated, "INFO", "參照模型訓練版本已更新，恢復分析後將重新建立模型。")
                    continue
            if (run.method_name == "rotating" and not run.aruco_layout_snapshot
                    and run.stage in {"waiting_for_stereo_review", "estimating_stereo_pose"}
                    and run.status in {"needs_review", "reviewing", "failed"}):
                # Upgrade old direct-stereo reviews without starting any work.
                self._set_state(run, status="paused", stage="estimating_reference_poses", clear_error=True)
                continue
            if (run.status == "failed" and run.stage == "estimating_stereo_pose"
                    and "無法建立無標記雙鏡頭姿態" in (run.last_error or "")):
                self._request_stereo_review(run, run.last_error)
                continue
            if run.status not in PROCESSING_STATUSES:
                continue
            resumable = (self._artifacts(run).root / "checkpoints" / "steps.sqlite3").is_file()
            self._log(run, "WARNING", "偵測到程式中止，已保留完成的步驟與診斷。")
            self._set_state(
                run,
                status="paused" if resumable else "failed",
                last_error="程式中止，已保留步驟紀錄，可恢復分析。" if resumable else "程式非正常中止；可在確認輸入後重試。",
            )

    def close(self) -> None:
        self._source_scans.close()
        self._runner.close()

    def _resolved_tip_landmarks(
        self,
        analysis_id: str,
    ) -> list[TipLandmark]:
        resolved = {
            item.round_key: item
            for item in self.repository.list_tip_landmarks(analysis_id)
        }
        for correction in self.repository.list_tip_corrections(analysis_id):
            resolved[correction.round_key] = correction.corrected_tip
        return list(resolved.values())

    def _refresh_tip_correction_artifacts(self, run: AnalysisRun) -> None:
        output_settings = run.parameters.get("outputs")
        export_trajectory_csv = (
            bool(output_settings.get("export_trajectory_csv", True))
            if isinstance(output_settings, Mapping)
            else True
        )
        corrections = self.repository.list_tip_corrections(run.analysis_id)
        resolved_landmarks = self._resolved_tip_landmarks(run.analysis_id)
        landmark_by_round = {
            item.round_key: item
            for item in resolved_landmarks
        }
        models = self.repository.list_round_models(run.analysis_id)
        model_by_round = {
            item.round_key: item
            for item in models
        }
        rounds = []
        for round_item in self.repository.list_rounds(run.analysis_id):
            landmark = landmark_by_round.get(round_item.round_key)
            if landmark is None:
                rounds.append(round_item)
                continue
            model = model_by_round.get(round_item.round_key)
            if not landmark.valid:
                status = "tip_invalid"
                failure_reason = landmark.failure_reason
            elif (
                run.method_name == "rotating"
                and round_item.round_id != "round.00"
                and (model is None or model.status != "completed")
            ):
                status = "tip_only"
                failure_reason = (
                    model.failure_reason
                    if model is not None
                    else round_item.failure_reason
                )
            else:
                status = "tip_completed"
                failure_reason = None
            updated_round = round_item.model_copy(
                update={
                    "status": status,
                    "tip_landmark_id": landmark.tip_id,
                    "failure_reason": failure_reason,
                }
            )
            self.repository.update_round(updated_round)
            rounds.append(updated_round)
        trajectory = link_tip_trajectory(
            rounds,
            resolved_landmarks,
            blocked_interpolation_round_keys=_model_failed_round_keys(
                rounds,
                model_by_round,
                run.method_name,
            ),
        )
        self.repository.replace_tip_trajectory(
            run.analysis_id,
            trajectory.points,
        )
        valid_count = sum(item.valid for item in resolved_landmarks)
        completed_round_count = sum(
            item.status == "tip_completed"
            for item in rounds
        )
        failed_round_count = sum(
            item.status in {
                "failed",
                "model_failed",
                "tip_only",
                "tip_invalid",
            }
            for item in rounds
        )
        self.repository.update_state(
            run.analysis_id,
            updated_at=utc_now_iso(),
            completed_round_count=completed_round_count,
            failed_round_count=failed_round_count,
            tip_marker_count=valid_count,
            trajectory_status="completed" if valid_count else "unavailable",
        )
        reprojection_errors = [
            float(item.mean_reprojection_error_px)
            for item in resolved_landmarks
            if (
                item.valid
                and item.mean_reprojection_error_px is not None
            )
        ]
        self.repository.update_average_reprojection_error(
            run.analysis_id,
            (
                float(np.mean(reprojection_errors))
                if reprojection_errors
                else None
            ),
            utc_now_iso(),
        )
        updated = self._require_run(run.analysis_id)
        artifacts = self._artifacts(updated)
        artifacts.write_tip_corrections(corrections)
        artifacts.write_tip_trajectory(
            trajectory.points,
            trajectory.quality,
            export_csv=export_trajectory_csv,
        )
        artifacts.write_formal_summaries(
            rounds,
            models,
            resolved_landmarks,
            trajectory.quality,
        )
        artifacts.write_run(updated)
        self._emit_progress(updated)

    def list_tip_corrections(
        self,
        analysis_id: str,
        round_key: str | None = None,
    ) -> list[TipCorrection]:
        run = self._require_run(analysis_id)
        if run.method_name not in SUPPORTED_ANALYSIS_METHODS:
            return []
        return self.repository.list_tip_corrections(
            analysis_id,
            round_key,
        )

    def save_tip_correction(
        self,
        analysis_id: str,
        request: TipCorrectionRequest,
        actor_id: str,
    ) -> TipCorrection:
        with self._lock:
            run = self._require_run(analysis_id)
            if run.method_name not in SUPPORTED_ANALYSIS_METHODS:
                raise AnalysisError("此分析方法不支援三維尖端標記修正。")
            if run.status not in {
                "needs_review",
                "reviewing",
                "completed",
                "partially_completed",
            }:
                raise AnalysisError("目前狀態不可修正三維尖端標記。")
            round_item = next(
                (
                    item
                    for item in self.repository.list_rounds(analysis_id)
                    if item.round_key == request.round_key
                ),
                None,
            )
            if round_item is None:
                raise AnalysisError(f"找不到 Round：{request.round_key}")
            automatic_tip = next(
                (
                    item
                    for item in self.repository.list_tip_landmarks(analysis_id)
                    if item.round_key == request.round_key
                ),
                None,
            )
            if automatic_tip is None:
                raise AnalysisError("此 Round 尚無可修正的自動尖端標記。")
            model_result = next(
                (
                    item
                    for item in self.repository.list_round_models(analysis_id)
                    if item.round_key == request.round_key
                ),
                None,
            )
            tip_settings = run.parameters.get("tip_analysis")
            maximum_error = (
                float(tip_settings.get("maximum_reprojection_error_px", 5.0))
                if isinstance(tip_settings, Mapping)
                else 5.0
            )
            try:
                correction = create_tip_correction(
                    correction_id=f"tip_correction_{uuid4().hex}",
                    operator_id=actor_id,
                    created_at=utc_now_iso(),
                    request=request,
                    round_item=round_item,
                    views=self.repository.list_views(
                        analysis_id,
                        request.round_key,
                    ),
                    poses=self.repository.list_camera_poses(
                        analysis_id,
                        request.round_key,
                    ),
                    intrinsics_snapshot=run.intrinsics_snapshot,
                    automatic_tip=automatic_tip,
                    artifacts_root=self._artifacts(run).root,
                    model_result=model_result,
                    maximum_reprojection_error_px=maximum_error,
                )
            except (KeyError, TypeError, ValueError) as error:
                raise AnalysisError(f"尖端標記人工修正失敗：{error}") from error
            self.repository.insert_tip_correction(correction)
            try:
                self._refresh_tip_correction_artifacts(run)
            except Exception as error:
                self.repository.delete_tip_correction(
                    analysis_id,
                    correction.correction_id,
                )
                try:
                    self._refresh_tip_correction_artifacts(run)
                except Exception:
                    pass
                if isinstance(error, AnalysisError):
                    raise
                raise AnalysisError(
                    f"尖端標記修正後的軌跡更新失敗：{error}"
                ) from error
            if run.status == "needs_review":
                self._set_state(
                    self._require_run(analysis_id),
                    status="reviewing",
                    stage="waiting_for_review",
                    progress=0.95,
                )
            return correction

    def delete_tip_correction(
        self,
        analysis_id: str,
        correction_id: str,
    ) -> None:
        with self._lock:
            run = self._require_run(analysis_id)
            if run.method_name not in SUPPORTED_ANALYSIS_METHODS:
                raise AnalysisError("此分析方法不支援三維尖端標記修正。")
            if run.status not in {
                "needs_review",
                "reviewing",
                "completed",
                "partially_completed",
            }:
                raise AnalysisError("目前狀態不可刪除三維尖端標記修正。")
            stored = next(
                (
                    item
                    for item in self.repository.list_tip_corrections(analysis_id)
                    if item.correction_id == correction_id
                ),
                None,
            )
            if stored is None or not self.repository.delete_tip_correction(
                analysis_id,
                correction_id,
            ):
                raise AnalysisError(f"找不到尖端標記修正：{correction_id}")
            try:
                self._refresh_tip_correction_artifacts(run)
            except Exception as error:
                self.repository.insert_tip_correction(stored)
                try:
                    self._refresh_tip_correction_artifacts(run)
                except Exception:
                    pass
                if isinstance(error, AnalysisError):
                    raise
                raise AnalysisError(
                    f"刪除修正後的軌跡更新失敗：{error}"
                ) from error

    def export(self, analysis_id: str) -> Path:
        run = self._require_run(analysis_id)
        if run.status not in {"completed", "partially_completed"}:
            raise AnalysisError("分析完成後才能匯出。")
        root = self._artifacts(run).root
        destination = root / f"{analysis_id}_export.zip"
        temporary = root / f".{analysis_id}.{uuid4().hex}.tmp"
        try:
            with zipfile.ZipFile(
                temporary,
                "w",
                compression=zipfile.ZIP_DEFLATED,
            ) as archive:
                for path in sorted(root.rglob("*")):
                    if (
                        path.is_file()
                        and path not in {destination, temporary}
                        and path.suffix != ".zip"
                    ):
                        archive.write(path, path.relative_to(root).as_posix())
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination

    @staticmethod
    def _check_cancel(cancel_event: Event) -> None:
        if cancel_event.is_set():
            if getattr(cancel_event, "pause_requested", False):
                raise AnalysisPausedError("分析已暫停，完成的步驟與模型 checkpoint 已保存。")
            raise OperationCancelledError("分析已由使用者取消。")

    def _saved_step(self, run: AnalysisRun, stage: str, item: str, signature: str):
        with StepJournal(self._artifacts(run).root) as journal:
            return journal.get(stage, item, signature)

    @staticmethod
    def _stereo_pose_signature(run: AnalysisRun) -> str:
        return step_signature({"version": 3 if run.method_name == "rotating" else 2, "pose": run.parameters.get("pose_strategy"),
                               **({"training_version": PLANT_TRAINING_VERSION, "model_parameters": run.parameters.get("reconstruction")}
                                  if run.method_name == "rotating" else {}),
                               "intrinsics": run.intrinsics_snapshot, "aruco": run.aruco_layout_snapshot})

    @staticmethod
    def _is_stereo_review(run: AnalysisRun) -> bool:
        return run.status in {"needs_review", "reviewing", "failed"} and run.stage in {
            "waiting_for_stereo_review", "estimating_stereo_pose",
            "waiting_for_model_review", "aligning_model_cameras",
        }

    def _request_stereo_review(self, run: AnalysisRun, reason: str) -> AnalysisRun:
        path = self._artifacts(run).root / "pose_debug" / "stereo" / "manual_review.json"
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previous = {}
        write_json_atomic(path, {**previous, "accepted": False, "reason": reason, "updated_at": utc_now_iso()})
        model_review = run.method_name == "rotating" and (self._artifacts(run).root / "pose_debug/model_reference/context.json").is_file()
        updated = self._set_state(run, status="needs_review", stage="waiting_for_model_review" if model_review else "waiting_for_stereo_review",
                                  manual_review_completed=False, clear_error=True)
        self._log(updated, "WARNING", "相機對齊需要人工確認，已保存三維參照與影像。" if model_review
                  else "自動雙鏡頭配對不足，已保存影像，等待人工配對。")
        return updated

    def get_stereo_review(self, analysis_id: str) -> dict:
        with self._lock:
            return self._stereo_review_payload(analysis_id)

    def _stereo_review_payload(self, analysis_id: str) -> dict:
        run = self._require_image_context(analysis_id)
        if not self._is_stereo_review(run):
            raise AnalysisError("目前沒有待確認的雙鏡頭姿態。")
        context_path = self._artifacts(run).root / "pose_debug/model_reference/context.json"
        if run.stage == "waiting_for_model_review":
            context = json.loads(context_path.read_text(encoding="utf-8"))
            saved_path = self._artifacts(run).root / "pose_debug/stereo/manual_review.json"
            saved = json.loads(saved_path.read_text(encoding="utf-8")) if saved_path.is_file() else {}
            review_views = [self.repository.get_view(analysis_id, view_id) for view_id in context["fixed_view_ids"]]
            if any(view is None for view in review_views):
                raise AnalysisError("模型對齊影像遺失，請重試分析。")
            reference = model_review_reference(context, self._artifacts(run).root)
            draft = saved.get("request")
            if draft and draft.get("reference_signature") == context["reference"]["signature"]:
                # Existing sparse anchors retain their IDs when opening an already trained model.
                draft = {**draft, "reference_signature": reference["signature"]}
            valid_draft = draft and draft.get("reference_signature") == reference["signature"]
            return {"analysis_id": analysis_id, "mode": "model_reference", "minimum_pairs": 4,
                    "reason": saved.get("reason"), "views": [v.model_dump(mode="json") for v in review_views],
                    "reference": reference, "draft": draft if valid_draft else None,
                    "validation": saved.get("validation") if valid_draft else None}
        preview = self._progress_for_run(run).processing_preview
        views = [self.repository.get_view(analysis_id, view.view_id) for view in (preview.views if preview else [])]
        views = [view for view in views if view is not None and view.camera_id in {"top", "side"}]
        if {view.camera_id for view in views} != {"top", "side"}:
            raise AnalysisError("缺少待確認的俯視與側視影像，請重試姿態估計以產生診斷影像。")
        path = self._artifacts(run).root / "pose_debug" / "stereo" / "manual_review.json"
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {}
        return {"analysis_id": analysis_id, "reason": saved.get("reason") or run.last_error,
                "minimum_pairs": MINIMUM_MANUAL_STEREO_PAIRS, "views": [view.model_dump(mode="json") for view in views],
                "draft": saved.get("request"), "validation": saved.get("validation"),
                "diagnostics": preview.diagnostics if preview else {}}

    def submit_stereo_review(self, analysis_id: str, request: StereoPoseReviewRequest | ModelPoseReviewRequest, actor_id: str) -> AnalysisRun:
        with self._lock:
            run = self._require_run(analysis_id)
            if not self._is_stereo_review(run):
                raise AnalysisError("目前沒有待確認的雙鏡頭姿態。")
            if not self._runner.wait_until_idle(analysis_id):
                raise AnalysisError("前一個分析工作尚未保存完畢，請稍後再試。")
            views = [self.repository.get_view(analysis_id, view_id) for view_id in (request.top_view_id, request.side_view_id)]
            if any(view is None for view in views) or [view.camera_id for view in views] != ["top", "side"]:
                raise AnalysisError("配對影像必須是本分析的俯視與側視影像。")
            if (views[0].round_key, views[0].snapshot_id) != (views[1].round_key, views[1].snapshot_id):
                raise AnalysisError("人工配對必須使用同一輪、同一次擷取的兩個視角。")
            for pair in request.correspondences:
                for view in views:
                    point = getattr(pair, view.camera_id)
                    if point.x_px >= view.image_width or point.y_px >= view.image_height:
                        raise AnalysisError("人工標記超出影像範圍，請重新選取。")
            root = self._artifacts(run).root
            frames, intrinsics, paths = [], {}, []
            for view in views:
                preview_path = self.get_view_image_path(analysis_id, view.view_id)
                path = preview_path.with_suffix(".tiff")
                if not path.is_file():
                    raise AnalysisError("找不到人工配對所需的無損去畸變影像，請重試分析。")
                paths.append(path)
                frames.append({"file_path": str(path), "camera_id": view.camera_id})
                snapshot = run.intrinsics_snapshot[view.camera_id]
                intrinsics[view.camera_id] = {"camera_matrix": snapshot["undistorted_camera_matrix"],
                                            "width": view.image_width, "height": view.image_height}
            review_path = root / "pose_debug" / "stereo" / "manual_review.json"
            payload = {"accepted": False, "request": request.model_dump(mode="json"),
                       "reviewed_by": actor_id, "updated_at": utc_now_iso()}
            write_json_atomic(review_path, payload)
            validation = {}
            try:
                settings = MarkerlessPoseSettings.model_validate(run.parameters.get("pose_strategy")).model_dump(mode="json")
                if run.stage == "waiting_for_model_review":
                    if not isinstance(request, ModelPoseReviewRequest):
                        raise ValueError("請先選擇模型參照點，再標記兩個視角。")
                    context = json.loads((root / "pose_debug/model_reference/context.json").read_text(encoding="utf-8"))
                    reference = model_review_reference(context, root)
                    if request.reference_signature != reference["signature"] or {v.view_id for v in views} != set(context["fixed_view_ids"]):
                        raise ValueError("模型或對齊影像已變更，請重新讀取參照模型。")
                    objects = model_review_objects(context, root, reference, [p.model_point_id for p in request.correspondences])
                    fixed, checks = {}, {}
                    validation.update(validated_stage="reprojection", inlier_indices=[], cameras=checks)
                    for camera in ("top", "side"):
                        pixels = [[getattr(p, camera).x_px, getattr(p, camera).y_px] for p in request.correspondences]
                        pose, check = model_camera_pose(objects, pixels, intrinsics[camera]["camera_matrix"], settings["maximum_pnp_reprojection_error_px"])
                        fixed[camera], checks[camera] = pose.tolist(), check
                    validation.update(validated_stage="reprojection", inlier_indices=sorted(set(checks["top"]["inlier_indices"]) & set(checks["side"]["inlier_indices"])), cameras=checks)
                    if len(validation["inlier_indices"]) < 4:
                        raise ValueError("模型對齊至少需要四組通過兩個視角幾何檢查的參照點。")
                    registration = metric_model_registration(context["reference"], fixed, settings)
                    poses, quality = registration["poses"], registration["quality"]
                    quality["estimation_source"] = "manual_model_reference"
                    self._store_model_registration(run, registration)
                else:
                    if isinstance(request, ModelPoseReviewRequest):
                        raise ValueError("目前沒有可供對齊的參照模型，請使用雙鏡頭配對。")
                    poses, quality = estimate_manual_stereo_pose(
                        *frames, intrinsics, settings, payload["request"]["correspondences"], diagnostics=validation,
                    )
            except (ValueError, cv2.error) as error:
                payload.update(validation=validation)
                write_json_atomic(review_path, payload)
                self._request_stereo_review(run, str(error))
                raise AnalysisError(str(error)) from error
            payload.update(accepted=True, quality=quality, validation=validation)
            write_json_atomic(review_path, payload)
            self._save_step(run, "estimating_stereo_pose", "rig", self._stereo_pose_signature(run),
                            {"poses": poses, "quality": quality}, outputs=[review_path, *paths])
            resumed = self._set_state(run, status="processing",
                                      stage="aligning_model_cameras" if isinstance(request, ModelPoseReviewRequest) else "estimating_stereo_pose",
                                      clear_error=True)
            try:
                if not self._runner.start(analysis_id):
                    raise AnalysisError("背景工作尚未停止，請稍後再恢復分析。")
            except Exception:
                self._set_state(resumed, status="paused")
                raise
            self._log(resumed, "INFO", "人工雙鏡頭配對通過幾何檢查，已從保存的步驟繼續分析。")
            return resumed

    def _save_step(self, run: AnalysisRun, stage: str, item: str, signature: str, payload: dict, *, outputs=()):
        with StepJournal(self._artifacts(run).root) as journal:
            journal.save(stage, item, signature, payload, outputs=outputs)

    def _store_model_registration(self, run, registration):
        # Registration remains valid when joint training publishes a new PLY.
        # Depending on context.json would invalidate the accepted manual pose.
        payload = {key: value for key, value in registration.items() if key != "outputs"}
        path = self._artifacts(run).root / "pose_debug/model_reference/registration.json"
        write_json_atomic(path, payload)
        self._save_step(run, "aligning_model_cameras", "registration",
                        self._stereo_pose_signature(run), payload, outputs=[path])

    @staticmethod
    def _reference_model_job(run, reference, training_views, *, alignment_preview=False):
        cameras = {view["camera_id"] for view in training_views}
        if alignment_preview:
            if (not cameras <= {"top", "side", "rotating"}
                    or sum(view["camera_id"] == "rotating" for view in training_views) < 6
                    or any(view.get("pose") is None for view in training_views)):
                raise AnalysisError("選點預覽至少需要六張已對齊的旋臂影像。")
        elif cameras != {"top", "side", "rotating"}:
            raise AnalysisError("初始 3DGS 必須包含已對齊的俯視、側視與旋臂影像。")
        return {"analysis_id": run.analysis_id, "round_key": training_views[0]["round_key"],
                "artifact_root": run.output_path, "backend": "gsplat_3dgs",
                "purpose": "camera_alignment_preview" if alignment_preview else "reference_model",
                "world_coordinate_unit": "relative", "geometry_signature": reference["signature"],
                "initial_sparse_path": reference["sparse_path"], "intrinsics_snapshot": run.intrinsics_snapshot,
                "selected_views": training_views,
                "camera_poses": [{"view_id": view["view_id"], "valid": True,
                                  "pose_source": view.get("pose_source") or "sfm",
                                  "rotation_matrix": np.asarray(view["pose"])[:3, :3].tolist(),
                                  "translation_vector_mm": np.asarray(view["pose"])[:3, 3].tolist()}
                                 for view in training_views],
                "background": run.parameters.get("background", {}),
                "parameters": {**run.parameters["reconstruction"], "use_constrained_bundle_adjustment": False,
                               "export_gaussians": True, "export_render_preview": True}}

    def _train_reference_model(self, run, job, output, cancel_event, *, item="model"):
        self._check_cancel(cancel_event)
        signature = step_signature({"training_version": PLANT_TRAINING_VERSION, "job": job})
        model = self._saved_step(run, "building_reference_model", item, signature)
        if model is None:
            def progress(stage, value, message):
                self._check_cancel(cancel_event)
                self._set_state(run, stage="building_alignment_preview" if item == "alignment_preview" else "building_reference_model",
                                current_frame=int(value * 100), total_frames=100,
                                progress=(.26 + value * .02) if item == "joint_model" else (.22 + value * .04))
            model = run_reconstruction_worker(job, output, cancel_event, progress_callback=progress)
            self._check_cancel(cancel_event)
            self._save_step(run, "building_reference_model", item, signature, model,
                            outputs=[Path(model["gaussian_model_path"]), *map(Path, model["preview_paths"])])
        return model, signature

    def _build_alignment_preview(self, run, context, reference_root, cancel_event):
        # A dense, trained preview makes physical landmarks identifiable before
        # all cameras register. Never invent a pose for an unregistered camera.
        training_views = [view for view in context["reference"]["views"] if view.get("pose") is not None]
        job = self._reference_model_job(run, context["reference"], training_views, alignment_preview=True)
        model, signature = self._train_reference_model(
            run, job, reference_root / "alignment_preview", cancel_event, item="alignment_preview",
        )
        quality = {**model["model_quality"], "representation": "alignment_3dgs", "purpose": "camera_alignment_preview"}
        model = {**model, "status": "awaiting_camera_alignment", "model_quality": quality}
        model_review_reference({**context, "model": model}, self._artifacts(run).root)
        return {**context, "model": model, "alignment_preview_signature": signature,
                "training_camera_counts": quality.get("training_camera_counts", {})}

    def _joint_reference_views(self, run, context, registration, views, undistorted_by_view):
        root = self._artifacts(run).root
        fixed_ids = set(context["fixed_view_ids"])
        round_keys = {view.round_key for view in views if view.view_id in fixed_ids}
        # Legacy contexts listed only one stereo pair. Expand that same round,
        # preserving accepted reference coordinates and manual camera alignment.
        fixed_views = [view for view in views if view.round_key in round_keys and view.camera_id in {"top", "side"}]
        if {view.camera_id for view in fixed_views} != {"top", "side"}:
            raise AnalysisError("共同建模缺少已對齊的俯視或側視影像。")
        poses = reference_space_fixed_poses(registration)
        training_views = [view for view in context["reference"]["views"] if view["camera_id"] == "rotating"]
        if not training_views:
            raise AnalysisError("共同建模缺少有效的旋臂姿態。")
        for view in fixed_views:
            metadata = undistorted_by_view[view.view_id]
            image = (root / metadata["undistorted_path"]).resolve()
            training_views.append({**view.model_dump(mode="json"), "undistorted_path": str(image),
                                   "valid_mask_path": str((root / metadata["valid_pixel_mask_path"]).resolve()),
                                   "undistorted_sha256": _sha256(image), "pose": poses[view.camera_id],
                                   "pose_source": "model_reference"})
        return training_views, fixed_views

    def _build_joint_reference_model(self, run, context, registration, views, undistorted_by_view, cancel_event):
        root = self._artifacts(run).root
        training_views, fixed_views = self._joint_reference_views(run, context, registration, views, undistorted_by_view)
        job = self._reference_model_job(run, context["reference"], training_views)
        job["artifact_root"] = str(root)
        signature = step_signature({"training_version": PLANT_TRAINING_VERSION, "job": job})
        initial = (context["model"].get("status") in {"pending", "awaiting_camera_alignment"}
                   or context["model"].get("model_quality", {}).get("representation") == "sfm_points")
        if context.get("model_signature") == signature:
            model = context["model"]
        else:
            self._write_processing_preview(run, fixed_views, message="本輪三鏡頭共同建模")
            model, signature = self._train_reference_model(
                run, job, root / "pose_debug/model_reference" / ("model" if initial else "joint_model"),
                cancel_event, item="model" if initial else "joint_model",
            )
        counts = model.get("model_quality", {}).get("training_camera_counts", {})
        if any(int(counts.get(camera, 0)) < 1 for camera in ("top", "side", "rotating")):
            raise AnalysisError("參照模型未完整使用俯視、側視與旋臂影像，請重新建模。")
        if context.get("model_signature") != signature:
            updated = {**context, "model": model, "model_signature": signature, "training_camera_counts": counts,
                       "fixed_training_view_ids": [view.view_id for view in fixed_views]}
            # Retain the alignment PLY and legacy models for existing drafts.
            # The final model has its own three-camera job and checkpoint.
            if context["model"].get("model_quality", {}).get("representation") == "alignment_3dgs":
                updated["alignment_preview"] = context["model"]
            elif not initial:
                updated["bootstrap_model"] = context.get("bootstrap_model", context["model"])
            write_json_atomic(root / "pose_debug/model_reference/context.json", updated)
            self._log(run, "INFO", f"參照模型共同訓練完成：俯視 {counts['top']} 張、側視 {counts['side']} 張、旋臂 {counts['rotating']} 張。")

    def _prepare_model_reference(self, run, views, undistorted_by_view, cancel_event):
        root = self._artifacts(run).root
        signature = self._stereo_pose_signature(run)
        saved = self._saved_step(run, "aligning_model_cameras", "registration", signature)
        if saved is not None:
            context = json.loads((root / "pose_debug/model_reference/context.json").read_text(encoding="utf-8"))
            self._store_model_registration(run, saved)
            self._build_joint_reference_model(run, context, saved, views, undistorted_by_view, cancel_event)
            return saved
        grouped = {}
        for view in views:
            grouped.setdefault(view.round_key, []).append(view)
        candidates = [items for items in grouped.values() if sum(v.camera_id == "rotating" for v in items) >= 6]
        if not candidates:
            raise AnalysisError("找不到至少六個角度的旋臂影像，無法先建立參照模型。")
        selected_round = candidates[0]
        pairs = {}
        for view in selected_round:
            if view.camera_id in {"top", "side"}:
                pairs.setdefault(view.snapshot_id, {})[view.camera_id] = view
        complete = [pair for pair in pairs.values() if {"top", "side"} <= pair.keys()]
        if not complete:
            raise AnalysisError("參照模型輪次缺少同一次擷取的俯視與側視影像。")
        fixed_pair = complete[len(complete) // 2]
        selected = [v for v in selected_round if v.camera_id in {"top", "side", "rotating"}]
        payloads = []
        for view in selected:
            metadata = undistorted_by_view[view.view_id]
            image = (root / metadata["undistorted_path"]).resolve()
            payloads.append({**view.model_dump(mode="json"), "undistorted_path": str(image),
                             "angle_deg": view.angle_deg if view.angle_deg is not None else view.motor_position_deg,
                             "valid_mask_path": str((root / metadata["valid_pixel_mask_path"]).resolve()),
                             "undistorted_sha256": _sha256(image)})
        reference_root = root / "pose_debug/model_reference"
        sfm_job = {"kind": "reference_sfm", "reference_action": "rotating", "artifact_root": str(root),
                   "selected_views": payloads, "intrinsics_snapshot": run.intrinsics_snapshot,
                   "parameters": run.parameters["pose_strategy"]}

        def progress(stage, value, message):
            self._check_cancel(cancel_event)
            self._set_state(run, stage=stage, current_frame=int(value * 100), total_frames=100,
                            progress=.18 + value * .04)

        reference = run_reconstruction_worker(sfm_job, reference_root / "sfm", cancel_event, progress_callback=progress)
        self._save_step(run, "estimating_reference_poses", "reference", reference["signature"],
                        {"backend": reference["quality"]["feature_backend"], "quality": reference["quality"]},
                        outputs=list(Path(reference["sparse_path"]).glob("*.bin")))
        context_path = reference_root / "context.json"
        context = {"reference": reference, "fixed_view_ids": [fixed_pair[c].view_id for c in ("top", "side")],
                   "model": {"status": "pending", "model_quality": {"coordinate_unit": "relative"}}}
        if context_path.is_file():
            previous = json.loads(context_path.read_text(encoding="utf-8"))
            if previous["reference"]["signature"] == reference["signature"]:
                # A previously trained reference/draft remains usable while
                # migrating the old rotating-only workflow.
                context = previous
        registration = None
        reason = None
        try:
            fixed, consensus = aggregate_fixed_camera_poses(reference["views"], orbit_radius=reference["orbit"]["radius"])
            if set(fixed) == {"top", "side"}:
                registration = metric_model_registration(reference, fixed, run.parameters["pose_strategy"])
                registration["quality"]["fixed_pose_consensus"] = consensus
        except ValueError as error:
            reason = str(error)
        self._write_processing_preview(run, [fixed_pair["top"], fixed_pair["side"]], message="對齊三鏡頭")
        self._set_state(run, stage="aligning_model_cameras", current_frame=0, total_frames=2, progress=.22)
        try:
            if registration is None:
                aligned = run_reconstruction_worker({**sfm_job, "reference_action": "register_fixed",
                    "reference_root": str(reference_root / "sfm"), "source_signature": reference["signature"]},
                    reference_root / "alignment", cancel_event, progress_callback=progress)
                fixed, consensus = aggregate_fixed_camera_poses(aligned["views"], orbit_radius=reference["orbit"]["radius"])
                if set(fixed) != {"top", "side"}:
                    missing = "、".join({"top": "俯視", "side": "側視"}[camera] for camera in ("top", "side") if camera not in fixed)
                    raise ValueError(f"{missing}尚未對齊，請選四組三維參照點；通過後才開始三鏡頭 3DGS 建模。")
                registration = metric_model_registration(reference, fixed, run.parameters["pose_strategy"])
                registration["quality"]["fixed_pose_consensus"] = consensus
        except (AnalysisError, ValueError) as error:
            reason = str(error)
        if registration is None:
            self._check_cancel(cancel_event)
            if (context["model"].get("status") == "pending"
                    or context["model"].get("model_quality", {}).get("representation") == "sfm_points"):
                context = self._build_alignment_preview(run, context, reference_root, cancel_event)
            write_json_atomic(context_path, context)
            raise AnalysisReviewRequiredError(reason or "請先完成三鏡頭對齊，再開始 3DGS 建模。")
        write_json_atomic(context_path, context)
        self._store_model_registration(run, registration)
        self._build_joint_reference_model(run, context, registration, views, undistorted_by_view, cancel_event)
        return registration

    def _run_round_preprocessing(
        self,
        run: AnalysisRun,
        cancel_event: Event,
    ) -> AnalysisRun:
        self._check_cancel(cancel_event)
        rounds = self.repository.list_rounds(run.analysis_id)
        views = self.repository.list_views(run.analysis_id)
        if not rounds or not views:
            raise AnalysisError("分析缺少 Round／View 清單。")
        self._clear_processing_preview(run)
        self._set_state(
            run,
            stage="snapshotting_intrinsics",
            current_frame=0,
            total_frames=len(views),
            progress=0.02,
        )

        image_backends: dict[str, int] = {}
        last_preview_update = float("-inf")

        def update_image_backends(counts: dict[str, int]) -> None:
            if not image_backends:
                self._log(run, "INFO", f"影像前處理自動並行 {counts['workers']} 個執行緒。")
            image_backends.update(counts)

        def update_undistortion(index: int, total: int) -> None:
            nonlocal last_preview_update
            self._check_cancel(cancel_event)
            now = monotonic()
            if index != total and now - last_preview_update < .5:
                return
            last_preview_update = now
            current = run
            self._write_processing_preview(
                current, [views[index - 1]], message="目前完成去畸變的影像",
            )
            self._set_state(
                current,
                stage="undistorting_images",
                current_frame=index,
                total_frames=total,
                progress=0.02 + (index / max(total, 1)) * 0.16,
                image_probe_backends=image_backends,
            )

        try:
            undistorted = undistort_analysis_views(
                views,
                run.intrinsics_snapshot,
                self._artifacts(run).root,
                cancel_check=lambda: self._check_cancel(cancel_event),
                progress_callback=update_undistortion,
                backend_callback=update_image_backends,
                source_manifest=run.parameters.get("source_manifest", run.parameters.get("input_manifest", [])),
            )
        except (OSError, TypeError, ValueError, cv2.error) as error:
            raise AnalysisError(f"分析影像去畸變失敗：{error}") from error

        undistorted_by_view = {
            item["view_id"]: item
            for item in undistorted
        }
        artifacts = self._artifacts(run)
        undistorted_intrinsics = {
            camera_id: {
                "camera_matrix": snapshot["undistorted_camera_matrix"],
                "distortion_coefficients": [0.0, 0.0, 0.0, 0.0, 0.0],
                "camera_model": "opencv",
                "width": snapshot["analysis_image_width"],
                "height": snapshot["analysis_image_height"],
            }
            for camera_id, snapshot in run.intrinsics_snapshot.items()
        }
        pose_strategy = run.parameters.get("pose_strategy")
        markerless = not run.aruco_layout_snapshot
        pose_settings = None if markerless else self._pose_settings_for_run(run)
        fixed_stereo_poses = None
        stereo_quality: dict[str, object] = {}
        pose_signature = step_signature({"rig": self._stereo_pose_signature(run), "round_pipeline_version": 2})
        model_registration = None
        if markerless and run.method_name == "rotating":
            model_registration = self._prepare_model_reference(run, views, undistorted_by_view, cancel_event)
            fixed_stereo_poses, stereo_quality = model_registration["poses"], model_registration["quality"]
        elif markerless:
            try:
                markerless_settings = MarkerlessPoseSettings.model_validate(
                    pose_strategy
                ).model_dump(mode="json")
                all_frames = [{
                    "capture_id": view.capture_id,
                    "camera_id": view.camera_id,
                    "relative_path": undistorted_by_view[view.view_id]["undistorted_path"],
                    "file_path": str(
                        self._artifacts(run).root
                        / undistorted_by_view[view.view_id]["undistorted_path"]
                    ),
                    "timestamp": view.timestamp,
                    "snapshot_id": view.snapshot_id,
                    "round_key": view.round_key,
                } for view in views]
                views_by_capture = {view.capture_id: view for view in views}

                def update_stereo_preview(index, total, top, side, diagnostics):
                    self._check_cancel(cancel_event)
                    detail = dict(diagnostics)
                    match_image = detail.pop("match_image_path", None)
                    self._write_processing_preview(
                        run,
                        [views_by_capture[frame["capture_id"]] for frame in (top, side)],
                        artifact_path=(
                            Path(match_image).relative_to(artifacts.root).as_posix()
                            if match_image else None
                        ),
                        message=f"雙鏡頭姿態估計：影像組 {index} / {total}",
                        diagnostics=detail,
                    )
                    self._set_state(
                        run,
                        stage="estimating_stereo_pose",
                        current_frame=index,
                        total_frames=total,
                        progress=0.18,
                    )

                saved = self._saved_step(run, "estimating_stereo_pose", "rig", self._stereo_pose_signature(run))
                if saved is not None:
                    fixed_stereo_poses, stereo_quality = saved["poses"], saved["quality"]
                else:
                    fixed_stereo_poses, stereo_quality = estimate_fixed_stereo_pose(
                        all_frames, undistorted_intrinsics, markerless_settings,
                        cancel_check=lambda: self._check_cancel(cancel_event),
                        debug_directory=artifacts.root / "pose_debug" / "stereo",
                        progress_callback=update_stereo_preview,
                    )
                    self._save_step(run, "estimating_stereo_pose", "rig", self._stereo_pose_signature(run),
                                    {"poses": fixed_stereo_poses, "quality": stereo_quality})
            except StereoPoseEstimationError as error:
                raise AnalysisReviewRequiredError(str(error)) from error
            except (ValidationError, ValueError, cv2.error) as error:
                raise AnalysisError(f"無標記雙鏡頭姿態估計失敗：{error}") from error
        use_feature_refinement = (
            bool(pose_strategy.get("use_bundle_adjustment", True))
            if isinstance(pose_strategy, Mapping)
            else True
        )
        views_by_round: dict[str, list] = {}
        for view in views:
            views_by_round.setdefault(view.round_key, []).append(view)
        stored_poses: list[AnalysisCameraPoseResult] = []
        updated_views = []
        round_quality_payloads: list[dict[str, Any]] = []
        pose_estimation_version = run.pose_estimation_version or "unknown"
        failed_round_count = 0
        existing_poses_by_round: dict[str, list[AnalysisCameraPoseResult]] = {}
        for pose in self.repository.list_camera_poses(run.analysis_id):
            existing_poses_by_round.setdefault(pose.round_key, []).append(pose)
        previous_quality = {
            str(item.get("round_key")): item
            for item in run.pose_quality.get("rounds", [])
            if isinstance(item, Mapping) and item.get("round_key")
        }

        for round_index, round_item in enumerate(rounds, start=1):
            self._check_cancel(cancel_event)
            round_views = views_by_round.get(round_item.round_key, [])
            saved = self._saved_step(run, "estimating_camera_poses", round_item.round_key, pose_signature)
            if saved is not None:
                stored_poses.extend(AnalysisCameraPoseResult.model_validate(item) for item in saved["poses"])
                updated_views.extend(AnalysisView.model_validate(item) for item in saved["views"])
                round_quality_payloads.append(saved["quality"])
                pose_estimation_version = saved["version"]
                failed_round_count += int(saved["failed"])
                continue
            if round_item.status in {"model_completed", "tip_completed"} and run.pose_quality.get("round_pipeline_version") == 2:
                stored_poses.extend(
                    existing_poses_by_round.get(round_item.round_key, [])
                )
                updated_views.extend(round_views)
                previous = previous_quality.get(round_item.round_key)
                if previous is not None:
                    round_quality_payloads.append(previous)
                continue
            if round_item.status == "incomplete":
                failed_round_count += 1
                updated_views.extend(round_views)
                continue
            derived_frames = []
            self._write_processing_preview(
                run, round_views, message=f"{round_item.round_id} 的姿態估計輸入",
            )
            derived_paths: dict[str, Path] = {}
            for view in round_views:
                metadata = undistorted_by_view[view.view_id]
                derived_path = artifacts.root / metadata["undistorted_path"]
                derived_paths[view.view_id] = derived_path
                derived_frames.append({
                    "view_id": view.view_id,
                    "capture_id": view.capture_id,
                    "camera_id": view.camera_id,
                    "relative_path": metadata["undistorted_path"],
                    "file_path": str(derived_path),
                    "timestamp": view.timestamp,
                    "angle_deg": view.angle_deg,
                    "motor_position_deg": view.motor_position_deg,
                    "snapshot_id": view.snapshot_id,
                    "round_key": view.round_key,
                })

            def update_pose_stage(stage: str, progress: float) -> None:
                self._check_cancel(cancel_event)
                current = run
                round_progress = (
                    (round_index - 1) + min(max(progress, 0), 1)
                ) / max(len(rounds), 1)
                self._set_state(
                    current,
                    stage=stage,
                    current_frame=round_index,
                    total_frames=len(rounds),
                    progress=0.18 + round_progress * 0.14,
                )

            if model_registration is not None:
                update_pose_stage("estimating_camera_poses", .02)
                result = align_model_camera_poses(derived_frames, model_registration,
                    required_camera_ids=self._required_camera_ids(run.method_name))
            elif markerless:
                update_pose_stage("estimating_camera_poses", 0.02)
                result = align_markerless_camera_poses(
                    derived_frames,
                    undistorted_intrinsics,
                    markerless_settings,
                    fixed_stereo_poses,
                    required_camera_ids=self._required_camera_ids(run.method_name),
                    cancel_check=lambda: self._check_cancel(cancel_event),
                )
            else:
                result = align_dataset_camera_poses(
                    derived_frames,
                    undistorted_intrinsics,
                    pose_settings,
                    required_camera_ids=self._required_camera_ids(
                        run.method_name
                    ),
                    debug_directory=(
                        artifacts.root
                        / "pose_debug"
                        / f"round_{round_index:04d}"
                    ),
                    use_feature_refinement=use_feature_refinement,
                    stage_callback=update_pose_stage,
                    cancel_check=lambda: self._check_cancel(cancel_event),
                )
            pose_estimation_version = result.pose_estimation_version
            view_by_capture = {
                (view.capture_id, view.camera_id): view
                for view in round_views
            }
            round_poses: list[AnalysisCameraPoseResult] = []
            for pose in result.camera_poses:
                view = view_by_capture.get((pose.input_id, pose.camera_id))
                if view is None:
                    continue
                world_to_camera = (
                    np.asarray(
                        pose.world_to_camera_matrix,
                        dtype=np.float64,
                    )
                    if pose.world_to_camera_matrix is not None
                    else None
                )
                camera_to_world = (
                    np.asarray(
                        pose.camera_to_world_matrix,
                        dtype=np.float64,
                    )
                    if pose.camera_to_world_matrix is not None
                    else None
                )
                source = {
                    "rig_stereo": "rig_stereo",
                    "aruco": "aruco",
                    "aruco_refined": "feature_refined",
                    "sfm": "feature_refined",
                    "motor_prior": "motor_prior",
                    "interpolated": "interpolated",
                }.get(pose.source, "invalid")
                round_poses.append(
                    AnalysisCameraPoseResult(
                        analysis_id=run.analysis_id,
                        round_key=view.round_key,
                        view_id=view.view_id,
                        camera_id=view.camera_id,
                        rotation_matrix=(
                            world_to_camera[:3, :3]
                            .astype(float)
                            .tolist()
                            if world_to_camera is not None
                            else None
                        ),
                        translation_vector_mm=(
                            world_to_camera[:3, 3]
                            .astype(float)
                            .tolist()
                            if world_to_camera is not None
                            else None
                        ),
                        camera_center_world_mm=(
                            camera_to_world[:3, 3]
                            .astype(float)
                            .tolist()
                            if camera_to_world is not None
                            else None
                        ),
                        detected_marker_ids=pose.visible_marker_ids,
                        detected_corner_count=(
                            pose.visible_marker_count * 4
                        ),
                        aruco_reprojection_error_px=(
                            pose.aruco_reprojection_error_px
                        ),
                        refinement_reprojection_error_px=(
                            pose.feature_reprojection_error_px
                        ),
                        pose_source=source,
                        valid=pose.resolved,
                        quality_warnings=list(pose.quality_warnings),
                        failure_reason=pose.failure_reason,
                    )
                )
            quality = evaluate_round_quality(
                round_item.round_key,
                round_views,
                derived_paths,
            )
            pose_by_view = {
                item.view_id: item
                for item in round_poses
            }
            selection = select_round_reconstruction_views(
                round_views,
                pose_by_view,
                quality.view_quality,
            )
            updated_views.extend(selection.views)
            stored_poses.extend(round_poses)
            selected = [
                view
                for view in selection.views
                if view.selected_for_reconstruction
            ]
            selected_cameras = {view.camera_id for view in selected}
            required_cameras = set(
                self._required_camera_ids(run.method_name)
            )
            failures = list(result.quality.required_camera_failures)
            missing_selected = sorted(required_cameras - selected_cameras)
            if missing_selected:
                failures.append(
                    "無法選出必要模型視角："
                    + "、".join(missing_selected)
                )
            next_status = (
                "ready_tip_only"
                if round_item.status == "ready_tip_only" and not failures
                else "preprocessed"
                if not failures
                else "failed"
            )
            if failures:
                failed_round_count += 1
            updated_round = round_item.model_copy(
                update={
                    "status": next_status,
                    "static_scene_score": quality.static_scene_score,
                    "failure_reason": "；".join(
                        dict.fromkeys(failures)
                    ) or None,
                }
            )
            self.repository.update_round(updated_round)
            quality_payload = {
                **quality.as_dict(),
                "pose_quality": result.quality.model_dump(mode="json"),
                "selection": {
                    "selected_view_ids": list(
                        selection.selected_view_ids
                    ),
                    "warnings": list(selection.warnings),
                },
            }
            round_quality_payloads.append(quality_payload)
            artifacts.write_round_pose_results(
                round_item.round_key,
                round_poses,
                detections=result.aruco_detections,
                quality=result.quality.model_dump(mode="json"),
                pose_estimation_version=result.pose_estimation_version,
            )
            artifacts.write_round_quality(
                round_item.round_key,
                quality_payload,
            )
            self._save_step(run, "estimating_camera_poses", round_item.round_key, pose_signature, {
                "poses": [item.model_dump(mode="json") for item in round_poses],
                "views": [item.model_dump(mode="json") for item in selection.views],
                "quality": quality_payload, "version": pose_estimation_version, "failed": bool(failures),
            })

        last_consistency_update = float("-inf")

        def update_consistency_progress(index: int, total: int) -> None:
            nonlocal last_consistency_update
            self._check_cancel(cancel_event)
            now = monotonic()
            if index != total and now - last_consistency_update < .5:
                return
            last_consistency_update = now
            self._set_state(
                run,
                stage="checking_pose_consistency",
                current_frame=index,
                total_frames=total,
                progress=0.32,
            )

        stored_poses, fixed_camera_consistency = evaluate_fixed_camera_pose_consistency(
            stored_poses,
            cancel_check=lambda: self._check_cancel(cancel_event),
            progress_callback=update_consistency_progress,
        )
        final_poses_by_round: dict[
            str,
            list[AnalysisCameraPoseResult],
        ] = {}
        for pose in stored_poses:
            final_poses_by_round.setdefault(
                pose.round_key,
                [],
            ).append(pose)
        self._set_state(
            run,
            stage="saving_camera_poses",
            current_frame=0,
            total_frames=len(final_poses_by_round),
            progress=0.32,
        )
        last_export_update = float("-inf")
        for index, (round_key, round_poses) in enumerate(final_poses_by_round.items(), start=1):
            self._check_cancel(cancel_event)
            artifacts.write_round_camera_poses(
                round_key,
                round_poses,
            )
            now = monotonic()
            if index == len(final_poses_by_round) or now - last_export_update >= .5:
                last_export_update = now
                self._set_state(
                    run,
                    stage="saving_camera_poses",
                    current_frame=index,
                    total_frames=len(final_poses_by_round),
                    progress=0.32,
                )
        self._check_cancel(cancel_event)
        self.repository.replace_camera_poses(run.analysis_id, stored_poses)
        self.repository.update_views(updated_views)
        pose_payload = [
            item.model_dump(mode="json")
            for item in stored_poses
        ]
        aggregate_pose_quality = {
            "round_pipeline_version": 2,
            "coordinate_space": "undistorted",
            "world_scale": stereo_quality if markerless else {"scale_source": "aruco"},
            "fixed_camera_consistency": fixed_camera_consistency,
            "rounds": round_quality_payloads,
        }
        self.repository.update_pose_alignment(
            run.analysis_id,
            camera_pose_results=pose_payload,
            pose_estimation_version=pose_estimation_version,
            pose_quality=aggregate_pose_quality,
            updated_at=utc_now_iso(),
        )
        self.repository.update_state(
            run.analysis_id,
            updated_at=utc_now_iso(),
            failed_round_count=failed_round_count,
        )
        self._check_cancel(cancel_event)
        artifacts.write_aggregated_pose_results(
            stored_poses,
            pose_estimation_version=pose_estimation_version,
            round_quality=round_quality_payloads,
            fixed_camera_consistency=fixed_camera_consistency,
        )
        artifacts.write_round_index(
            self.repository.list_rounds(run.analysis_id),
            self.repository.list_views(run.analysis_id),
        )
        updated = self._require_run(run.analysis_id)
        artifacts.write_run(updated)
        if failed_round_count >= len(rounds):
            raise AnalysisError("所有 Round 的相機姿態或代表視角皆無法使用。")
        return updated

    def _round_reconstruction_job(
        self,
        run: AnalysisRun,
        round_key: str,
    ) -> dict[str, Any]:
        artifacts = self._artifacts(run)
        try:
            undistorted_items = artifacts.read_undistortion_manifest()
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise AnalysisError("分析的去畸變影像清單遺失或格式無效。") from error
        undistorted_by_view = {
            str(item.get("view_id")): item
            for item in undistorted_items
            if item.get("view_id")
        }
        selected_views = [
            item
            for item in self.repository.list_views(
                run.analysis_id,
                round_key,
            )
            if item.selected_for_reconstruction
        ]
        if not selected_views:
            raise AnalysisError("本輪沒有已選取的模型 View。")
        poses = self.repository.list_camera_poses(
            run.analysis_id,
            round_key,
        )
        valid_pose_ids = {
            item.view_id
            for item in poses
            if item.valid
        }
        selected_ids = {item.view_id for item in selected_views}
        missing_pose_ids = sorted(selected_ids - valid_pose_ids)
        if missing_pose_ids:
            raise AnalysisError(
                "本輪模型 View 缺少有效姿態："
                + "、".join(missing_pose_ids)
            )
        selected_payloads = []
        for view in selected_views:
            metadata = undistorted_by_view.get(view.view_id)
            if metadata is None:
                raise AnalysisError(
                    f"View {view.view_id} 缺少去畸變衍生資料。"
                )
            image_relative = str(metadata.get("undistorted_path") or "")
            mask_relative = str(
                metadata.get("valid_pixel_mask_path") or ""
            )
            image_path = (artifacts.root / image_relative).resolve()
            mask_path = (artifacts.root / mask_relative).resolve()
            if not image_path.is_file():
                raise AnalysisError(
                    f"View {view.view_id} 的去畸變影像不存在。"
                )
            if not mask_path.is_file():
                raise AnalysisError(
                    f"View {view.view_id} 的有效像素遮罩不存在。"
                )
            selected_payloads.append({
                **view.model_dump(mode="json"),
                "undistorted_path": str(image_path),
                "valid_mask_path": str(mask_path),
                "undistorted_sha256": _sha256(image_path),
            })
        reconstruction = run.parameters.get("reconstruction")
        if not isinstance(reconstruction, Mapping):
            raise AnalysisError("三維模型設定格式無效。")
        pose_strategy = run.parameters.get("pose_strategy")
        use_bundle_adjustment = (
            bool(pose_strategy.get("use_bundle_adjustment", True))
            if isinstance(pose_strategy, Mapping)
            else True
        )
        background = run.parameters.get("background")
        if not isinstance(background, Mapping):
            raise AnalysisError("背景處理設定格式無效。")
        return {
            "schema_version": "1.0",
            "analysis_id": run.analysis_id,
            "record_id": run.record_id,
            "round_key": round_key,
            "artifact_root": str(artifacts.root),
            "backend": str(reconstruction.get("backend") or ""),
            "parameters": {
                **dict(reconstruction),
                "use_constrained_bundle_adjustment": (
                    use_bundle_adjustment
                ),
            },
            "background": dict(background),
            "selected_views": selected_payloads,
            "camera_poses": [
                item.model_dump(mode="json")
                for item in poses
                if item.view_id in selected_ids
            ],
            "intrinsics_snapshot": run.intrinsics_snapshot,
            "aruco_layout_snapshot": run.aruco_layout_snapshot,
            "coordinate_space": "undistorted",
            "world_coordinate_unit": "millimetre",
            "source_images_are_read_only": True,
        }

    def _apply_bundle_adjusted_camera_poses(
        self,
        run: AnalysisRun,
        round_key: str,
        refined_payloads: object,
        bundle_adjustment_quality: object,
    ) -> None:
        if not isinstance(refined_payloads, list):
            raise AnalysisError("模型工作回傳的姿態精修結果格式無效。")
        quality = (
            dict(bundle_adjustment_quality)
            if isinstance(bundle_adjustment_quality, Mapping)
            else {}
        )
        all_poses = self.repository.list_camera_poses(run.analysis_id)
        pose_by_view = {
            item.view_id: item
            for item in all_poses
            if item.round_key == round_key
        }
        updated_by_view: dict[str, AnalysisCameraPoseResult] = {}
        for payload in refined_payloads:
            if not isinstance(payload, Mapping):
                raise AnalysisError("模型工作回傳的單筆姿態格式無效。")
            if not payload.get("refined"):
                continue
            view_id = str(payload.get("view_id") or "")
            stored = pose_by_view.get(view_id)
            if stored is None or stored.camera_id != "rotating":
                raise AnalysisError("姿態精修結果指向不存在的旋臂 View。")
            matrix = np.asarray(
                payload.get("world_to_camera_matrix"),
                dtype=np.float64,
            )
            if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
                raise AnalysisError("姿態精修矩陣格式無效。")
            translation_change = float(
                payload.get("translation_change_mm") or 0.0
            )
            rotation_change = float(
                payload.get("rotation_change_deg") or 0.0
            )
            if translation_change > 50.0 or rotation_change > 10.0:
                raise AnalysisError(
                    "姿態精修結果偏離初始姿態上限。"
                )
            camera_to_world = np.linalg.inv(matrix)
            warning = (
                "已使用固定雙鏡頭世界基準與旋臂位置先驗完成"
                "受約束多視角 Bundle Adjustment。"
            )
            warnings = list(stored.quality_warnings)
            if warning not in warnings:
                warnings.append(warning)
            updated_by_view[view_id] = stored.model_copy(
                update={
                    "rotation_matrix": (
                        matrix[:3, :3].astype(float).tolist()
                    ),
                    "translation_vector_mm": (
                        matrix[:3, 3].astype(float).tolist()
                    ),
                    "camera_center_world_mm": (
                        camera_to_world[:3, 3].astype(float).tolist()
                    ),
                    "pose_source": "feature_refined",
                    "quality_warnings": warnings,
                }
            )

        updated_poses = [
            updated_by_view.get(item.view_id, item)
            for item in all_poses
        ]
        if updated_by_view:
            self.repository.replace_camera_poses(
                run.analysis_id,
                updated_poses,
            )
            views = self.repository.list_views(
                run.analysis_id,
                round_key,
            )
            self.repository.update_views([
                (
                    view.model_copy(
                        update={"pose_status": "feature_refined"}
                    )
                    if view.view_id in updated_by_view
                    else view
                )
                for view in views
            ])

        pose_quality = deepcopy(run.pose_quality)
        round_quality = list(pose_quality.get("rounds") or [])
        found = False
        for index, item in enumerate(round_quality):
            if (
                isinstance(item, Mapping)
                and item.get("round_key") == round_key
            ):
                round_quality[index] = {
                    **dict(item),
                    "bundle_adjustment": quality,
                }
                found = True
                break
        if not found:
            round_quality.append({
                "round_key": round_key,
                "bundle_adjustment": quality,
            })
        pose_quality["rounds"] = round_quality
        self.repository.update_pose_alignment(
            run.analysis_id,
            camera_pose_results=[
                item.model_dump(mode="json")
                for item in updated_poses
            ],
            pose_estimation_version=(
                run.pose_estimation_version or "unknown"
            ),
            pose_quality=pose_quality,
            updated_at=utc_now_iso(),
        )
        artifacts = self._artifacts(run)
        artifacts.write_round_camera_poses(
            round_key,
            [
                item
                for item in updated_poses
                if item.round_key == round_key
            ],
        )
        round_quality_item = next(
            (
                dict(item)
                for item in round_quality
                if (
                    isinstance(item, Mapping)
                    and item.get("round_key") == round_key
                )
            ),
            {
                "round_key": round_key,
                "bundle_adjustment": quality,
            },
        )
        artifacts.write_round_quality(
            round_key,
            round_quality_item,
        )
        artifacts.write_aggregated_pose_results(
            updated_poses,
            pose_estimation_version=(
                run.pose_estimation_version or "unknown"
            ),
            round_quality=round_quality,
            fixed_camera_consistency=dict(
                pose_quality.get("fixed_camera_consistency") or {}
            ),
        )

    def _run_round_models(
        self,
        run: AnalysisRun,
        cancel_event: Event,
    ) -> AnalysisRun:
        if run.method_name != "rotating":
            return run
        reconstruction = run.parameters.get("reconstruction")
        if not isinstance(reconstruction, Mapping):
            raise AnalysisError("三維模型設定格式無效。")
        backend_name = str(reconstruction.get("backend") or "")
        readiness = self._reconstruction_backends.check(backend_name)
        if not readiness.get("available"):
            raise AnalysisError(
                "；".join(readiness.get("errors") or ["模型後端不可用。"])
            )
        self.repository.update_reconstruction_metadata(
            run.analysis_id,
            backend=backend_name,
            backend_version=str(readiness.get("backend_version") or "unknown"),
            environment=dict(readiness.get("environment") or {}),
            updated_at=utc_now_iso(),
        )
        artifacts = self._artifacts(run)
        artifacts.write_reconstruction_environment(readiness)
        rounds = self.repository.list_rounds(run.analysis_id)
        candidates = [item for item in rounds if item.status in {"preprocessed", "reconstructing"}]
        if not candidates:
            if any(
                item.status in {
                    "model_completed",
                    "model_failed",
                    "tip_completed",
                    "tip_only",
                    "tip_invalid",
                }
                for item in rounds
            ):
                return self._require_run(run.analysis_id)
            raise AnalysisError("沒有通過前處理的 Round 可建立三維模型。")

        completed = sum(item.status == "model_completed" for item in rounds)
        failed = sum(item.status in {"failed", "model_failed"} for item in rounds)
        for index, round_item in enumerate(candidates, start=1):
            self._check_cancel(cancel_event)
            self._write_processing_preview(
                run,
                self.repository.list_views(run.analysis_id, round_item.round_key),
                message=f"{round_item.round_id} 的全部有效建模影像",
            )
            model_id = f"{run.analysis_id}:{round_item.mode_id}:{round_item.round_id}:model"
            running_model = RoundModelResult(
                analysis_id=run.analysis_id,
                round_key=round_item.round_key,
                model_id=model_id,
                backend=backend_name,
                backend_version=str(readiness.get("backend_version") or "unknown"),
                repository_url=readiness.get("repository_url"),
                repository_commit=readiness.get("repository_commit"),
                license=readiness.get("license"),
                environment=dict(readiness.get("environment") or {}),
                status="processing",
                source_view_ids=[],
            )
            self.repository.upsert_round_model(running_model)
            reconstructing_round = round_item.model_copy(
                update={"status": "reconstructing", "failure_reason": None}
            )
            self.repository.update_round(reconstructing_round)
            artifacts.write_round_model_result(running_model)
            last_worker_log_bucket = -1

            def update_worker_progress(
                stage: str,
                progress: float,
                message: str | None,
            ) -> None:
                nonlocal last_worker_log_bucket
                self._check_cancel(cancel_event)
                overall = ((index - 1) + progress) / max(len(candidates), 1)
                current = run
                self._save_step(run, stage, round_item.round_key, "", {"progress": progress, "message": message})
                self._set_state(
                    current,
                    status="reconstructing",
                    stage=stage,
                    current_frame=index,
                    total_frames=len(candidates),
                    progress=0.32 + overall * 0.36,
                )
                log_bucket = int(min(max(progress, 0.0), 1.0) * 20)
                if message and log_bucket != last_worker_log_bucket:
                    last_worker_log_bucket = log_bucket
                    self._log(current, "INFO", f"{round_item.round_id}：{message}")

            try:
                job = self._round_reconstruction_job(
                    run,
                    round_item.round_key,
                )
                worker_result = run_reconstruction_worker(
                    job,
                    round_artifact_directory(
                        artifacts.root,
                        round_item.round_key,
                    ),
                    cancel_event,
                    progress_callback=update_worker_progress,
                )
                self._apply_bundle_adjusted_camera_poses(
                    self._require_run(run.analysis_id),
                    round_item.round_key,
                    worker_result.get("refined_camera_poses") or [],
                    (
                        worker_result.get("model_quality", {})
                        .get("sparse_initialization", {})
                        .get("bundle_adjustment", {})
                    ),
                )
                relative_path = lambda value: (
                    str(Path(value).resolve().relative_to(artifacts.root))
                    if value
                    else None
                )
                completed_model = running_model.model_copy(
                    update={
                        "status": "completed",
                        "repository_url": worker_result.get(
                            "repository_url"
                        ),
                        "repository_commit": worker_result.get(
                            "repository_commit"
                        ),
                        "license": worker_result.get("license"),
                        "environment": dict(
                            worker_result.get("environment") or {}
                        ),
                        "source_view_ids": list(
                            worker_result.get("source_view_ids") or []
                        ),
                        "model_path": relative_path(
                            worker_result.get("gaussian_model_path")
                        ),
                        "plant_model_path": relative_path(
                            worker_result.get(
                                "plant_gaussian_model_path"
                            )
                        ),
                        "background_model_path": relative_path(
                            worker_result.get(
                                "background_gaussian_model_path"
                            )
                        ),
                        "point_cloud_path": relative_path(
                            worker_result.get("point_cloud_path")
                        ),
                        "preview_paths": [
                            path
                            for path in (
                                relative_path(item)
                                for item in worker_result.get(
                                    "preview_paths",
                                    [],
                                )
                            )
                            if path is not None
                        ],
                        "gaussian_count": worker_result.get("gaussian_count"),
                        "point_count": worker_result.get("point_count"),
                        "training_iterations": worker_result.get(
                            "training_iterations"
                        ),
                        "training_duration_seconds": worker_result.get(
                            "training_duration_seconds"
                        ),
                        "model_quality": {
                            **dict(worker_result.get("model_quality") or {}),
                            "checkpoint_path": relative_path(
                                worker_result.get("checkpoint_path")
                            ),
                        },
                        "failure_reason": None,
                    }
                )
                self.repository.upsert_round_model(completed_model)
                self.repository.update_round(
                    reconstructing_round.model_copy(
                        update={
                            "status": "model_completed",
                            "model_result_id": model_id,
                            "failure_reason": None,
                        }
                    )
                )
                artifacts.write_round_model_result(completed_model)
                self._save_step(run, "reconstructing_round_model", round_item.round_key, "",
                                {"backend": "cuda", "model_id": model_id,
                                 "iterations": completed_model.training_iterations})
                completed += 1
                self._log(
                    run,
                    "INFO",
                    f"{round_item.round_id} 三維模型建立完成。",
                )
            except OperationCancelledError:
                checkpoint = (
                    round_artifact_directory(
                        artifacts.root,
                        round_item.round_key,
                    )
                    / "model"
                    / "checkpoint"
                    / "latest.pt"
                )
                cancelled_model = running_model.model_copy(
                    update={
                        "status": "cancelled",
                        "model_quality": {
                            "checkpoint_path": (
                                str(checkpoint.relative_to(artifacts.root))
                                if checkpoint.is_file()
                                else None
                            ),
                        },
                        "failure_reason": "三維模型工作已由使用者取消。",
                    }
                )
                self.repository.upsert_round_model(cancelled_model)
                self.repository.update_round(
                    reconstructing_round.model_copy(
                        update={
                            "status": "preprocessed" if getattr(cancel_event, "pause_requested", False) else "cancelled",
                            "failure_reason": cancelled_model.failure_reason,
                        }
                    )
                )
                artifacts.write_round_model_result(cancelled_model)
                for pending in candidates[index:]:
                    if getattr(cancel_event, "pause_requested", False):
                        break
                    self.repository.update_round(
                        pending.model_copy(
                            update={
                                "status": "cancelled",
                                "failure_reason": "分析在執行本輪前已取消。",
                            }
                        )
                    )
                raise
            except Exception as error:
                reason = public_error_detail(error)
                checkpoint = (
                    round_artifact_directory(
                        artifacts.root,
                        round_item.round_key,
                    )
                    / "model"
                    / "checkpoint"
                    / "latest.pt"
                )
                failed_model = running_model.model_copy(
                    update={
                        "status": "failed",
                        "model_quality": {
                            "checkpoint_path": (
                                str(checkpoint.relative_to(artifacts.root))
                                if checkpoint.is_file()
                                else None
                            ),
                        },
                        "failure_reason": reason,
                    }
                )
                self.repository.upsert_round_model(failed_model)
                self.repository.update_round(
                    reconstructing_round.model_copy(
                        update={
                            "status": "model_failed",
                            "failure_reason": reason,
                        }
                    )
                )
                artifacts.write_round_model_result(failed_model)
                failed += 1
                self._log(
                    run,
                    "ERROR",
                    f"{round_item.round_id} 三維模型建立失敗：{reason}",
                )
            self.repository.update_state(
                run.analysis_id,
                updated_at=utc_now_iso(),
                completed_round_count=completed,
                failed_round_count=failed,
            )
            artifacts.write_round_model_index(
                self.repository.list_round_models(run.analysis_id)
            )
            artifacts.write_round_index(
                self.repository.list_rounds(run.analysis_id),
                self.repository.list_views(run.analysis_id),
            )

        if completed == 0:
            self._log(
                run,
                "WARNING",
                "所有 Round 的三維模型皆建立失敗，將保留相機姿態並繼續建立尖端標記。",
            )
        updated = self._require_run(run.analysis_id)
        artifacts.write_run(updated)
        return updated

    def _run_tip_markers(
        self,
        run: AnalysisRun,
        cancel_event: Event,
    ) -> AnalysisRun:
        self._check_cancel(cancel_event)
        artifacts = self._artifacts(run)
        try:
            undistortion_manifest = artifacts.read_undistortion_manifest()
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise AnalysisError(
                f"無法讀取去畸變影像清單：{error}"
            ) from error

        tip_settings = run.parameters.get("tip_analysis")
        if not isinstance(tip_settings, Mapping):
            raise AnalysisError("尖端標記設定格式無效。")
        output_settings = run.parameters.get("outputs")
        if not isinstance(output_settings, Mapping):
            raise AnalysisError("分析輸出設定格式無效。")
        background_settings = run.parameters.get("background")
        if not isinstance(background_settings, Mapping):
            raise AnalysisError("背景處理設定格式無效。")
        export_tip_markers = bool(
            output_settings.get("export_tip_markers", True)
        )
        export_trajectory_csv = bool(
            output_settings.get("export_trajectory_csv", True)
        )
        minimum_confidence = float(
            tip_settings.get("minimum_confidence", 0.7)
        )
        minimum_supporting_views = int(
            tip_settings.get("minimum_supporting_views", 2)
        )
        maximum_reprojection_error_px = float(
            tip_settings.get("maximum_reprojection_error_px", 5.0)
        )

        rounds = order_analysis_rounds(
            self.repository.list_rounds(run.analysis_id)
        )
        views_by_round: dict[str, list] = {}
        for view in self.repository.list_views(run.analysis_id):
            views_by_round.setdefault(view.round_key, []).append(view)
        poses_by_round: dict[str, list[AnalysisCameraPoseResult]] = {}
        for pose in self.repository.list_camera_poses(run.analysis_id):
            poses_by_round.setdefault(pose.round_key, []).append(pose)
        models_by_round = {
            item.round_key: item
            for item in self.repository.list_round_models(run.analysis_id)
        }
        existing_landmarks = {
            item.round_key: item
            for item in self.repository.list_tip_landmarks(run.analysis_id)
        }
        processable_statuses = (
            {
                "model_completed",
                "model_failed",
                "ready_tip_only",
            }
            if run.method_name == "rotating"
            else {"ready_tip_only"}
        )
        candidates = [
            item
            for item in rounds
            if item.status in processable_statuses
        ]
        candidate_keys = {
            item.round_key
            for item in candidates
        }
        previous_by_mode: dict[str, TipLandmark] = {}
        processed_index = 0
        for round_item in rounds:
            if round_item.round_key not in candidate_keys:
                previous = existing_landmarks.get(round_item.round_key)
                if previous is not None and previous.valid:
                    previous_by_mode[round_item.mode_id] = previous
                continue
            processed_index += 1
            self._check_cancel(cancel_event)
            current = self._require_run(run.analysis_id)
            self._write_processing_preview(
                current, views_by_round.get(round_item.round_key, ()),
                message=f"{round_item.round_id} 的尖端分析輸入",
            )
            self._set_state(
                current,
                status="processing",
                stage="detecting_tip_candidates",
                current_frame=processed_index,
                total_frames=len(candidates),
                progress=0.68 + (
                    (processed_index - 1) / max(len(candidates), 1)
                ) * 0.20,
            )
            def update_tip_stage(
                stage: str,
                round_progress: float,
            ) -> None:
                self._check_cancel(cancel_event)
                latest = run
                overall = (
                    (processed_index - 1)
                    + min(max(round_progress, 0.0), 1.0)
                ) / max(len(candidates), 1)
                self._set_state(
                    latest,
                    status="processing",
                    stage=stage,
                    current_frame=processed_index,
                    total_frames=len(candidates),
                    progress=0.68 + overall * 0.20,
                )

            model_result = models_by_round.get(round_item.round_key)
            if model_result is not None and model_result.status != "completed":
                model_result = None
            try:
                result = analyze_round_tip(
                    analysis_id=run.analysis_id,
                    round_item=round_item,
                    views=views_by_round.get(round_item.round_key, ()),
                    poses=poses_by_round.get(round_item.round_key, ()),
                    intrinsics_snapshot=run.intrinsics_snapshot,
                    undistortion_manifest=undistortion_manifest,
                    artifacts_root=artifacts.root,
                    model_result=model_result,
                    previous_landmark=previous_by_mode.get(round_item.mode_id),
                    minimum_confidence=minimum_confidence,
                    minimum_supporting_views=minimum_supporting_views,
                    maximum_reprojection_error_px=(
                        maximum_reprojection_error_px
                    ),
                    use_skeleton_refinement=bool(
                        tip_settings.get("use_skeleton_refinement", True)
                    ),
                    use_temporal_prior=bool(
                        tip_settings.get("use_temporal_prior", True)
                    ),
                    export_all_2d_candidates=bool(
                        tip_settings.get(
                            "export_all_2d_candidates",
                            False,
                        )
                    ),
                    export_scene_point_cloud=bool(
                        output_settings.get(
                            "export_scene_point_cloud",
                            True,
                        )
                    ),
                    export_plant_point_cloud=bool(
                        output_settings.get(
                            "export_plant_point_cloud",
                            True,
                        )
                    ),
                    export_background_point_cloud=bool(
                        background_settings.get(
                            "save_background_model",
                            False,
                        )
                    ),
                    export_skeleton=bool(
                        output_settings.get("export_skeleton", True)
                    ),
                    export_tip_marker=export_tip_markers,
                    save_reprojection_overlays=bool(
                        tip_settings.get("save_reprojection_overlays", True)
                    ),
                    save_diagnostics=bool(
                        output_settings.get("save_diagnostics", True)
                    ),
                    cancel_check=lambda: self._check_cancel(cancel_event),
                    stage_callback=update_tip_stage,
                    view_callback=lambda view: self._write_processing_preview(
                        run, [view], message="目前正在偵測尖端候選的影像",
                    ),
                )
                landmark = result.landmark
                if result.model_result is not None:
                    self.repository.upsert_round_model(result.model_result)
                    artifacts.write_round_model_result(result.model_result)
                    models_by_round[round_item.round_key] = result.model_result
                self.repository.replace_tip_observations(
                    run.analysis_id,
                    round_item.round_key,
                    result.observations,
                )
                if result.warnings:
                    self._log(
                        current,
                        "WARNING",
                        f"{round_item.round_id} 尖端標記警告："
                        + "；".join(result.warnings),
                    )
            except OperationCancelledError:
                raise
            except Exception as error:
                reason = public_error_detail(error)
                landmark = TipLandmark(
                    analysis_id=run.analysis_id,
                    round_key=round_item.round_key,
                    tip_id=f"{round_item.round_key}:tip",
                    record_id=round_item.record_id,
                    mode_id=round_item.mode_id,
                    round_id=round_item.round_id,
                    timestamp=round_item.started_at,
                    confidence=0.0,
                    valid=False,
                    source="invalid",
                    detection_type="invalid",
                    failure_reason=reason,
                )
                self.repository.replace_tip_observations(
                    run.analysis_id,
                    round_item.round_key,
                    (),
                )
                if export_tip_markers:
                    artifacts.write_tip_landmark(
                        landmark,
                        quality={"failure_reason": reason},
                    )
                else:
                    (
                        round_artifact_directory(
                            artifacts.root,
                            round_item.round_key,
                        )
                        / "tip"
                        / "tip_marker.json"
                    ).unlink(missing_ok=True)
                self._log(
                    current,
                    "ERROR",
                    f"{round_item.round_id} 尖端標記失敗：{reason}",
                )

            self.repository.upsert_tip_landmark(landmark)
            self._save_step(run, "triangulating_tip_marker", round_item.round_key, "",
                            {"valid": landmark.valid, "tip_id": landmark.tip_id})
            existing_landmarks[round_item.round_key] = landmark
            if landmark.valid:
                previous_by_mode[round_item.mode_id] = landmark
            model_failed = (
                run.method_name == "rotating"
                and round_item.round_id != "round.00"
                and (
                    models_by_round.get(round_item.round_key) is None
                    or models_by_round[round_item.round_key].status != "completed"
                )
            )
            if landmark.valid and not model_failed:
                round_status = "tip_completed"
                failure_reason = None
            elif landmark.valid:
                round_status = "tip_only"
                stored_model = models_by_round.get(
                    round_item.round_key
                )
                failure_reason = (
                    stored_model.failure_reason
                    if stored_model is not None
                    else round_item.failure_reason
                )
            else:
                round_status = "tip_invalid"
                failure_reason = landmark.failure_reason
                if round_item.failure_reason:
                    failure_reason = (
                        f"{round_item.failure_reason}；{failure_reason}"
                    )
            self.repository.update_round(
                round_item.model_copy(
                    update={
                        "status": round_status,
                        "tip_landmark_id": landmark.tip_id,
                        "failure_reason": failure_reason,
                    }
                )
            )

        resolved_rounds = self.repository.list_rounds(run.analysis_id)
        resolved_landmarks = self.repository.list_tip_landmarks(
            run.analysis_id
        )
        current = self._require_run(run.analysis_id)
        self._set_state(
            current,
            stage="linking_tip_trajectory",
            current_frame=len(candidates),
            total_frames=len(candidates),
            progress=0.89,
        )
        trajectory = link_tip_trajectory(
            resolved_rounds,
            resolved_landmarks,
            blocked_interpolation_round_keys=_model_failed_round_keys(
                resolved_rounds,
                models_by_round,
                run.method_name,
            ),
        )
        self.repository.replace_tip_trajectory(
            run.analysis_id,
            trajectory.points,
        )
        artifacts.write_tip_trajectory(
            trajectory.points,
            trajectory.quality,
            export_csv=export_trajectory_csv,
        )
        current = self._require_run(run.analysis_id)
        self._set_state(
            current,
            stage="calculating_quality_metrics",
            current_frame=len(candidates),
            total_frames=len(candidates),
            progress=0.90,
        )
        artifacts.write_formal_summaries(
            resolved_rounds,
            self.repository.list_round_models(run.analysis_id),
            resolved_landmarks,
            trajectory.quality,
        )
        artifacts.write_round_model_index(
            self.repository.list_round_models(run.analysis_id)
        )
        artifacts.write_round_index(
            resolved_rounds,
            self.repository.list_views(run.analysis_id),
        )
        current = self._require_run(run.analysis_id)
        self._set_state(
            current,
            stage="exporting",
            current_frame=len(candidates),
            total_frames=len(candidates),
            progress=0.91,
        )

        valid_count = sum(item.valid for item in resolved_landmarks)
        successful_round_count = sum(
            item.status == "tip_completed"
            for item in resolved_rounds
        )
        failed_round_count = sum(
            item.status in {
                "failed",
                "model_failed",
                "tip_only",
                "tip_invalid",
            }
            for item in resolved_rounds
        )
        trajectory_status = "completed" if valid_count else "unavailable"
        self.repository.update_state(
            run.analysis_id,
            updated_at=utc_now_iso(),
            completed_round_count=successful_round_count,
            failed_round_count=failed_round_count,
            tip_marker_count=valid_count,
            trajectory_status=trajectory_status,
        )
        reprojection_errors = [
            float(item.mean_reprojection_error_px)
            for item in resolved_landmarks
            if (
                item.valid
                and item.mean_reprojection_error_px is not None
            )
        ]
        self.repository.update_average_reprojection_error(
            run.analysis_id,
            (
                float(np.mean(reprojection_errors))
                if reprojection_errors
                else None
            ),
            utc_now_iso(),
        )
        current = self._require_run(run.analysis_id)
        artifacts.write_run(current)
        if valid_count == 0:
            raise AnalysisError("所有 Round 都無法建立有效的三維尖端標記。")

        wait_for_review = bool(
            tip_settings.get("wait_for_low_confidence_review", True)
        )
        needs_review = bool(
            run.parameters.get("manual_review_required", True)
        ) or (
            wait_for_review
            and any(not item.valid for item in resolved_landmarks)
        )
        if needs_review:
            completed = self._set_state(
                current,
                status="needs_review",
                stage="waiting_for_review",
                current_frame=len(resolved_rounds),
                total_frames=len(resolved_rounds),
                progress=0.92,
                manual_review_completed=False,
                clear_error=True,
            )
            self._log(completed, "INFO", "尖端標記已建立，等待人工確認。")
            return completed

        final_status = (
            "partially_completed"
            if failed_round_count > 0
            else "completed"
        )
        completed = self._set_state(
            current,
            status=final_status,
            stage="completed",
            current_frame=len(resolved_rounds),
            total_frames=len(resolved_rounds),
            progress=1.0,
            manual_review_completed=True,
            clear_error=True,
        )
        self._log(
            completed,
            "INFO",
            f"分析完成，共建立 {valid_count} 個三維尖端標記。",
        )
        return completed

    def _run_job(self, analysis_id: str, cancel_event: Event) -> None:
        run = self._require_run(analysis_id)
        try:
            self._check_cancel(cancel_event)
            if run.status == "validating":
                with StepJournal(self._artifacts(run).root) as journal:
                    journal.save("control", "mode", "", {"mode": "validating"})
                self._validate_round_analysis(run, cancel_event)
                return
            if run.status in {"processing", "reconstructing"}:
                root = self._artifacts(run).root
                signature = step_signature({
                    "round_pipeline_version": 2,
                    "version": 3 if run.method_name == "rotating" else 2, "intrinsics": run.intrinsics_snapshot,
                    **({"training_version": PLANT_TRAINING_VERSION} if run.method_name == "rotating" else {}),
                    "pose": run.parameters.get("pose_strategy"), "aruco": run.aruco_layout_snapshot,
                    "reconstruction": run.parameters.get("reconstruction"), "tips": run.parameters.get("tip_analysis"),
                })
                # Reusing checkpoints still checks every immutable source's identity.
                for source in run.parameters.get("source_manifest", run.parameters.get("input_manifest", [])):
                    self._check_cancel(cancel_event)
                    stat = Path(source["absolute_path"]).stat()
                    if (stat.st_size, stat.st_mtime_ns) != (source["size_bytes"], source["modified_ns"]):
                        raise AnalysisError("分析輸入在建立後已變更，無法恢復既有結果。")
                with StepJournal(root) as journal:
                    journal.save("control", "mode", "", {"mode": "processing"})
                    if journal.get("phase", "preprocessing", signature) is None:
                        run = self._run_round_preprocessing(run, cancel_event)
                        # Bundle adjustment updates the pose exports later. Their
                        # changing timestamps must not invalidate preprocessing.
                        journal.save("phase", "preprocessing", signature, {}, outputs=[
                            root / "undistortion_manifest.json",
                        ])
                    self._check_cancel(cancel_event)
                    if journal.get("phase", "models", signature) is None:
                        run = self._run_round_models(run, cancel_event)
                        journal.save("phase", "models", signature, {})
                    self._check_cancel(cancel_event)
                    self._run_tip_markers(run, cancel_event)
                return
            raise AnalysisError(
                "分析背景工作收到不支援的狀態："
                f"{_status_label(run.status)}"
            )
        except AnalysisReviewRequiredError as error:
            self._request_stereo_review(self._require_run(analysis_id), str(error))
        except OperationCancelledError as error:
            current = self._require_run(analysis_id)
            self._log(current, "WARNING", str(error))
            self._set_state(
                current,
                status="paused" if getattr(cancel_event, "pause_requested", False) else "cancelled",
                last_error=None if getattr(cancel_event, "pause_requested", False) else str(error),
                clear_error=getattr(cancel_event, "pause_requested", False),
            )
        except Exception as error:
            current = self._require_run(analysis_id)
            self._record_failure(
                current,
                error,
                context="分析紀錄失敗",
                report_error=True,
            )
        finally:
            with self._preview_lock:
                self._validation_progress.pop(analysis_id, None)
                self._validation_progress_times.pop(analysis_id, None)
