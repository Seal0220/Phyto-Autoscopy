from __future__ import annotations

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
from typing import Any
from uuid import uuid4

import cv2
import numpy as np
from pydantic import ValidationError

from app.analysis import analysis_method
from app.analysis.analysis_runner import AnalysisJobManager
from app.analysis.artifacts import AnalysisArtifacts
from app.analysis.intrinsics import (
    build_intrinsics_snapshot,
    undistort_analysis_views,
)
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
from app.analysis.reconstruction import ReconstructionBackendRegistry
from app.analysis.reconstruction.reconstruction_worker import (
    run_reconstruction_worker,
)
from app.analysis.review import create_tip_correction
from app.analysis.pose_alignment import align_dataset_camera_poses
from app.analysis.pose_alignment.aruco_world import aruco_layout_snapshot
from app.analysis.run_metadata import (
    next_dated_identifier,
    repository_commit,
    runtime_versions,
    utc_now_iso,
)
from app.analysis.record_validator import (
    CaptureRecordValidation,
    CaptureRecordValidator,
)
from app.analysis.tip.pipeline import analyze_round_tip
from app.analysis.tip.trajectory_linker import link_tip_trajectory
from app.core.config import (
    AppSettings,
    BACKEND_ROOT,
    PoseAlignmentSettings,
)
from app.core.constants import CAPTURE_MODE_NAMES
from app.core.exceptions import (
    AnalysisError,
    OperationCancelledError,
    public_error_detail,
)
from app.models.analysis_models import (
    AnalysisCreateRequest,
    AnalysisRound,
    CameraPoseResult as AnalysisCameraPoseResult,
    AnalysisProgress,
    AnalysisRun,
    AnalysisSourceSummary,
    AnalysisSourceMode,
    AnalysisSourcePreview,
    AnalysisSourcePreviewRequest,
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
})
TERMINAL_STATUSES = frozenset({
    "completed",
    "partially_completed",
    "failed",
    "cancelled",
})
SUPPORTED_ANALYSIS_METHODS = frozenset({
    "round_multiview",
    "top_side_tip_only",
})
STATUS_LABELS = {
    "draft": "草稿",
    "validating": "驗證中",
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
    "cycle_duration_seconds",
    "cycle_interval_seconds",
    "rotation_start_deg",
    "rotation_end_deg",
    "rotation_step_deg",
    "angle_tolerance_deg",
    "stabilization_delay_ms",
    "capture_on_return",
    "return_to_origin",
    "arm_height_mm",
)

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
        self._validator = CaptureRecordValidator()
        self._reconstruction_backends = ReconstructionBackendRegistry()
        self._runner = AnalysisJobManager(
            self._run_job,
            maximum_workers=maximum_workers,
        )

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
            if method == "round_multiview"
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

    def _record_payload(self, record_id: str) -> dict[str, Any]:
        record = self._require_record(record_id)
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

    def _record_modes(
        self,
        record_id: str,
        payload: Mapping[str, Any] | None = None,
    ) -> list[AnalysisSourceMode]:
        record_payload = payload or self._record_payload(record_id)
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
        method: str = "top_side_tip_only",
        mode_ids: Iterable[str] = (),
    ) -> CaptureRecordValidation:
        record = self._require_record(record_id)
        captures = self.capture_repository.list_by_record(record_id)
        return self._validator.validate(
            record,
            captures,
            required_camera_ids=(
                ("top", "side", "rotating")
                if method == "round_multiview"
                else ("top", "side")
            ),
            selected_mode_folders=self._selected_mode_folders(
                record_id,
                mode_ids,
            ),
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

    def _validation_for_run(self, run: AnalysisRun) -> CaptureRecordValidation:
        if run.method_name not in SUPPORTED_ANALYSIS_METHODS:
            raise AnalysisError("找不到分析紀錄。")
        if not run.record_id:
            raise AnalysisError("分析紀錄缺少捕捉紀錄 ID。")
        mode_ids = run.parameters.get("mode_ids", [])
        if not isinstance(mode_ids, list):
            raise AnalysisError("分析擷取模式清單格式無效。")
        return self._validation_for_record(
            run.record_id,
            method=run.method_name,
            mode_ids=mode_ids,
        )

    @staticmethod
    def _manifest(validation: CaptureRecordValidation) -> list[dict[str, Any]]:
        result = []
        for frame in validation.frames:
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
                "sha256": _sha256(frame.file_path),
            })
        return result

    def list_sources(self) -> list[AnalysisSourceSummary]:
        results = []
        for record in self.record_repository.list():
            record_payload = self._record_payload(record.record_id)
            available_modes = self._record_modes(
                record.record_id,
                record_payload,
            )
            capture_configuration = self._capture_configuration(record_payload)
            total_image_count = self._capture_image_count(record_payload)
            try:
                validation = self._validation_for_record(
                    record.record_id,
                )
                full_validation = self._validation_for_record(
                    record.record_id,
                    method="round_multiview",
                )
                reasons = list(validation.not_ready_reasons)
                ready = validation.ready
                top_count = validation.top_frame_count
                side_count = validation.side_frame_count
                rotating_count = full_validation.rotating_frame_count
                pair_count = validation.pairable_frame_count
                total_frame_count = validation.total_frame_count
                camera_resolutions = dict(full_validation.camera_resolutions)
                camera_directories = dict(full_validation.camera_directories)
            except Exception as error:
                logger.exception("Failed to inspect analysis source %s", record.record_id)
                reasons = [f"無法檢查紀錄：{error}"]
                ready = False
                top_count = 0
                side_count = 0
                rotating_count = 0
                pair_count = 0
                total_frame_count = 0
                camera_resolutions = {}
                camera_directories = {}
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
                    pairable_frame_count=pair_count,
                    total_frame_count=total_frame_count,
                    total_image_count=total_image_count,
                    camera_resolutions=camera_resolutions,
                    camera_directories=camera_directories,
                    capture_configuration=capture_configuration,
                    ready=ready,
                    not_ready_reasons=list(dict.fromkeys(reasons)),
                    available_modes=available_modes,
                    analysis_runs=self.repository.list(record.record_id),
                )
            )
        return results

    def preview_sources(
        self,
        request: AnalysisSourcePreviewRequest,
    ) -> AnalysisSourcePreview:
        validation = self._validation_for_record(
            request.record_id,
            method=request.method,
            mode_ids=request.mode_ids,
        )
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
        validation_errors = [
            issue.message
            for issue in validation.issues
        ]
        errors = list(dict.fromkeys([*validation_errors, *grouping.errors]))
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
        layout = aruco_layout_snapshot(self.settings.pose_alignment.aruco_world)
        aruco_readiness = {
            "ready": bool(layout.get("markers")),
            "layout_version": layout.get("layout_version"),
            "dictionary": layout.get("dictionary"),
            "marker_count": len(layout.get("markers", [])),
            "marker_size_mm": layout.get("marker_size_mm"),
            "world_origin": layout.get("world_origin"),
            "unit": layout.get("unit", "mm"),
        }
        backend_readiness = self._reconstruction_backends.check(
            self.settings.reconstruction.backend
        )
        return AnalysisSourcePreview(
            ready=not errors and ready_rounds > 0,
            camera_frame_counts={
                "top": validation.top_frame_count,
                "side": validation.side_frame_count,
                "rotating": validation.rotating_frame_count,
            },
            camera_resolutions=dict(validation.camera_resolutions),
            camera_directories=dict(validation.camera_directories),
            pairable_frame_count=ready_rounds,
            rotating_pairable_frame_count=sum(
                item.status == "ready" and item.rotating_view_count > 0
                for item in grouping.readiness
            ),
            total_frame_count=len(grouping.rounds),
            errors=errors,
            warnings=list(grouping.warnings),
            round_count=len(grouping.rounds),
            ready_round_count=ready_rounds,
            incomplete_round_count=grouping.incomplete_round_count,
            total_view_count=len(grouping.views),
            round_readiness=list(grouping.readiness),
            intrinsics_readiness=intrinsics_readiness,
            aruco_readiness=aruco_readiness,
            backend_readiness=backend_readiness,
        )

    def list_runs(self, record_id: str | None = None) -> list[AnalysisRun]:
        return self.repository.list(record_id)

    def list_reconstruction_backends(self) -> list[dict[str, Any]]:
        return self._reconstruction_backends.list_readiness()

    def _new_analysis_parameters(
        self,
        incoming: Mapping[str, Any],
    ) -> dict[str, Any]:
        defaults = {
            "reconstruction": self.settings.reconstruction.model_dump(mode="json"),
            "pose_strategy": {
                "use_aruco_world_pose": True,
                "use_bundle_adjustment": True,
            },
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
        reconstruction = merged.get("reconstruction")
        if not isinstance(reconstruction, Mapping):
            raise AnalysisError("三維模型設定格式無效。")
        backend = str(reconstruction.get("backend") or "")
        if backend not in self.settings.reconstruction.available_backends:
            raise AnalysisError(f"不支援的三維模型後端：{backend}")
        quality = str(reconstruction.get("quality_preset") or "")
        if quality not in {"preview", "standard", "high"}:
            raise AnalysisError("模型品質只能使用預覽、標準或高品質。")
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
        run = self._require_run(analysis_id)
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
        run = self._require_run(analysis_id)
        view = next(
            (
                item
                for item in self.repository.list_views(analysis_id)
                if item.view_id == view_id
            ),
            None,
        )
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
            item = next(
                (
                    row
                    for row in artifacts.read_undistortion_manifest()
                    if str(row.get("view_id")) == view_id
                ),
                None,
            )
            if item is None:
                raise AnalysisError("此視角尚無去畸變影像。")
            candidate = self.get_artifact_path(
                analysis_id,
                str(item.get("undistorted_path") or ""),
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

    def create(
        self,
        request: AnalysisCreateRequest,
        actor_id: str,
    ) -> AnalysisRun:
        with self._lock:
            analysis_parameters = self._new_analysis_parameters(
                request.parameters
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
            for source in selected_sources.values():
                if source["enabled"]:
                    source["path"] = str(validation.record_path)
            validation_errors = [
                issue.message
                for issue in validation.issues
            ]
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
            pose_settings = self.settings.pose_alignment.model_dump(mode="json")
            top_camera = self.settings.cameras["top"]
            side_camera = self.settings.cameras["side"]
            rotating_camera = self.settings.cameras["rotating"]
            pose_settings["camera_installation_parameters"] = {
                "top": {
                    "height_mm": top_camera.installation_height_mm,
                    "horizontal_distance_to_origin_mm": (
                        top_camera.horizontal_distance_to_origin_mm
                    ),
                    "facing_origin_angle_deg": 90.0,
                },
                "side": {
                    "height_mm": side_camera.installation_height_mm,
                    "horizontal_distance_to_origin_mm": (
                        side_camera.horizontal_distance_to_origin_mm
                    ),
                    "facing_origin_angle_deg": 0.0,
                },
                "rotating": {
                    "arm_height_mm": rotating_camera.arm_height_mm,
                    "horizontal_distance_to_origin_mm": (
                        rotating_camera.horizontal_distance_to_origin_mm
                    ),
                },
            }
            layout_snapshot = aruco_layout_snapshot(
                self.settings.pose_alignment.aruco_world
            )

            try:
                input_manifest = self._manifest(validation)
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
                input_manifest=input_manifest,
            )
            if grouping.errors:
                raise AnalysisError(
                    "捕捉紀錄無法建立分析輪次："
                    + "；".join(grouping.errors)
                )
            reconstruction = analysis_parameters["reconstruction"]
            backend_readiness = self._reconstruction_backends.check(
                reconstruction["backend"]
            )
            if (
                request.method == "round_multiview"
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
                "input_manifest": input_manifest,
                "source_validation": {
                    "ready_at_creation": validation.ready,
                    "not_ready_reasons": validation_errors,
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
                    "warnings": list(grouping.warnings),
                },
                "pose_alignment": pose_settings,
                "coordinate_space": "undistorted",
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
                artifacts.write_input_manifest(input_manifest)
                artifacts.write_round_index(grouping.rounds, grouping.views)
                artifacts.write_reconstruction_environment(backend_readiness)
                artifacts.write_run(run)
                artifacts.write_intrinsics_snapshot(intrinsics_snapshot)
                artifacts.write_aruco_layout_snapshot(layout_snapshot)
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
    ) -> None:
        current = AnalysisService._manifest(validation)
        frozen = run.parameters.get("input_manifest", [])
        if current != frozen:
            raise AnalysisError(
                "捕捉資料輸入在分析紀錄建立後已變更；"
                "請建立新的分析，原始資料未被修改。"
            )

    def _validate_round_analysis(self, run: AnalysisRun) -> AnalysisRun:
        validation = self._validation_for_run(run)
        errors = [
            issue.message
            for issue in validation.issues
        ]
        if errors:
            raise AnalysisError(
                "紀錄不可分析：" + "；".join(dict.fromkeys(errors))
            )
        self._verify_frozen_manifest(run, validation)
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
        try:
            stored_layout = self._artifacts(run).read_aruco_layout_snapshot()
        except (OSError, ValueError) as error:
            raise AnalysisError("分析建立時固化的 ArUco 基準快照遺失。") from error
        if stored_layout != run.aruco_layout_snapshot:
            raise AnalysisError("分析的 ArUco 基準快照與資料庫紀錄不一致。")

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
        backend_readiness = self._reconstruction_backends.probe_runtime(
            backend_name
        )
        if (
            run.method_name == "round_multiview"
            and not backend_readiness["available"]
        ):
            raise AnalysisError("；".join(backend_readiness["errors"]))
        parameters = {
            **run.parameters,
            "backend_readiness_at_validation": backend_readiness,
        }
        self.repository.update_parameters(
            run.analysis_id,
            parameters,
            utc_now_iso(),
        )
        self._artifacts(run).write_parameters(parameters)
        updated = self._set_state(
            run,
            status="ready",
            stage="grouping_rounds",
            current_frame=0,
            total_frames=len(ready_rounds),
            progress=0.0,
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
            self._set_state(
                run,
                status="validating",
                stage="validating",
                current_frame=0,
                progress=0.0,
                clear_error=True,
            )
            try:
                return self._validate_round_analysis(run)
            except Exception as error:
                self._record_failure(run, error, context="驗證失敗")
                if isinstance(error, AnalysisError):
                    raise
                raise AnalysisError(f"分析驗證失敗：{error}") from error

    def _emit_progress(self, run: AnalysisRun) -> None:
        if self.progress_callback is None:
            return
        try:
            self.progress_callback(
                AnalysisProgress(
                    analysis_id=run.analysis_id,
                    status=run.status,
                    stage=run.stage,
                    current_frame=run.current_frame,
                    total_frames=run.total_frames,
                    progress=run.progress,
                    last_error=run.last_error,
                )
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
        updated = self._require_run(run.analysis_id)
        self._artifacts(updated).write_run(updated)
        self._emit_progress(updated)
        return updated

    def _log(
        self,
        run: AnalysisRun,
        level: str,
        message: str,
    ) -> None:
        line = f"{utc_now_iso()} [{level}] {message}\n"
        path = self._artifacts(run).log_path
        with self._lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line)
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
        return AnalysisProgress(
            analysis_id=run.analysis_id,
            status=run.status,
            stage=run.stage,
            current_frame=run.current_frame,
            total_frames=run.total_frames,
            progress=run.progress,
            last_error=run.last_error,
        )

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
                stage="detecting_aruco",
                current_frame=0,
                progress=0.0,
                clear_error=True,
            )
            try:
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
        run = self._require_run(analysis_id)
        if run.status not in {"failed", "cancelled"}:
            raise AnalysisError("只有狀態為「失敗」或「已取消」的分析紀錄可以重試。")
        if self._runner.is_active(analysis_id) and not self._runner.wait_until_idle(
            analysis_id
        ):
            raise AnalysisError("前一個分析背景工作尚未停止，請稍後重試。")
        validated = self.validate(analysis_id)
        resumed = self._set_state(
            validated,
            status="processing",
            stage="detecting_aruco",
            current_frame=0,
            progress=0.0,
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
        self._log(resumed, "INFO", "分析已從既有 Round checkpoint 繼續執行。")
        return resumed

    def resume(self, analysis_id: str) -> AnalysisRun:
        run = self._require_run(analysis_id)
        if run.status == "ready":
            return self.start(analysis_id)
        if run.status in {"needs_review", "reviewing"}:
            return self.reconstruct(analysis_id, manual_review_completed=True)
        if run.status in {"failed", "cancelled"}:
            return self.retry(analysis_id)
        raise AnalysisError(
            f"目前狀態「{_status_label(run.status)}」沒有可繼續的工作。"
        )

    def reconstruct(
        self,
        analysis_id: str,
        manual_review_completed: bool = True,
    ) -> AnalysisRun:
        with self._lock:
            run = self._require_run(analysis_id)
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
            for relative in (
                "summaries",
                "rounds",
                "trajectory",
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
                    run.method_name == "round_multiview"
                    and item.round_id == "round.00"
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

    def recover_interrupted_runs(self) -> None:
        for run in self.repository.list():
            if run.status not in PROCESSING_STATUSES:
                continue
            self._log(run, "WARNING", "偵測到程式非正常中止，保留進度與診斷後標記失敗。")
            self._set_state(
                run,
                status="failed",
                last_error="程式非正常中止；可在確認輸入後重試。",
            )

    def close(self) -> None:
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
                run.method_name == "round_multiview"
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
        trajectory = link_tip_trajectory(rounds, resolved_landmarks)
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
        updated = self._require_run(run.analysis_id)
        artifacts = self._artifacts(updated)
        artifacts.write_tip_corrections(corrections)
        artifacts.write_tip_trajectory(
            trajectory.points,
            trajectory.quality,
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
            raise OperationCancelledError("分析已由使用者取消。")

    def _run_round_preprocessing(
        self,
        run: AnalysisRun,
        cancel_event: Event,
    ) -> AnalysisRun:
        self._check_cancel(cancel_event)
        validation = self._validation_for_run(run)
        self._verify_frozen_manifest(run, validation)
        rounds = self.repository.list_rounds(run.analysis_id)
        views = self.repository.list_views(run.analysis_id)
        if not rounds or not views:
            raise AnalysisError("分析缺少 Round／View 清單。")
        self._set_state(
            run,
            stage="snapshotting_intrinsics",
            current_frame=0,
            total_frames=len(views),
            progress=0.02,
        )

        def update_undistortion(index: int, total: int) -> None:
            self._check_cancel(cancel_event)
            current = self._require_run(run.analysis_id)
            self._set_state(
                current,
                stage="undistorting_images",
                current_frame=index,
                total_frames=total,
                progress=0.02 + (index / max(total, 1)) * 0.16,
            )

        try:
            undistorted = undistort_analysis_views(
                views,
                run.intrinsics_snapshot,
                self._artifacts(run).root,
                cancel_check=lambda: self._check_cancel(cancel_event),
                progress_callback=update_undistortion,
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
        pose_settings = self._pose_settings_for_run(run)
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
            if round_item.status in {"model_completed", "tip_completed"}:
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
            derived_paths: dict[str, Path] = {}
            for view in round_views:
                metadata = undistorted_by_view[view.view_id]
                derived_path = artifacts.root / metadata["undistorted_path"]
                derived_paths[view.view_id] = derived_path
                derived_frames.append({
                    "capture_id": view.capture_id,
                    "camera_id": view.camera_id,
                    "relative_path": metadata["undistorted_path"],
                    "file_path": str(derived_path),
                    "timestamp": view.timestamp,
                    "angle_deg": view.angle_deg,
                    "motor_position_deg": view.motor_position_deg,
                })

            def update_pose_stage(stage: str, progress: float) -> None:
                self._check_cancel(cancel_event)
                current = self._require_run(run.analysis_id)
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
                    "aruco": "aruco",
                    "aruco_refined": "feature_refined",
                    "sfm": "feature_refined",
                    "motor_prior": "motor_prior",
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
                        pose_source=source,
                        valid=pose.resolved,
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

        self.repository.replace_camera_poses(run.analysis_id, stored_poses)
        self.repository.update_views(updated_views)
        pose_payload = [
            item.model_dump(mode="json")
            for item in stored_poses
        ]
        aggregate_pose_quality = {
            "coordinate_space": "undistorted",
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
        artifacts.write_aggregated_pose_results(
            stored_poses,
            pose_estimation_version=pose_estimation_version,
            round_quality=round_quality_payloads,
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
        return {
            "schema_version": "1.0",
            "analysis_id": run.analysis_id,
            "record_id": run.record_id,
            "round_key": round_key,
            "artifact_root": str(artifacts.root),
            "backend": str(reconstruction.get("backend") or ""),
            "parameters": dict(reconstruction),
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

    def _run_round_models(
        self,
        run: AnalysisRun,
        cancel_event: Event,
    ) -> AnalysisRun:
        if run.method_name != "round_multiview":
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
        candidates = [item for item in rounds if item.status == "preprocessed"]
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
            model_id = f"{run.analysis_id}:{round_item.mode_id}:{round_item.round_id}:model"
            running_model = RoundModelResult(
                analysis_id=run.analysis_id,
                round_key=round_item.round_key,
                model_id=model_id,
                backend=backend_name,
                backend_version=str(readiness.get("backend_version") or "unknown"),
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
                current = self._require_run(run.analysis_id)
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
                relative_path = lambda value: (
                    str(Path(value).resolve().relative_to(artifacts.root))
                    if value
                    else None
                )
                completed_model = running_model.model_copy(
                    update={
                        "status": "completed",
                        "source_view_ids": list(
                            worker_result.get("source_view_ids") or []
                        ),
                        "model_path": relative_path(
                            worker_result.get("gaussian_model_path")
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
                            "status": "cancelled",
                            "failure_reason": cancelled_model.failure_reason,
                        }
                    )
                )
                artifacts.write_round_model_result(cancelled_model)
                for pending in candidates[index:]:
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
        minimum_confidence = float(
            tip_settings.get("minimum_confidence", 0.7)
        )
        minimum_supporting_views = int(
            tip_settings.get("minimum_supporting_views", 2)
        )
        maximum_reprojection_error_px = float(
            tip_settings.get("maximum_reprojection_error_px", 5.0)
        )

        rounds = self.repository.list_rounds(run.analysis_id)
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
            {"model_completed", "model_failed"}
            if run.method_name == "round_multiview"
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
                    save_reprojection_overlays=bool(
                        tip_settings.get("save_reprojection_overlays", True)
                    ),
                    cancel_check=lambda: self._check_cancel(cancel_event),
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
                artifacts.write_tip_landmark(
                    landmark,
                    quality={"failure_reason": reason},
                )
                self._log(
                    current,
                    "ERROR",
                    f"{round_item.round_id} 尖端標記失敗：{reason}",
                )

            self.repository.upsert_tip_landmark(landmark)
            existing_landmarks[round_item.round_key] = landmark
            if landmark.valid:
                previous_by_mode[round_item.mode_id] = landmark
            model_failed = (
                run.method_name == "round_multiview"
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
                failure_reason = round_item.failure_reason
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
        trajectory = link_tip_trajectory(
            resolved_rounds,
            resolved_landmarks,
        )
        self.repository.replace_tip_trajectory(
            run.analysis_id,
            trajectory.points,
        )
        artifacts.write_tip_trajectory(
            trajectory.points,
            trajectory.quality,
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
            if run.status == "processing":
                run = self._run_round_preprocessing(run, cancel_event)
                run = self._run_round_models(run, cancel_event)
                self._run_tip_markers(run, cancel_event)
                return
            raise AnalysisError(
                "分析背景工作收到不支援的狀態："
                f"{_status_label(run.status)}"
            )
        except OperationCancelledError as error:
            current = self._require_run(analysis_id)
            self._log(current, "WARNING", str(error))
            self._set_state(
                current,
                status="cancelled",
                last_error=str(error),
            )
        except Exception as error:
            current = self._require_run(analysis_id)
            self._record_failure(
                current,
                error,
                context="分析紀錄失敗",
                report_error=True,
            )
