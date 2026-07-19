from __future__ import annotations

import json
import hashlib
import logging
import math
import shutil
import traceback
import zipfile
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from copy import deepcopy
from pathlib import Path
from threading import Event, RLock
from typing import Any, Literal
from uuid import uuid4

import cv2
import numpy as np
from pydantic import ValidationError

from app.analysis import analysis_method
from app.analysis.analysis_runner import AnalysisJobManager
from app.analysis.artifacts import AnalysisArtifacts
from app.analysis.calibration.resolution_adaptation import (
    StereoResolutionAdaptation,
    adapt_stereo_resolution,
)
from app.analysis.detection.epipolar_constraint import epipolar_line_from_top_point
from app.analysis.detection.side_tip_detection import side_tip_candidates
from app.analysis.detection.top_tip_detection import top_tip_candidates
from app.analysis.detection.rotating_tip import (
    detect_rotating_tip_near_projection,
)
from app.analysis.frame_pairing import pair_capture_frames
from app.analysis.reconstruction.coordinate_system import (
    apply_world_transform,
    validate_rigid_transform,
)
from app.analysis.reconstruction.reprojection import (
    reprojection_errors,
    summarize_reprojection_errors,
)
from app.analysis.reconstruction.triangulation import triangulate_point
from app.analysis.reconstruction.multiview import (
    project_rotating_point,
    robust_multiview_triangulate,
    rotating_projection_matrix,
    undistort_rotating_point,
)
from app.analysis.run_metadata import (
    next_dated_identifier,
    repository_commit,
    runtime_versions,
    utc_now_iso,
)
from app.analysis.segmentation.mog2_background import Mog2BackgroundSegmenter
from app.analysis.record_validator import (
    CaptureRecordValidation,
    CaptureRecordValidator,
)
from app.analysis.source_validator import validate_analysis_sources
from app.analysis.tracking.linear_interpolation import (
    TrackPoint,
    interpolate_missing_track,
)
from app.analysis.tracking.temporal_selection import select_temporal_candidate
from app.core.config import AnalysisSettings, AppSettings, BACKEND_ROOT
from app.core.exceptions import (
    AnalysisError,
    OperationCancelledError,
    public_error_detail,
)
from app.models.analysis_models import (
    AnalysisCreateRequest,
    AnalysisFrameDetail,
    AnalysisFramePair,
    AnalysisProgress,
    AnalysisRun,
    AnalysisSourceSummary,
    AnalysisSourcePreview,
    AnalysisSourcePreviewRequest,
    DetectionSummary,
    DetectionResult,
    ManualCorrection,
    ManualCorrectionRequest,
    Point2D,
    ReprojectionErrorRecord,
    StoredDetection,
    TrajectoryPoint,
)
from app.models.calibration_models import CalibrationProfile
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.calibration_repository import CalibrationRepository
from app.repositories.capture_repository import CaptureRepository
from app.repositories.record_repository import RecordRepository


logger = logging.getLogger(__name__)


PROCESSING_STATUSES = frozenset({
    "validating",
    "processing",
    "reconstructing",
})
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})
PAIRABLE_STATUSES = frozenset({"paired", "manually_aligned"})
DETECTION_CATEGORIES = (
    "Automatic",
    "Estimated",
    "Interpolated",
    "Manual",
    "Missing",
    "Invalid",
)
STATUS_LABELS = {
    "draft": "草稿",
    "validating": "驗證中",
    "ready": "就緒",
    "processing": "處理中",
    "needs_review": "待人工檢查",
    "reviewing": "人工檢查中",
    "reconstructing": "三維重建中",
    "completed": "已完成",
    "failed": "失敗",
    "cancelled": "已取消",
}

_REQUIRED_ANALYSIS_PARAMETERS = (
    "segmentation.history",
    "segmentation.variance_threshold",
    "segmentation.learning_rate",
    "segmentation.initialization_frames",
    "segmentation.minimum_top_contour_area_px",
    "segmentation.minimum_side_contour_area_px",
    "lighting_change.lighting_change_area_px",
    "lighting_change.lighting_change_est_time_frames",
    "top_detection.roi",
    "top_detection.plant_base",
    "top_detection.num_selected_points",
    "side_detection.roi",
    "side_detection.plant_base",
    "side_detection.num_selected_points",
    "side_detection.maximum_epipolar_distance_px",
    "side_detection.minimum_path_connectivity",
    "side_detection.minimum_path_edge_weight",
    "interpolation.maximum_gap_seconds",
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


def _nested_value(payload: dict[str, Any], dotted_path: str) -> Any:
    current: Any = payload
    for key in dotted_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _status_label(status: str) -> str:
    return STATUS_LABELS.get(status, "未知狀態")


def _point(value: Iterable[float]) -> tuple[float, float]:
    values = tuple(float(item) for item in value)
    if len(values) != 2 or not all(math.isfinite(item) for item in values):
        raise AnalysisError("植物基部座標必須包含兩個有效數值。")
    return values[0], values[1]


def _roi(value: Iterable[int]) -> tuple[int, int, int, int]:
    values = tuple(int(item) for item in value)
    if len(values) != 4:
        raise AnalysisError("ROI 必須為 [x, y, width, height]。")
    return values[0], values[1], values[2], values[3]


def _shift_contour(
    contour: np.ndarray,
    origin: tuple[int, int],
) -> list[list[float]]:
    points = contour.reshape(-1, 2).astype(np.float64)
    if not len(points):
        return []
    points[:, 0] += origin[0]
    points[:, 1] += origin[1]
    return points.tolist()


def _skew(vector: np.ndarray) -> np.ndarray:
    x, y, z = np.asarray(vector, dtype=np.float64).reshape(3)
    return np.asarray([[0, -z, y], [z, 0, -x], [-y, x, 0]], dtype=np.float64)


def _fundamental_from_projections(
    top_projection: np.ndarray,
    side_projection: np.ndarray,
) -> np.ndarray:
    """Derive the Fundamental Matrix in the rectified image coordinates."""

    top = np.asarray(top_projection, dtype=np.float64)
    side = np.asarray(side_projection, dtype=np.float64)
    _, _, top_vt = np.linalg.svd(top)
    top_center = top_vt[-1]
    epipole = side @ top_center
    matrix = _skew(epipole) @ side @ np.linalg.pinv(top)
    norm = np.linalg.norm(matrix)
    if norm <= 1e-12 or not np.isfinite(matrix).all():
        raise AnalysisError("無法由雙鏡頭投影矩陣建立校正後 Fundamental Matrix。")
    return matrix / norm


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
        calibration_repository: CalibrationRepository,
        progress_callback: Callable[[AnalysisProgress], None] | None = None,
        error_reporter: Callable[[str], None] | None = None,
        calibration_service: Any | None = None,
        *,
        maximum_workers: int = 1,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.record_repository = record_repository
        self.capture_repository = capture_repository
        self.calibration_repository = calibration_repository
        self.progress_callback = progress_callback
        self.error_reporter = error_reporter
        self.calibration_service = calibration_service
        self._lock = RLock()
        self._validator = CaptureRecordValidator()
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
        if run.status != "completed":
            raise AnalysisError("分析完成後才能讀取重建結果。")
        return run

    def _require_record(self, record_id: str):
        record = self.record_repository.get(record_id)
        if record is None:
            raise AnalysisError(f"找不到紀錄：{record_id}")
        return record

    def _require_calibration(self, calibration_id: str | None) -> CalibrationProfile:
        if not calibration_id:
            raise AnalysisError("分析尚未選擇相機校正設定檔。")
        try:
            profile = (
                self.calibration_service.get_profile(calibration_id)
                if self.calibration_service is not None
                else self.calibration_repository.get(calibration_id)
            )
        except Exception as error:
            raise AnalysisError(
                f"相機校正設定檔無法使用：{error}"
            ) from error
        if profile is None:
            raise AnalysisError(f"找不到相機校正設定檔：{calibration_id}")
        return profile

    def _output_dir(self, run: AnalysisRun) -> Path:
        path = Path(run.output_path).resolve()
        root = self.settings.paths.analysis_dir.resolve()
        if (
            path.name != run.analysis_id
            or path.parent.name != (run.record_id or "custom")
            or path.parent.parent != root
        ):
            raise AnalysisError("分析執行的儲存位置無效。")
        return path

    def _artifacts(self, run: AnalysisRun) -> AnalysisArtifacts:
        return AnalysisArtifacts.create(self._output_dir(run))

    def _validation_for_record(
        self,
        record_id: str,
        *,
        timestamp_tolerance_ms: float,
        manual_frame_offset: int,
        method: str = "top_side",
    ) -> CaptureRecordValidation:
        record = self._require_record(record_id)
        captures = self.capture_repository.list_by_record(record_id)
        return self._validator.validate(
            record,
            captures,
            timestamp_tolerance_ms=timestamp_tolerance_ms,
            manual_frame_offset=manual_frame_offset,
            required_camera_ids=(
                ("top", "side", "rotating")
                if method == "top_side_rotating"
                else ("top", "side")
            ),
        )

    def _validation_for_sources(
        self,
        camera_sources: Mapping[str, object],
        *,
        method: str,
    ) -> CaptureRecordValidation:
        return validate_analysis_sources(
            camera_sources,
            method=method,
            allowed_roots=(self.settings.paths.captures_dir,),
            image_probe=self._validator.image_probe,
        )

    def _validation_for_run(self, run: AnalysisRun) -> CaptureRecordValidation:
        sources = run.parameters.get("camera_sources")
        synchronization = self._analysis_settings(run).synchronization
        if isinstance(sources, Mapping):
            if run.record_id:
                automatic = self._validation_for_record(
                    run.record_id,
                    timestamp_tolerance_ms=(
                        synchronization.timestamp_tolerance_ms
                    ),
                    manual_frame_offset=synchronization.manual_frame_offset,
                    method=run.method_name,
                )
                matches_automatic = all(
                    not isinstance(value, Mapping)
                    or not value.get("enabled")
                    or (
                        automatic.camera_directories.get(camera_id) is not None
                        and Path(str(value.get("path", ""))).expanduser().resolve()
                        == Path(
                            automatic.camera_directories[camera_id]
                        ).resolve()
                    )
                    for camera_id, value in sources.items()
                )
                if matches_automatic:
                    return automatic
            normalized = {
                camera_id: type(
                    "StoredSource",
                    (),
                    {"path": value.get("path", "")},
                )()
                for camera_id, value in sources.items()
                if isinstance(value, Mapping) and value.get("enabled")
            }
            return self._validation_for_sources(
                normalized,
                method=run.method_name,
            )
        if not run.record_id:
            raise AnalysisError("分析缺少影像目錄。")
        return self._validation_for_record(
            run.record_id,
            timestamp_tolerance_ms=synchronization.timestamp_tolerance_ms,
            manual_frame_offset=synchronization.manual_frame_offset,
            method=run.method_name,
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

    @staticmethod
    def _analysis_settings(run: AnalysisRun) -> AnalysisSettings:
        try:
            return AnalysisSettings.model_validate(run.parameters["analysis"])
        except (KeyError, ValidationError) as error:
            raise AnalysisError(f"分析執行設定無效：{error}") from error

    @staticmethod
    def _camera_resolutions(run: AnalysisRun) -> dict[str, tuple[int, int]]:
        source_validation = run.parameters.get("source_validation", {})
        stored = source_validation.get("camera_resolutions", {})
        resolutions: dict[str, tuple[int, int]] = {}

        if isinstance(stored, Mapping):
            camera_ids = (
                ("top", "side", "rotating")
                if run.method_name == "top_side_rotating"
                else ("top", "side")
            )
            for camera_id in camera_ids:
                value = stored.get(camera_id)
                if isinstance(value, (list, tuple)) and len(value) == 2:
                    try:
                        width, height = (int(item) for item in value)
                    except (TypeError, ValueError):
                        continue
                    if width > 0 and height > 0:
                        resolutions[camera_id] = (width, height)

        if len(resolutions) < 2:
            manifest_resolutions: dict[str, set[tuple[int, int]]] = {
                "top": set(),
                "side": set(),
                "rotating": set(),
            }
            for item in run.parameters.get("input_manifest", []):
                if not isinstance(item, Mapping):
                    continue
                camera_id = item.get("camera_id")
                value = item.get("resolution")
                if (
                    camera_id not in manifest_resolutions
                    or not isinstance(value, (list, tuple))
                    or len(value) != 2
                ):
                    continue
                try:
                    width, height = (int(part) for part in value)
                except (TypeError, ValueError):
                    continue
                if width > 0 and height > 0:
                    manifest_resolutions[camera_id].add((width, height))
            for camera_id, values in manifest_resolutions.items():
                if camera_id not in resolutions and len(values) == 1:
                    resolutions[camera_id] = next(iter(values))

        missing = [
            camera_id
            for camera_id in (
                ("top", "side", "rotating")
                if run.method_name == "top_side_rotating"
                else ("top", "side")
            )
            if camera_id not in resolutions
        ]
        if missing:
            raise AnalysisError(
                "分析執行缺少固定的影像解析度：" + ", ".join(missing)
            )
        return resolutions

    @staticmethod
    def _adapted_calibration(
        profile: CalibrationProfile,
        camera_resolutions: Mapping[str, tuple[int, int]],
    ) -> StereoResolutionAdaptation:
        try:
            return adapt_stereo_resolution(
                calibration_resolution=(
                    int(profile.image_width or 0),
                    int(profile.image_height or 0),
                ),
                camera_resolutions=camera_resolutions,
                top_camera_matrix=np.asarray(profile.top_camera_matrix),
                side_camera_matrix=np.asarray(profile.side_camera_matrix),
                top_projection_matrix=np.asarray(profile.top_projection_matrix),
                side_projection_matrix=np.asarray(profile.side_projection_matrix),
                fundamental_matrix=np.asarray(profile.fundamental_matrix),
            )
        except (TypeError, ValueError) as error:
            raise AnalysisError(f"相機校正解析度換算失敗：{error}") from error

    @staticmethod
    def _adapted_rotating_profile(
        profile: CalibrationProfile,
        resolution: tuple[int, int],
    ) -> CalibrationProfile:
        if profile.rotating_camera_matrix is None:
            raise AnalysisError("相機校正缺少 rotating 內參矩陣。")
        stored_size = profile.camera_image_sizes.get("rotating", [])
        calibration_size = (
            (
                int(stored_size[0])
                if len(stored_size) == 2
                else int(profile.image_width or 0)
            ),
            (
                int(stored_size[1])
                if len(stored_size) == 2
                else int(profile.image_height or 0)
            ),
        )
        if min(calibration_size) <= 0 or min(resolution) <= 0:
            raise AnalysisError("rotating 校正或分析解析度無效。")
        scale_x = resolution[0] / calibration_size[0]
        scale_y = resolution[1] / calibration_size[1]
        intrinsic = np.asarray(
            profile.rotating_camera_matrix,
            dtype=np.float64,
        ).copy()
        intrinsic[0] *= scale_x
        intrinsic[1] *= scale_y
        return profile.model_copy(
            update={
                "rotating_camera_matrix": intrinsic.tolist(),
            },
            deep=True,
        )

    @staticmethod
    def _implementation_choices() -> dict[str, Any]:
        return {
            "minimum_path_graph": (
                "CHLOROCULUS implementation choice: topology-preserving skeleton, "
                "configured 4/8-neighbour graph, Dijkstra minimum cost path."
            ),
            "minimum_path_edge_weight": (
                "CHLOROCULUS implementation choice: inverse distance-transform weight; "
                "the paper does not disclose the edge weight."
            ),
            "dynamic_roi": (
                "CHLOROCULUS implementation choice: configured ROI is the hard bound; "
                "when enabled, the next ROI is the selected contour bounding rectangle "
                "expanded by the user-provided margin and clipped to that hard bound."
            ),
            "rectification": (
                "Input images are undistorted and stereo-rectified. Epipolar lines use "
                "a Fundamental Matrix derived from the resolution-adapted rectified "
                "P_top/P_side."
            ),
            "resolution_adaptation": (
                "Calibration pixel-coordinate camera and projection matrices are scaled "
                "independently to each fixed input resolution; the source Calibration "
                "Profile remains immutable."
            ),
            "optional_morphology": (
                "A null morphology kernel explicitly disables that optional cleanup "
                "operation; no undocumented numeric kernel is substituted."
            ),
            "paper_metrics": (
                "Reported paper accuracy and error values are comparison baselines only, "
                "never pass thresholds or guarantees."
            ),
        }

    def list_sources(self) -> list[AnalysisSourceSummary]:
        try:
            profiles = (
                self.calibration_service.list_profiles()
                if self.calibration_service is not None
                else self.calibration_repository.list()
            )
        except Exception:
            logger.exception("Failed to inspect Calibration Profiles")
            profiles = []
        results = []
        synchronization = self.settings.analysis.synchronization
        for record in self.record_repository.list():
            try:
                validation = self._validation_for_record(
                    record.record_id,
                    timestamp_tolerance_ms=synchronization.timestamp_tolerance_ms,
                    manual_frame_offset=synchronization.manual_frame_offset,
                )
                full_validation = self._validation_for_record(
                    record.record_id,
                    timestamp_tolerance_ms=synchronization.timestamp_tolerance_ms,
                    manual_frame_offset=synchronization.manual_frame_offset,
                    method="top_side_rotating",
                )
                available_calibrations = []
                for profile in profiles:
                    try:
                        self._validate_calibration(profile, validation)
                    except AnalysisError:
                        continue
                    available_calibrations.append(profile)
                reasons = list(validation.not_ready_reasons)
                calibration_status = (
                    "valid"
                    if available_calibrations
                    else "missing_or_invalid"
                )
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
                calibration_status = "unknown"
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
                    status=record.status,
                    record_path=record.record_path,
                    top_frame_count=top_count,
                    side_frame_count=side_count,
                    rotating_frame_count=rotating_count,
                    pairable_frame_count=pair_count,
                    total_frame_count=total_frame_count,
                    camera_resolutions=camera_resolutions,
                    camera_directories=camera_directories,
                    calibration_status=calibration_status,
                    ready=ready,
                    not_ready_reasons=list(dict.fromkeys(reasons)),
                    analysis_runs=self.repository.list(record.record_id),
                )
            )
        return results

    def preview_sources(
        self,
        request: AnalysisSourcePreviewRequest,
    ) -> AnalysisSourcePreview:
        camera_sources = {
            camera_id: {
                "enabled": bool(source.enabled),
                "path": source.path.strip(),
            }
            for camera_id, source in request.camera_sources.items()
        }
        validation = None
        if request.record_id:
            synchronization = self.settings.analysis.synchronization
            automatic = self._validation_for_record(
                request.record_id,
                timestamp_tolerance_ms=synchronization.timestamp_tolerance_ms,
                manual_frame_offset=synchronization.manual_frame_offset,
                method=request.method,
            )
            uses_automatic_paths = True
            for camera_id, source in camera_sources.items():
                if not source["enabled"]:
                    continue
                automatic_path = automatic.camera_directories.get(camera_id)
                requested_path = source["path"]
                if requested_path and (
                    automatic_path is None
                    or Path(requested_path).expanduser().resolve()
                    != Path(automatic_path).resolve()
                ):
                    uses_automatic_paths = False
                    break
                source["path"] = automatic_path or str(automatic.record_path)
            if uses_automatic_paths:
                validation = automatic
        if validation is None:
            validation = self._validation_for_sources(
                {
                    camera_id: type(
                        "PreviewSource",
                        (),
                        {"path": source["path"]},
                    )()
                    for camera_id, source in camera_sources.items()
                    if source["enabled"]
                },
                method=request.method,
            )
        return AnalysisSourcePreview(
            ready=validation.ready,
            camera_frame_counts={
                "top": validation.top_frame_count,
                "side": validation.side_frame_count,
                "rotating": validation.rotating_frame_count,
            },
            camera_resolutions=dict(validation.camera_resolutions),
            camera_directories=dict(validation.camera_directories),
            pairable_frame_count=validation.pairable_frame_count,
            rotating_pairable_frame_count=(
                validation.rotating_pairable_frame_count
            ),
            total_frame_count=validation.total_frame_count,
            errors=list(validation.not_ready_reasons),
        )

    def list_runs(self, record_id: str | None = None) -> list[AnalysisRun]:
        return self.repository.list(record_id)

    def get_run(self, analysis_id: str) -> AnalysisRun:
        return self._require_run(analysis_id)

    def create(
        self,
        request: AnalysisCreateRequest,
        actor_id: str,
    ) -> AnalysisRun:
        with self._lock:
            base = self.settings.analysis.model_dump(mode="json")
            merged = _deep_merge(base, request.parameters)
            if request.top_roi is not None:
                merged["top_detection"]["roi"] = [
                    request.top_roi.x,
                    request.top_roi.y,
                    request.top_roi.width,
                    request.top_roi.height,
                ]
            if request.side_roi is not None:
                merged["side_detection"]["roi"] = [
                    request.side_roi.x,
                    request.side_roi.y,
                    request.side_roi.width,
                    request.side_roi.height,
                ]
            if request.manual_frame_offset is not None:
                merged["synchronization"]["manual_frame_offset"] = (
                    request.manual_frame_offset
                )
            try:
                analysis_settings = AnalysisSettings.model_validate(merged)
            except ValidationError as error:
                raise AnalysisError(f"分析設定無效：{error}") from error
            synchronization = analysis_settings.synchronization
            selected_sources = {
                camera_id: {
                    "enabled": bool(source.enabled),
                    "path": source.path.strip(),
                }
                for camera_id, source in request.camera_sources.items()
            }
            if request.record_id:
                automatic = self._validation_for_record(
                    request.record_id,
                    timestamp_tolerance_ms=synchronization.timestamp_tolerance_ms,
                    manual_frame_offset=synchronization.manual_frame_offset,
                    method=request.method,
                )
                for camera_id, source in selected_sources.items():
                    if source["enabled"] and not source["path"]:
                        source["path"] = automatic.camera_directories.get(
                            camera_id,
                            str(automatic.record_path),
                        )
                uses_automatic_paths = all(
                    not source["enabled"]
                    or (
                        automatic.camera_directories.get(camera_id) is not None
                        and Path(source["path"]).expanduser().resolve()
                        == Path(
                            automatic.camera_directories[camera_id]
                        ).resolve()
                    )
                    for camera_id, source in selected_sources.items()
                )
            else:
                automatic = None
                uses_automatic_paths = False
            validation = (
                automatic
                if uses_automatic_paths and automatic is not None
                else self._validation_for_sources(
                    {
                        camera_id: type(
                            "SelectedSource",
                            (),
                            {"path": source["path"]},
                        )()
                        for camera_id, source in selected_sources.items()
                        if source["enabled"]
                    },
                    method=request.method,
                )
            )
            if not validation.ready:
                raise AnalysisError(
                    "影像目錄不可分析："
                    + "；".join(validation.not_ready_reasons)
                )
            profile = self._require_calibration(request.calibration_id)
            self._validate_calibration(
                profile,
                validation,
                method=request.method,
            )
            adaptation = self._adapted_calibration(
                profile,
                validation.camera_resolutions,
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
            parameters = {
                "analysis": analysis_settings.model_dump(mode="json"),
                "frame_range": {
                    "start_frame": request.start_frame,
                    "end_frame": request.end_frame,
                },
                "manual_review_required": request.manual_review_required,
                "camera_sources": selected_sources,
                "input_manifest": input_manifest,
                "source_validation": {
                    "ready_at_creation": validation.ready,
                    "not_ready_reasons": list(validation.not_ready_reasons),
                    "source_frame_count": validation.source_frame_count,
                    "rejected_frame_count": validation.rejected_frame_count,
                    "camera_resolutions": {
                        camera_id: list(resolution)
                        for camera_id, resolution
                        in validation.camera_resolutions.items()
                    },
                },
                "calibration_resolution_adaptation": adaptation.metadata(),
                "runtime_versions": runtime_versions(),
                "implementation_choices": self._implementation_choices(),
            }
            run = AnalysisRun(
                analysis_id=analysis_id,
                record_id=request.record_id,
                calibration_id=request.calibration_id,
                method_name=analysis_method(request.method)["name"],
                method_version=analysis_method(request.method)["version"],
                git_commit=repository_commit(BACKEND_ROOT.parent),
                parameters=parameters,
                created_at=now,
                updated_at=now,
                created_by=actor_id,
                output_path=str(output_dir),
                status="draft",
            )
            artifacts = AnalysisArtifacts.create(output_dir)
            try:
                artifacts.write_parameters(parameters)
                artifacts.write_corrections([])
                artifacts.write_run(run)
                artifacts.write_calibration_reference(
                    profile.model_dump(mode="json")
                )
                self.repository.create(run)
            except Exception:
                shutil.rmtree(output_dir, ignore_errors=True)
                raise
            self._log(run, "INFO", "分析執行已建立；輸入清單與參數已固化。")
            return run

    def _validate_required_parameters(
        self,
        analysis: AnalysisSettings,
        camera_resolutions: Mapping[str, tuple[int, int]],
    ) -> None:
        payload = analysis.model_dump(mode="json")
        missing = [
            dotted_path
            for dotted_path in _REQUIRED_ANALYSIS_PARAMETERS
            if _nested_value(payload, dotted_path) is None
        ]
        if (
            analysis.top_detection.update_roi
            and analysis.top_detection.roi_update_margin_px is None
        ):
            missing.append("top_detection.roi_update_margin_px")
        if (
            analysis.side_detection.update_roi
            and analysis.side_detection.roi_update_margin_px is None
        ):
            missing.append("side_detection.roi_update_margin_px")
        if missing:
            raise AnalysisError(
                "下列資料相依參數尚未決定，不能以虛構值執行："
                + ", ".join(missing)
            )

        for camera_id, label, settings in (
            ("top", "俯視", analysis.top_detection),
            ("side", "側視", analysis.side_detection),
        ):
            resolution = camera_resolutions.get(camera_id)
            if resolution is None:
                raise AnalysisError(f"紀錄缺少{label}影像解析度。")
            width, height = resolution
            x, y, roi_width, roi_height = _roi(settings.roi or ())
            if x + roi_width > width or y + roi_height > height:
                raise AnalysisError(f"{label} ROI 超出分析影像解析度。")
            base_x, base_y = _point(settings.plant_base or ())
            if not (0 <= base_x < width and 0 <= base_y < height):
                raise AnalysisError(f"{label}植物基部超出影像範圍。")

    def _validate_calibration(
        self,
        profile: CalibrationProfile,
        validation: CaptureRecordValidation,
        *,
        method: str = "top_side",
    ) -> None:
        if not profile.valid or profile.status != "valid":
            raise AnalysisError("相機校正設定檔尚未通過驗證或可能已失效。")
        if profile.potentially_invalid_reasons:
            raise AnalysisError("相機校正設定檔可能已失效，請重新校正。")
        if profile.top_camera_identifier != "top" or profile.side_camera_identifier != "side":
            raise AnalysisError("相機校正設定檔的相機角色不是 top/side。")
        required = {
            "俯視 Camera Matrix": profile.top_camera_matrix,
            "側視 Camera Matrix": profile.side_camera_matrix,
            "俯視畸變係數": profile.top_distortion_coefficients,
            "側視畸變係數": profile.side_distortion_coefficients,
            "俯視 Rectification Rotation": profile.top_rectification_rotation,
            "側視 Rectification Rotation": profile.side_rectification_rotation,
            "R": profile.rotation_matrix,
            "t": profile.translation_vector,
            "E": profile.essential_matrix,
            "F": profile.fundamental_matrix,
            "P_top": profile.top_projection_matrix,
            "P_side": profile.side_projection_matrix,
            "T_world_from_stereo": profile.world_transform_matrix,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            raise AnalysisError("相機校正設定檔缺少：" + ", ".join(missing))
        if method == "top_side_rotating" and not profile.supports_rotating:
            raise AnalysisError(
                "頂+側+環繞方法需要包含 rotating 內參與旋臂運動模型的校正。"
            )
        try:
            validate_rigid_transform(np.asarray(profile.world_transform_matrix))
        except ValueError as error:
            raise AnalysisError(str(error)) from error
        self._adapted_calibration(profile, validation.camera_resolutions)

    @staticmethod
    def _verify_frozen_manifest(
        run: AnalysisRun,
        validation: CaptureRecordValidation,
    ) -> None:
        current = AnalysisService._manifest(validation)
        frozen = run.parameters.get("input_manifest", [])
        if current != frozen:
            raise AnalysisError(
                "捕捉資料輸入在分析執行建立後已變更；"
                "請建立新的分析，原始資料未被修改。"
            )

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
                analysis = self._analysis_settings(run)
                synchronization = analysis.synchronization
                validation = self._validation_for_run(run)
                if not validation.ready:
                    raise AnalysisError("紀錄不可分析：" + "；".join(validation.not_ready_reasons))
                self._verify_frozen_manifest(run, validation)
                profile = self._require_calibration(run.calibration_id)
                self._validate_calibration(
                    profile,
                    validation,
                    method=run.method_name,
                )
                self._validate_required_parameters(
                    analysis,
                    validation.camera_resolutions,
                )
                self._set_state(run, stage="pairing_frames", progress=0.02)
                pairs = pair_capture_frames(
                    validation.top_frames,
                    validation.side_frames,
                    validation.rotating_frames,
                    timestamp_tolerance_ms=synchronization.timestamp_tolerance_ms,
                    manual_frame_offset=synchronization.manual_frame_offset,
                )
                frame_range = run.parameters.get("frame_range", {})
                start_frame = frame_range.get("start_frame") or 1
                end_frame = frame_range.get("end_frame") or len(pairs)
                selected_pairs = [
                    pair
                    for pair in pairs
                    if start_frame <= pair.frame_id <= end_frame
                ]
                if not any(pair.pair_status in PAIRABLE_STATUSES for pair in selected_pairs):
                    raise AnalysisError("指定範圍沒有可分析的雙鏡頭影格配對。")
                if not synchronization.keep_unpaired_frames:
                    selected_pairs = [
                        pair
                        for pair in selected_pairs
                        if pair.pair_status in PAIRABLE_STATUSES
                    ]
                self.repository.replace_frame_pairs(analysis_id, selected_pairs)
                self._artifacts(run).write_frame_pairs(selected_pairs)
                updated = self._set_state(
                    run,
                    status="ready",
                    stage="pairing_frames",
                    current_frame=0,
                    total_frames=len(selected_pairs),
                    progress=0.0,
                    clear_error=True,
                )
                self._log(updated, "INFO", f"驗證完成，共 {len(selected_pairs)} 組影格。")
                return updated
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
                raise AnalysisError("只有狀態為「就緒」的分析執行可以開始。")
            if self._runner.is_active(analysis_id):
                raise AnalysisError("分析工作已在執行。")
            self.repository.clear_results(analysis_id)
            run = self._set_state(
                run,
                status="processing",
                stage="initializing_background",
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

    def cancel(self, analysis_id: str) -> AnalysisRun:
        run = self._require_run(analysis_id)
        if self._runner.cancel(analysis_id):
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
            raise AnalysisError("只有狀態為「失敗」或「已取消」的分析執行可以重試。")
        if self._runner.is_active(analysis_id) and not self._runner.wait_until_idle(
            analysis_id
        ):
            raise AnalysisError("前一個分析背景工作尚未停止，請稍後重試。")
        self.validate(analysis_id)
        return self.start(analysis_id)

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
            if run.status not in {"needs_review", "reviewing", "completed"}:
                raise AnalysisError("目前狀態不可執行三維重建。")
            if self._runner.is_active(analysis_id):
                raise AnalysisError("分析工作已在執行。")
            run = self._set_state(
                run,
                status="reconstructing",
                stage="triangulating",
                current_frame=0,
                progress=0.72,
                manual_review_completed=manual_review_completed,
                clear_error=True,
            )
            try:
                if not self._runner.start(analysis_id):
                    raise AnalysisError("分析工作已在執行。")
            except Exception as error:
                self._record_failure(run, error, context="無法啟動重建背景工作")
                if isinstance(error, AnalysisError):
                    raise
                raise AnalysisError(f"無法啟動重建背景工作：{error}") from error
            return run

    def reset(self, analysis_id: str) -> AnalysisRun:
        with self._lock:
            run = self._require_run(analysis_id)
            if (
                self._runner.is_active(analysis_id)
                and not self._runner.wait_until_idle(analysis_id)
            ) or run.status in PROCESSING_STATUSES:
                raise AnalysisError("分析執行中，請先取消並等待背景工作停止。")
            self.repository.clear_results(
                analysis_id,
                include_frame_pairs=True,
                include_corrections=True,
            )
            artifacts = self._artifacts(run)
            for relative in (
                "detections",
                "reconstruction",
                "summaries",
                "overlays",
                "masks",
            ):
                shutil.rmtree(artifacts.root / relative, ignore_errors=True)
            for file_name in (
                "frame_pairs.csv",
                "top_detections.csv",
                "side_detections.csv",
                "manual_corrections.json",
                "resolved_top_positions.csv",
                "resolved_side_positions.csv",
                "trajectory_3d.csv",
                "reprojection_errors.csv",
                "detection_summary.json",
            ):
                (artifacts.root / file_name).unlink(missing_ok=True)
            AnalysisArtifacts.create(artifacts.root).write_corrections([])
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
                raise AnalysisError("分析執行中，不能刪除。")
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

    def list_frame_pairs(self, analysis_id: str) -> list[AnalysisFramePair]:
        self._require_run(analysis_id)
        return self.repository.list_frame_pairs(analysis_id)

    def list_corrections(self, analysis_id: str) -> list[ManualCorrection]:
        self._require_run(analysis_id)
        return self.repository.list_corrections(analysis_id)

    @staticmethod
    def _base_resolved_detection(
        stored: StoredDetection,
    ) -> DetectionResult | None:
        automatic = stored.automatic_detection
        interpolated = stored.interpolated_detection
        if automatic is not None and automatic.valid and automatic.selected_point:
            return automatic.model_copy(deep=True)
        if interpolated is not None and interpolated.valid and interpolated.selected_point:
            return interpolated.model_copy(deep=True)
        if automatic is not None:
            return automatic.model_copy(deep=True)
        if interpolated is not None:
            return interpolated.model_copy(deep=True)
        return None

    def _apply_correction(
        self,
        stored: StoredDetection,
        correction: ManualCorrection | None,
    ) -> StoredDetection:
        resolved = self._base_resolved_detection(stored)
        if correction is not None:
            if resolved is None:
                resolved = DetectionResult(
                    frame_id=stored.frame_id,
                    camera_id=stored.camera_id,
                    detection_type="Missing",
                    valid=False,
                )
            if correction.invalid:
                resolved = resolved.model_copy(
                    update={
                        "selected_point": None,
                        "detection_type": "Invalid",
                        "valid": False,
                        "status_reason": correction.reason or "manual_invalid",
                    },
                    deep=True,
                )
            else:
                resolved = resolved.model_copy(
                    update={
                        "selected_point": Point2D(
                            x_px=float(correction.corrected_x_px),
                            y_px=float(correction.corrected_y_px),
                        ),
                        "detection_type": "Manual",
                        "valid": True,
                        "status_reason": correction.reason,
                    },
                    deep=True,
                )
        return stored.model_copy(
            update={
                "resolved_detection": resolved,
                "updated_at": utc_now_iso(),
            },
            deep=True,
        )

    def _record_correction_refresh_failure(
        self,
        run: AnalysisRun,
        error: BaseException,
    ) -> AnalysisError:
        message = (
            "人工修正已套用，但衍生檔案刷新失敗；"
            "資料庫仍保留一致的修正內容，可重新執行重建："
            f"{public_error_detail(error)}"
        )
        self.repository.update_state(
            run.analysis_id,
            updated_at=utc_now_iso(),
            status="reviewing",
            stage="waiting_for_review",
            manual_review_completed=False,
            last_error=message,
        )
        updated = self._require_run(run.analysis_id)
        try:
            self._artifacts(updated).write_run(updated)
        except Exception:
            logger.exception(
                "Failed to update analysis metadata after correction refresh error"
            )
        try:
            self._log(updated, "ERROR", message)
        except Exception:
            logger.exception(
                "Failed to write analysis log after correction refresh error"
            )
        self._emit_progress(updated)
        if self.error_reporter is not None:
            try:
                self.error_reporter(
                    f"分析 {run.analysis_id} 的人工修正衍生檔案刷新失敗。"
                )
            except Exception:
                logger.exception("Analysis correction error reporter failed")
        return AnalysisError(message)

    def _refresh_correction_artifacts(self, run: AnalysisRun) -> None:
        updated = self._require_run(run.analysis_id)
        try:
            self._write_detection_exports(updated)
            self._artifacts(updated).write_corrections(
                self.repository.list_corrections(run.analysis_id)
            )
            self._artifacts(updated).write_run(updated)
        except Exception as error:
            raise self._record_correction_refresh_failure(
                updated,
                error,
            ) from error
        self._emit_progress(updated)

    def save_correction(
        self,
        analysis_id: str,
        request: ManualCorrectionRequest,
        actor_id: str,
    ) -> ManualCorrection:
        with self._lock:
            run = self._require_run(analysis_id)
            if run.status not in {"needs_review", "reviewing", "completed"}:
                raise AnalysisError("目前狀態不可儲存人工修正。")
            pair = self.repository.get_frame_pair(analysis_id, request.frame_id)
            if pair is None:
                raise AnalysisError(f"找不到影格：{request.frame_id}")
            capture_id = (
                pair.top_capture_id
                if request.camera_id == "top"
                else pair.side_capture_id
            )
            if capture_id is None:
                raise AnalysisError("缺少該相機影格，不能指定人工位置。")
            stored = self.repository.get_detection(
                analysis_id,
                request.frame_id,
                request.camera_id,
            )
            if stored is None:
                raise AnalysisError("尚無可修正的自動偵測資料。")
            if not request.invalid:
                assert request.corrected_x_px is not None
                assert request.corrected_y_px is not None
                width, height = self._camera_resolutions(run)[request.camera_id]
                if (
                    request.corrected_x_px < 0
                    or request.corrected_y_px < 0
                    or request.corrected_x_px >= width
                    or request.corrected_y_px >= height
                ):
                    raise AnalysisError("人工修正位置超出影像範圍。")
            automatic = stored.automatic_detection
            automatic_point = automatic.selected_point if automatic else None
            correction = ManualCorrection(
                correction_id=f"correction_{uuid4().hex}",
                analysis_id=analysis_id,
                frame_id=request.frame_id,
                camera_id=request.camera_id,
                automatic_x_px=automatic_point.x_px if automatic_point else None,
                automatic_y_px=automatic_point.y_px if automatic_point else None,
                corrected_x_px=request.corrected_x_px,
                corrected_y_px=request.corrected_y_px,
                operator_id=actor_id,
                created_at=utc_now_iso(),
                reason=request.reason,
                invalid=request.invalid,
            )
            correction_history = [
                *self.repository.list_corrections(analysis_id),
                correction,
            ]
            updates = self._interpolated_camera_detections(
                run,
                request.camera_id,
                correction_history,
            )
            self.repository.insert_correction_with_detections(
                correction,
                updates,
                updated_at=utc_now_iso(),
            )
            self._refresh_correction_artifacts(run)
            return correction

    def delete_correction(
        self,
        analysis_id: str,
        correction_id: str,
    ) -> None:
        with self._lock:
            run = self._require_run(analysis_id)
            if run.status not in {"needs_review", "reviewing", "completed"}:
                raise AnalysisError("目前狀態不可刪除人工修正。")
            correction = self.repository.get_correction(analysis_id, correction_id)
            if correction is None:
                raise AnalysisError(f"找不到人工修正：{correction_id}")
            correction_history = [
                item
                for item in self.repository.list_corrections(analysis_id)
                if item.correction_id != correction_id
            ]
            updates = self._interpolated_camera_detections(
                run,
                correction.camera_id,
                correction_history,
            )
            if not self.repository.delete_correction_with_detections(
                analysis_id,
                correction_id,
                updates,
                updated_at=utc_now_iso(),
            ):
                raise AnalysisError(f"找不到人工修正：{correction_id}")
            self._refresh_correction_artifacts(run)

    def _manifest_item(
        self,
        run: AnalysisRun,
        input_id: int,
    ) -> dict[str, Any]:
        for item in run.parameters.get("input_manifest", []):
            stored_input_id = item.get("input_id", item.get("capture_id", -1))
            if int(stored_input_id) == input_id:
                return item
        raise AnalysisError(f"輸入清單找不到影像輸入 ID：{input_id}")

    def get_frame_image_path(
        self,
        analysis_id: str,
        frame_id: int,
        camera_id: Literal["top", "side", "rotating"],
    ) -> Path:
        if camera_id not in {"top", "side", "rotating"}:
            raise AnalysisError("影格相機角色只能是 top、side 或 rotating。")
        run = self._require_run(analysis_id)
        pair = self.repository.get_frame_pair(analysis_id, frame_id)
        if pair is None:
            raise AnalysisError(f"找不到影格：{frame_id}")
        input_ids = {
            "top": pair.top_capture_id,
            "side": pair.side_capture_id,
            "rotating": pair.rotating_capture_id,
        }
        input_id = input_ids[camera_id]
        if input_id is None:
            raise AnalysisError("該相機影格不存在。")
        item = self._manifest_item(run, input_id)
        absolute_path = item.get("absolute_path")
        if absolute_path:
            path = Path(str(absolute_path)).resolve()
        elif run.record_id:
            record = self._require_record(run.record_id)
            path = (
                Path(record.record_path).resolve()
                / str(item["relative_path"])
            ).resolve()
        else:
            raise AnalysisError("輸入清單缺少影像的絕對路徑。")
        root = self.settings.paths.captures_dir.resolve()
        try:
            path.relative_to(root)
        except ValueError as error:
            raise AnalysisError("輸入影像路徑超出允許的擷取目錄。") from error
        if not path.is_file():
            raise AnalysisError("輸入影像已不存在。")
        stat = path.stat()
        if stat.st_size != item["size_bytes"] or stat.st_mtime_ns != item["modified_ns"]:
            raise AnalysisError("輸入影像在分析執行建立後已變更。")
        if _sha256(path) != item.get("sha256"):
            raise AnalysisError("輸入影像內容與固化的 SHA-256 不一致。")
        return path

    def get_frame_detail(
        self,
        analysis_id: str,
        frame_id: int,
    ) -> AnalysisFrameDetail:
        pair = self.repository.get_frame_pair(analysis_id, frame_id)
        if pair is None:
            raise AnalysisError(f"找不到影格：{frame_id}")
        top_url = (
            f"/api/analysis/{analysis_id}/frames/{frame_id}/images/top"
            if pair.top_capture_id is not None
            else None
        )
        side_url = (
            f"/api/analysis/{analysis_id}/frames/{frame_id}/images/side"
            if pair.side_capture_id is not None
            else None
        )
        rotating_url = (
            f"/api/analysis/{analysis_id}/frames/{frame_id}/images/rotating"
            if pair.rotating_capture_id is not None
            else None
        )
        return AnalysisFrameDetail(
            pair=pair,
            top_image_url=top_url,
            side_image_url=side_url,
            rotating_image_url=rotating_url,
            top_detection=self.repository.get_detection(
                analysis_id,
                frame_id,
                "top",
            ),
            side_detection=self.repository.get_detection(
                analysis_id,
                frame_id,
                "side",
            ),
            rotating_detection=self.repository.get_detection(
                analysis_id,
                frame_id,
                "rotating",
            ),
            corrections=[
                correction
                for correction in self.repository.list_corrections(analysis_id)
                if correction.frame_id == frame_id
            ],
        )

    def list_frames(self, analysis_id: str) -> list[AnalysisFrameDetail]:
        self._require_run(analysis_id)
        pairs = self.repository.list_frame_pairs(analysis_id)
        detections = {
            (stored.frame_id, stored.camera_id): stored
            for stored in self.repository.list_detections(analysis_id)
        }
        corrections_by_frame: dict[int, list[ManualCorrection]] = {}
        for correction in self.repository.list_corrections(analysis_id):
            corrections_by_frame.setdefault(correction.frame_id, []).append(
                correction
            )
        return [
            AnalysisFrameDetail(
                pair=pair,
                top_image_url=(
                    f"/api/analysis/{analysis_id}/frames/"
                    f"{pair.frame_id}/images/top"
                    if pair.top_capture_id is not None
                    else None
                ),
                side_image_url=(
                    f"/api/analysis/{analysis_id}/frames/"
                    f"{pair.frame_id}/images/side"
                    if pair.side_capture_id is not None
                    else None
                ),
                rotating_image_url=(
                    f"/api/analysis/{analysis_id}/frames/"
                    f"{pair.frame_id}/images/rotating"
                    if pair.rotating_capture_id is not None
                    else None
                ),
                top_detection=detections.get((pair.frame_id, "top")),
                side_detection=detections.get((pair.frame_id, "side")),
                rotating_detection=detections.get((pair.frame_id, "rotating")),
                corrections=corrections_by_frame.get(pair.frame_id, []),
            )
            for pair in pairs
        ]

    @staticmethod
    def _csv_bool(value: object) -> bool:
        return str(value).strip().lower() in {"1", "true", "yes"}

    @staticmethod
    def _csv_optional_float(value: object) -> float | None:
        text = str(value or "").strip()
        return float(text) if text else None

    def get_trajectory(self, analysis_id: str) -> list[TrajectoryPoint]:
        rows = self._artifacts(self._require_completed_run(analysis_id)).read_csv(
            "trajectory_3d.csv"
        )
        try:
            return [
                TrajectoryPoint(
                    frame_id=int(row["frame_id"]),
                    cycle_id=(
                        int(row["cycle_id"])
                        if row.get("cycle_id", "").strip()
                        else None
                    ),
                    timestamp=row.get("timestamp") or None,
                    top_x_px=float(row["top_x_px"]),
                    top_y_px=float(row["top_y_px"]),
                    side_x_px=float(row["side_x_px"]),
                    side_y_px=float(row["side_y_px"]),
                    rotating_x_px=self._csv_optional_float(
                        row.get("rotating_x_px")
                    ),
                    rotating_y_px=self._csv_optional_float(
                        row.get("rotating_y_px")
                    ),
                    rotating_angle_deg=self._csv_optional_float(
                        row.get("rotating_angle_deg")
                    ),
                    x_mm=float(row["x_mm"]),
                    y_mm=float(row["y_mm"]),
                    z_mm=float(row["z_mm"]),
                    refined_x_mm=self._csv_optional_float(
                        row.get("refined_x_mm")
                    ),
                    refined_y_mm=self._csv_optional_float(
                        row.get("refined_y_mm")
                    ),
                    refined_z_mm=self._csv_optional_float(
                        row.get("refined_z_mm")
                    ),
                    top_detection_type=row["top_detection_type"],
                    side_detection_type=row["side_detection_type"],
                    top_reprojection_error_px=float(
                        row["top_reprojection_error_px"]
                    ),
                    side_reprojection_error_px=float(
                        row["side_reprojection_error_px"]
                    ),
                    rotating_reprojection_error_px=self._csv_optional_float(
                        row.get("rotating_reprojection_error_px")
                    ),
                    rotating_used=self._csv_bool(row.get("rotating_used")),
                    valid=self._csv_bool(row["valid"]),
                )
                for row in rows
            ]
        except (KeyError, TypeError, ValueError) as error:
            raise AnalysisError(f"三維軌跡資料格式無效：{error}") from error

    def get_reprojection_errors(
        self,
        analysis_id: str,
    ) -> list[ReprojectionErrorRecord]:
        rows = self._artifacts(self._require_completed_run(analysis_id)).read_csv(
            "reprojection_errors.csv"
        )
        try:
            return [
                ReprojectionErrorRecord(
                    frame_id=int(row["frame_id"]),
                    top_error_px=float(row["top_error_px"]),
                    side_error_px=float(row["side_error_px"]),
                    rotating_error_px=self._csv_optional_float(
                        row.get("rotating_error_px")
                    ),
                    overall_error_px=float(row["overall_error_px"]),
                    refined_overall_error_px=self._csv_optional_float(
                        row.get("refined_overall_error_px")
                    ),
                    high_error=self._csv_bool(row["high_error"]),
                )
                for row in rows
            ]
        except (KeyError, TypeError, ValueError) as error:
            raise AnalysisError(f"重投影誤差資料格式無效：{error}") from error

    def get_detection_summary(self, analysis_id: str) -> DetectionSummary:
        path = (
            self._artifacts(self._require_completed_run(analysis_id)).root
            / "detection_summary.json"
        )
        if not path.is_file():
            raise AnalysisError("偵測摘要尚未產生。")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise AnalysisError(f"偵測摘要無法讀取：{error}") from error
        if not isinstance(payload, dict):
            raise AnalysisError("偵測摘要格式無效。")
        try:
            return DetectionSummary.model_validate(payload)
        except ValidationError as error:
            raise AnalysisError(f"偵測摘要格式無效：{error}") from error

    def export(self, analysis_id: str) -> Path:
        run = self._require_run(analysis_id)
        if run.status != "completed":
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

    def _run_job(self, analysis_id: str, cancel_event: Event) -> None:
        run = self._require_run(analysis_id)
        try:
            self._check_cancel(cancel_event)
            if run.status == "processing":
                self._run_detection(run, cancel_event)
                run = self._require_run(analysis_id)
                if bool(run.parameters.get("manual_review_required", True)):
                    self._set_state(
                        run,
                        status="needs_review",
                        stage="waiting_for_review",
                        current_frame=run.total_frames,
                        progress=0.70,
                        manual_review_completed=False,
                        clear_error=True,
                    )
                    self._log(run, "INFO", "自動偵測完成，等待人工檢查。")
                    return
                run = self._set_state(
                    run,
                    status="reconstructing",
                    stage="triangulating",
                    current_frame=0,
                    progress=0.72,
                    manual_review_completed=False,
                    clear_error=True,
                )
                self._run_reconstruction(run, cancel_event)
                return
            if run.status == "reconstructing":
                self._run_reconstruction(run, cancel_event)
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
                context="分析執行失敗",
                report_error=True,
            )

    @staticmethod
    def _decode_image(path: Path) -> np.ndarray:
        try:
            encoded = np.fromfile(path, dtype=np.uint8)
            image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        except (OSError, ValueError) as error:
            raise AnalysisError(f"影像無法讀取：{path.name}（{error}）") from error
        if image is None or image.size == 0:
            raise AnalysisError(f"影像無法解碼：{path.name}")
        return image

    @staticmethod
    def _write_image_atomic(path: Path, image: np.ndarray, extension: str) -> None:
        success, encoded = cv2.imencode(extension, image)
        if not success:
            raise AnalysisError(f"分析影像輸出編碼失敗：{path.name}")
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_bytes(encoded.tobytes())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _rectification_maps(
        profile: CalibrationProfile,
        adaptation: StereoResolutionAdaptation,
    ) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        values = {
            "top": (
                adaptation.top.camera_matrix,
                profile.top_distortion_coefficients,
                profile.top_rectification_rotation,
                adaptation.top.projection_matrix,
                adaptation.top.resolution,
            ),
            "side": (
                adaptation.side.camera_matrix,
                profile.side_distortion_coefficients,
                profile.side_rectification_rotation,
                adaptation.side.projection_matrix,
                adaptation.side.resolution,
            ),
        }
        maps = {}
        for camera_id, values_for_camera in values.items():
            camera, distortion, rotation, projection, size = values_for_camera
            arguments = (
                np.asarray(camera, dtype=np.float64),
                np.asarray(distortion, dtype=np.float64),
                np.asarray(rotation, dtype=np.float64),
                np.asarray(projection, dtype=np.float64)[:, :3],
                size,
                cv2.CV_32FC1,
            )
            if profile.camera_projection_models.get(camera_id) == "fisheye":
                map_x, map_y = cv2.fisheye.initUndistortRectifyMap(*arguments)
            else:
                map_x, map_y = cv2.initUndistortRectifyMap(*arguments)
            maps[camera_id] = map_x, map_y
        return maps

    def _rectified_frame(
        self,
        run: AnalysisRun,
        pair: AnalysisFramePair,
        camera_id: Literal["top", "side"],
        maps: dict[str, tuple[np.ndarray, np.ndarray]],
    ) -> np.ndarray:
        image = self._decode_image(
            self.get_frame_image_path(
                run.analysis_id,
                pair.frame_id,
                camera_id,
            )
        )
        map_x, map_y = maps[camera_id]
        return cv2.remap(
            image,
            map_x,
            map_y,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
        )

    @staticmethod
    def _make_segmenter(
        analysis: AnalysisSettings,
        camera_id: Literal["top", "side"],
    ) -> Mog2BackgroundSegmenter:
        segmentation = analysis.segmentation
        minimum_area = (
            segmentation.minimum_top_contour_area_px
            if camera_id == "top"
            else segmentation.minimum_side_contour_area_px
        )
        assert segmentation.history is not None
        assert segmentation.variance_threshold is not None
        assert segmentation.initialization_frames is not None
        assert minimum_area is not None
        assert analysis.lighting_change.lighting_change_area_px is not None
        assert analysis.lighting_change.lighting_change_est_time_frames is not None
        return Mog2BackgroundSegmenter(
            history=segmentation.history,
            variance_threshold=segmentation.variance_threshold,
            detect_shadows=segmentation.detect_shadows,
            initialization_frames=segmentation.initialization_frames,
            opening_kernel_size=segmentation.opening_kernel_size,
            closing_kernel_size=segmentation.closing_kernel_size,
            erosion_kernel_size=segmentation.erosion_kernel_size,
            minimum_contour_area_px=minimum_area,
            lighting_change_area_px=(
                analysis.lighting_change.lighting_change_area_px
            ),
            lighting_change_est_time_frames=(
                analysis.lighting_change.lighting_change_est_time_frames
            ),
        )

    @staticmethod
    def _updated_roi(
        hard_bound: tuple[int, int, int, int],
        contour: list[list[float]],
        margin: int | None,
    ) -> tuple[int, int, int, int]:
        if not contour or margin is None:
            return hard_bound
        bound_x, bound_y, bound_width, bound_height = hard_bound
        bound_right = bound_x + bound_width
        bound_bottom = bound_y + bound_height
        x, y, width, height = cv2.boundingRect(
            np.rint(np.asarray(contour)).astype(np.int32)
        )
        left = max(bound_x, x - margin)
        top = max(bound_y, y - margin)
        right = min(bound_right, x + width + margin)
        bottom = min(bound_bottom, y + height + margin)
        if right <= left or bottom <= top:
            return hard_bound
        return left, top, right - left, bottom - top

    @staticmethod
    def _status_detection(
        frame_id: int,
        camera_id: Literal["top", "side"],
        timestamp: str | None,
        status: str,
    ) -> DetectionResult:
        detection_type = (
            status
            if status in {"background_initialization", "lighting_transition"}
            else "Missing"
        )
        return DetectionResult(
            frame_id=frame_id,
            camera_id=camera_id,
            timestamp=timestamp,
            detection_type=detection_type,
            valid=False,
            status_reason=status,
        )

    @staticmethod
    def _mask_in_frame(
        mask: np.ndarray,
        frame_shape: tuple[int, int],
        origin: tuple[int, int],
    ) -> np.ndarray:
        height, width = frame_shape
        full = np.zeros((height, width), dtype=np.uint8)
        x, y = origin
        mask_height, mask_width = mask.shape[:2]
        full[y:y + mask_height, x:x + mask_width] = mask
        return full

    @staticmethod
    def _render_overlay(
        image: np.ndarray,
        detection: DetectionResult,
    ) -> np.ndarray:
        overlay = image.copy()
        if detection.contour:
            contour = np.rint(np.asarray(detection.contour)).astype(np.int32)
            cv2.polylines(overlay, [contour], True, (80, 220, 160), 1)
        if detection.epipolar_line:
            a, b, c = detection.epipolar_line
            height, width = overlay.shape[:2]
            if abs(b) > 1e-12:
                y0 = int(round(-c / b))
                y1 = int(round(-(a * (width - 1) + c) / b))
                cv2.line(overlay, (0, y0), (width - 1, y1), (40, 220, 250), 1)
            elif abs(a) > 1e-12:
                x = int(round(-c / a))
                cv2.line(overlay, (x, 0), (x, height - 1), (40, 220, 250), 1)
        if detection.minimum_path:
            path = np.rint(
                np.asarray([[point.x_px, point.y_px] for point in detection.minimum_path])
            ).astype(np.int32)
            if len(path) > 1:
                cv2.polylines(overlay, [path], False, (255, 160, 40), 2)
        for point in detection.candidate_points:
            cv2.circle(
                overlay,
                (int(round(point.x_px)), int(round(point.y_px))),
                4,
                (30, 80, 255),
                1,
            )
        if detection.selected_point:
            cv2.circle(
                overlay,
                (
                    int(round(detection.selected_point.x_px)),
                    int(round(detection.selected_point.y_px)),
                ),
                5,
                (70, 255, 120),
                2,
            )
        return overlay

    def _store_frame_artifacts(
        self,
        run: AnalysisRun,
        camera_id: Literal["top", "side"],
        frame_id: int,
        image: np.ndarray,
        mask: np.ndarray,
        detection: DetectionResult,
    ) -> None:
        root = self._artifacts(run).root
        self._write_image_atomic(
            root / "masks" / camera_id / f"{frame_id:06d}.png",
            mask,
            ".png",
        )
        self._write_image_atomic(
            root / "overlays" / camera_id / f"{frame_id:06d}.jpg",
            self._render_overlay(image, detection),
            ".jpg",
        )

    def _store_detection(
        self,
        run: AnalysisRun,
        detection: DetectionResult,
    ) -> StoredDetection:
        stored = StoredDetection(
            analysis_id=run.analysis_id,
            frame_id=detection.frame_id,
            camera_id=detection.camera_id,
            automatic_detection=detection,
            resolved_detection=detection.model_copy(deep=True),
            updated_at=utc_now_iso(),
        )
        self.repository.upsert_detection(stored)
        return stored

    def _run_detection(self, run: AnalysisRun, cancel_event: Event) -> None:
        analysis = self._analysis_settings(run)
        profile = self._require_calibration(run.calibration_id)
        pairs = self.repository.list_frame_pairs(run.analysis_id)
        if not pairs:
            raise AnalysisError("分析執行沒有已驗證的影格配對。")
        camera_resolutions = self._camera_resolutions(run)
        adaptation = self._adapted_calibration(
            profile,
            camera_resolutions,
        )
        maps = self._rectification_maps(profile, adaptation)
        rectified_fundamental = _fundamental_from_projections(
            adaptation.top.projection_matrix,
            adaptation.side.projection_matrix,
        )
        top_segmenter = self._make_segmenter(analysis, "top")
        side_segmenter = self._make_segmenter(analysis, "side")
        top_settings = analysis.top_detection
        side_settings = analysis.side_detection
        top_hard_roi = _roi(top_settings.roi or ())
        side_hard_roi = _roi(side_settings.roi or ())
        top_roi = top_hard_roi
        side_roi = side_hard_roi
        top_previous: tuple[float, float] | None = None
        side_previous: tuple[float, float] | None = None
        learning_rate = analysis.segmentation.learning_rate
        assert learning_rate is not None

        self._log(run, "INFO", "開始 MOG2、俯視與側視經典尖端偵測。")
        for index, pair in enumerate(pairs, start=1):
            self._check_cancel(cancel_event)
            if pair.pair_status not in PAIRABLE_STATUSES:
                for camera_id, timestamp in (
                    ("top", pair.top_timestamp),
                    ("side", pair.side_timestamp),
                ):
                    self._store_detection(
                        run,
                        self._status_detection(
                            pair.frame_id,
                            camera_id,
                            timestamp,
                            "unpaired",
                        ),
                    )
                self._set_state(
                    run,
                    stage="detecting_side_tip",
                    current_frame=pair.frame_id,
                    progress=0.05 + 0.55 * index / len(pairs),
                )
                continue

            top_image = self._rectified_frame(run, pair, "top", maps)
            side_image = self._rectified_frame(run, pair, "side", maps)
            top_segment = top_segmenter.process(
                top_image,
                roi=top_roi,
                learning_rate=learning_rate,
            )
            side_segment = side_segmenter.process(
                side_image,
                roi=side_roi,
                learning_rate=learning_rate,
            )

            if top_segment.status != "ready":
                top_detection = self._status_detection(
                    pair.frame_id,
                    "top",
                    pair.top_timestamp,
                    top_segment.status,
                )
            else:
                candidates = top_tip_candidates(
                    top_segment.contours,
                    plant_base=_point(top_settings.plant_base or ()),
                    num_selected_points=int(top_settings.num_selected_points or 0),
                    roi_origin=top_segment.roi_origin,
                )
                selected = select_temporal_candidate(
                    candidates.candidate_points,
                    top_previous,
                )
                selected_point = (
                    Point2D(x_px=selected.selected[0], y_px=selected.selected[1])
                    if selected.selected
                    else None
                )
                selected_contour = next(
                    (
                        contour
                        for point, contour in zip(
                            candidates.candidate_points,
                            candidates.selected_contours,
                        )
                        if selected.selected is not None
                        and np.allclose(point, selected.selected)
                    ),
                    None,
                )
                global_contour = (
                    _shift_contour(
                        selected_contour,
                        top_segment.roi_origin,
                    )
                    if selected_contour is not None
                    else []
                )
                top_detection = DetectionResult(
                    frame_id=pair.frame_id,
                    camera_id="top",
                    timestamp=pair.top_timestamp,
                    candidate_points=[
                        Point2D(x_px=point[0], y_px=point[1])
                        for point in candidates.candidate_points
                    ],
                    selected_point=selected_point,
                    detection_type=selected.detection_type,
                    valid=selected_point is not None,
                    contour=global_contour,
                    status_reason=(
                        "manual_initialization_required"
                        if selected.requires_manual_initialization
                        else None
                    ),
                )
                if selected.selected:
                    top_previous = selected.selected
                if top_settings.update_roi and global_contour:
                    top_roi = self._updated_roi(
                        top_hard_roi,
                        global_contour,
                        top_settings.roi_update_margin_px,
                    )
            top_mask = self._mask_in_frame(
                top_segment.mask,
                top_image.shape[:2],
                top_segment.roi_origin,
            )
            self._store_detection(run, top_detection)
            self._store_frame_artifacts(
                run,
                "top",
                pair.frame_id,
                top_image,
                top_mask,
                top_detection,
            )
            self._set_state(
                run,
                stage="detecting_top_tip",
                current_frame=pair.frame_id,
                progress=0.05 + 0.275 * index / len(pairs),
            )
            self._check_cancel(cancel_event)

            epipolar_line: tuple[float, float, float] | None = None
            minimum_paths = []
            selected_contours: list[np.ndarray] = []
            if side_segment.status != "ready":
                side_detection = self._status_detection(
                    pair.frame_id,
                    "side",
                    pair.side_timestamp,
                    side_segment.status,
                )
            elif not top_detection.valid or top_detection.selected_point is None:
                side_detection = self._status_detection(
                    pair.frame_id,
                    "side",
                    pair.side_timestamp,
                    "top_tip_missing",
                )
            else:
                epipolar_line = epipolar_line_from_top_point(
                    rectified_fundamental,
                    (
                        top_detection.selected_point.x_px,
                        top_detection.selected_point.y_px,
                    ),
                )
                assert side_settings.maximum_epipolar_distance_px is not None
                assert side_settings.minimum_path_connectivity is not None
                candidates = side_tip_candidates(
                    side_segment.contours,
                    image_shape=side_segment.mask.shape[:2],
                    plant_base=_point(side_settings.plant_base or ()),
                    epipolar_line=epipolar_line,
                    maximum_epipolar_distance_px=(
                        side_settings.maximum_epipolar_distance_px
                    ),
                    num_selected_points=int(side_settings.num_selected_points or 0),
                    connectivity=side_settings.minimum_path_connectivity,
                    roi_origin=side_segment.roi_origin,
                )
                minimum_paths = candidates.minimum_paths
                selected_contours = candidates.selected_contours
                selected = select_temporal_candidate(
                    candidates.candidate_points,
                    side_previous,
                )
                selected_point = (
                    Point2D(x_px=selected.selected[0], y_px=selected.selected[1])
                    if selected.selected
                    else None
                )
                selected_path = next(
                    (
                        path
                        for path in minimum_paths
                        if selected.selected is not None
                        and np.allclose(path.candidate_point, selected.selected)
                    ),
                    None,
                )
                selected_contour = next(
                    (
                        contour
                        for contour in selected_contours
                        if selected.selected is not None
                        and cv2.pointPolygonTest(
                            contour,
                            (
                                selected.selected[0] - side_segment.roi_origin[0],
                                selected.selected[1] - side_segment.roi_origin[1],
                            ),
                            False,
                        )
                        >= 0
                    ),
                    None,
                )
                global_contour = (
                    _shift_contour(
                        selected_contour,
                        side_segment.roi_origin,
                    )
                    if selected_contour is not None
                    else []
                )
                side_detection = DetectionResult(
                    frame_id=pair.frame_id,
                    camera_id="side",
                    timestamp=pair.side_timestamp,
                    candidate_points=[
                        Point2D(x_px=point[0], y_px=point[1])
                        for point in candidates.candidate_points
                    ],
                    selected_point=selected_point,
                    detection_type=selected.detection_type,
                    valid=selected_point is not None,
                    contour=global_contour,
                    epipolar_line=list(epipolar_line),
                    minimum_path=(
                        [Point2D(x_px=x, y_px=y) for x, y in selected_path.path]
                        if selected_path
                        else []
                    ),
                    status_reason=(
                        "manual_initialization_required"
                        if selected.requires_manual_initialization
                        else (
                            "minimum_path_unavailable"
                            if not candidates.candidate_points
                            else None
                        )
                    ),
                )
                if selected.selected:
                    side_previous = selected.selected
                if side_settings.update_roi and global_contour:
                    side_roi = self._updated_roi(
                        side_hard_roi,
                        global_contour,
                        side_settings.roi_update_margin_px,
                    )
            side_mask = self._mask_in_frame(
                side_segment.mask,
                side_image.shape[:2],
                side_segment.roi_origin,
            )
            self._store_detection(run, side_detection)
            self._store_frame_artifacts(
                run,
                "side",
                pair.frame_id,
                side_image,
                side_mask,
                side_detection,
            )
            self._set_state(
                run,
                stage="detecting_side_tip",
                current_frame=pair.frame_id,
                progress=0.05 + 0.55 * index / len(pairs),
            )

        self._check_cancel(cancel_event)
        self._set_state(run, stage="interpolating", progress=0.62)
        for camera_id in ("top", "side"):
            self._interpolate_camera(run, camera_id)
        self._resolve_all(run)
        self._write_detection_exports(run)
        self._artifacts(run).write_corrections(
            self.repository.list_corrections(run.analysis_id)
        )
        self._set_state(
            run,
            stage="interpolating",
            current_frame=len(pairs),
            progress=0.68,
        )

    def _interpolate_camera(
        self,
        run: AnalysisRun,
        camera_id: Literal["top", "side"],
    ) -> None:
        self.repository.upsert_detections(
            self._interpolated_camera_detections(run, camera_id)
        )

    def _interpolated_camera_detections(
        self,
        run: AnalysisRun,
        camera_id: Literal["top", "side"],
        correction_items: Iterable[ManualCorrection] | None = None,
    ) -> list[StoredDetection]:
        analysis = self._analysis_settings(run)
        records = self.repository.list_detections(run.analysis_id, camera_id)
        corrections = {
            (item.frame_id, item.camera_id): item
            for item in (
                correction_items
                if correction_items is not None
                else self.repository.list_corrections(run.analysis_id)
            )
        }
        points = []
        for record in records:
            correction = corrections.get((record.frame_id, camera_id))
            automatic = record.automatic_detection
            if correction is not None and correction.invalid:
                selected = None
                detection_type = "Invalid"
                valid = False
                barrier = "Invalid"
            elif correction is not None:
                selected = Point2D(
                    x_px=float(correction.corrected_x_px),
                    y_px=float(correction.corrected_y_px),
                )
                detection_type = "Manual"
                valid = True
                barrier = None
            else:
                selected = automatic.selected_point if automatic else None
                detection_type = (
                    automatic.detection_type if automatic else "Missing"
                )
                status_reason = (
                    automatic.status_reason if automatic else "missing"
                )
                valid = bool(automatic and automatic.valid)
                barrier = status_reason if status_reason in {
                    "camera_disconnected",
                    "record_interrupted",
                    "unpaired",
                    "lighting_transition",
                    "background_initialization",
                } else None
            points.append(
                TrackPoint(
                    frame_id=record.frame_id,
                    timestamp=automatic.timestamp if automatic else None,
                    x_px=selected.x_px if selected else None,
                    y_px=selected.y_px if selected else None,
                    detection_type=detection_type,
                    valid=valid,
                    barrier=barrier,
                )
            )
        interpolated = interpolate_missing_track(
            points,
            maximum_gap_seconds=analysis.interpolation.maximum_gap_seconds,
        )
        by_frame = {item.frame_id: item for item in interpolated}
        updates = []
        for record in records:
            point = by_frame[record.frame_id]
            interpolated_detection = None
            if point.detection_type == "Interpolated":
                interpolated_detection = DetectionResult(
                    frame_id=point.frame_id,
                    camera_id=camera_id,
                    timestamp=point.timestamp,
                    selected_point=Point2D(
                        x_px=float(point.x_px),
                        y_px=float(point.y_px),
                    ),
                    detection_type="Interpolated",
                    valid=True,
                    status_reason="linear_interpolation",
                )
            updated = record.model_copy(
                update={
                    "interpolated_detection": interpolated_detection,
                    "updated_at": utc_now_iso(),
                },
                deep=True,
            )
            updates.append(
                self._apply_correction(
                    updated,
                    corrections.get((record.frame_id, camera_id)),
                )
            )
        return updates

    def _resolve_all(self, run: AnalysisRun) -> None:
        corrections = {
            (item.frame_id, item.camera_id): item
            for item in self.repository.list_corrections(run.analysis_id)
        }
        updates = []
        for stored in self.repository.list_detections(run.analysis_id):
            correction = corrections.get((stored.frame_id, stored.camera_id))
            updates.append(
                self._apply_correction(stored, correction)
            )
        self.repository.upsert_detections(updates)

    def _write_detection_exports(self, run: AnalysisRun) -> None:
        artifacts = self._artifacts(run)
        for camera_id in ("top", "side"):
            artifacts.write_detections(
                camera_id,
                self.repository.list_detections(run.analysis_id, camera_id),
            )

    @staticmethod
    def _category(value: str) -> str:
        return value if value in DETECTION_CATEGORIES else "Missing"

    @staticmethod
    def _category_payload(counter: Counter, total: int) -> dict[str, dict[str, float | int]]:
        return {
            category: {
                "count": int(counter.get(category, 0)),
                "ratio": float(counter.get(category, 0) / total) if total else 0.0,
            }
            for category in DETECTION_CATEGORIES
        }

    def _detection_summary(
        self,
        run: AnalysisRun,
        reprojection: dict[str, float | int],
    ) -> dict[str, Any]:
        counters = {
            "top": Counter(),
            "side": Counter(),
            "rotating": Counter(),
        }
        totals = {"top": 0, "side": 0, "rotating": 0}
        for stored in self.repository.list_detections(run.analysis_id):
            resolved = stored.resolved_detection
            category = self._category(
                resolved.detection_type if resolved else "Missing"
            )
            counters[stored.camera_id][category] += 1
            totals[stored.camera_id] += 1
        overall = counters["top"] + counters["side"] + counters["rotating"]
        overall_total = totals["top"] + totals["side"] + totals["rotating"]
        return {
            "top": self._category_payload(counters["top"], totals["top"]),
            "side": self._category_payload(counters["side"], totals["side"]),
            "rotating": self._category_payload(
                counters["rotating"],
                totals["rotating"],
            ),
            "overall": self._category_payload(overall, overall_total),
            "reprojection": reprojection,
            "paper_comparison_notice": (
                "論文報告值僅供方法比較，不代表本次結果通過或保證相同表現。"
            ),
        }

    def _run_reconstruction(self, run: AnalysisRun, cancel_event: Event) -> None:
        self._check_cancel(cancel_event)
        profile = self._require_calibration(run.calibration_id)
        for camera_id in ("top", "side"):
            self._interpolate_camera(run, camera_id)
        self._resolve_all(run)
        self._write_detection_exports(run)
        self._artifacts(run).write_corrections(
            self.repository.list_corrections(run.analysis_id)
        )
        camera_resolutions = self._camera_resolutions(run)
        adaptation = self._adapted_calibration(
            profile,
            camera_resolutions,
        )
        top_projection = adaptation.top.projection_matrix
        side_projection = adaptation.side.projection_matrix
        world_transform = np.asarray(profile.world_transform_matrix, dtype=np.float64)
        stereo_from_world = np.linalg.inv(world_transform)
        top_world_projection = top_projection @ stereo_from_world
        side_world_projection = side_projection @ stereo_from_world
        uses_rotating = run.method_name == "top_side_rotating"
        rotating_profile = (
            self._adapted_rotating_profile(
                profile,
                camera_resolutions["rotating"],
            )
            if uses_rotating
            else profile
        )
        analysis = self._analysis_settings(run)
        threshold = analysis.reprojection.high_error_threshold_px
        pairs = self.repository.list_frame_pairs(run.analysis_id)
        detections = {
            (stored.frame_id, stored.camera_id): stored
            for stored in self.repository.list_detections(run.analysis_id)
        }
        reconstructed: list[dict[str, Any]] = []
        total = len(pairs)
        self._set_state(run, stage="triangulating", current_frame=0, progress=0.72)
        for index, pair in enumerate(pairs, start=1):
            self._check_cancel(cancel_event)
            top = detections.get((pair.frame_id, "top"))
            side = detections.get((pair.frame_id, "side"))
            top_result = top.resolved_detection if top else None
            side_result = side.resolved_detection if side else None
            if (
                pair.pair_status not in PAIRABLE_STATUSES
                or top_result is None
                or side_result is None
                or not top_result.valid
                or not side_result.valid
                or top_result.selected_point is None
                or side_result.selected_point is None
            ):
                continue
            top_point = (
                top_result.selected_point.x_px,
                top_result.selected_point.y_px,
            )
            side_point = (
                side_result.selected_point.x_px,
                side_result.selected_point.y_px,
            )
            try:
                stereo_point = np.asarray(
                    triangulate_point(
                        top_projection,
                        side_projection,
                        top_point,
                        side_point,
                    ),
                    dtype=np.float64,
                )
                world_point = apply_world_transform(
                    stereo_point.reshape(1, 3),
                    world_transform,
                )[0]
            except ValueError as error:
                self._log(
                    run,
                    "WARNING",
                    f"影格 {pair.frame_id} 三角化失敗，保留為無效：{error}",
                )
                continue
            rotating_result = None
            rotating_point = None
            rotating_error = None
            rotating_used = False
            refined_world_point = (
                world_point.copy()
                if uses_rotating
                else None
            )
            if (
                uses_rotating
                and pair.rotating_capture_id is not None
                and pair.rotating_angle_deg is not None
            ):
                try:
                    rotating_image = self._decode_image(
                        self.get_frame_image_path(
                            run.analysis_id,
                            pair.frame_id,
                            "rotating",
                        )
                    )
                    predicted_point = project_rotating_point(
                        rotating_profile,
                        pair.rotating_angle_deg,
                        world_point,
                    )
                    observation = detect_rotating_tip_near_projection(
                        rotating_image,
                        predicted_point,
                    )
                    if observation.point is not None:
                        rotating_point = observation.point
                        undistorted_point = undistort_rotating_point(
                            rotating_profile,
                            observation.point,
                        )
                        multiview = robust_multiview_triangulate(
                            (
                                top_world_projection,
                                side_world_projection,
                                rotating_projection_matrix(
                                    rotating_profile,
                                    pair.rotating_angle_deg,
                                ),
                            ),
                            (top_point, side_point, undistorted_point),
                            confidence=(1.0, 1.0, observation.confidence),
                            rejection_threshold_px=max(8.0, threshold),
                        )
                        rotating_error = multiview.reprojection_errors_px[2]
                        rotating_used = multiview.used_observations[2]
                        if rotating_used:
                            refined_world_point = multiview.point
                        rotating_result = DetectionResult(
                            frame_id=pair.frame_id,
                            camera_id="rotating",
                            timestamp=pair.rotating_timestamp,
                            candidate_points=[
                                Point2D(
                                    x_px=observation.point[0],
                                    y_px=observation.point[1],
                                )
                            ],
                            selected_point=Point2D(
                                x_px=observation.point[0],
                                y_px=observation.point[1],
                            ),
                            detection_type=(
                                "Automatic"
                                if rotating_used
                                else "Invalid"
                            ),
                            valid=rotating_used,
                            status_reason=(
                                None
                                if rotating_used
                                else "rotating_observation_rejected"
                            ),
                        )
                    else:
                        rotating_result = DetectionResult(
                            frame_id=pair.frame_id,
                            camera_id="rotating",
                            timestamp=pair.rotating_timestamp,
                            detection_type="Missing",
                            valid=False,
                            status_reason="rotating_tip_not_found",
                        )
                    self._store_detection(run, rotating_result)
                    self._store_frame_artifacts(
                        run,
                        "rotating",
                        pair.frame_id,
                        rotating_image,
                        np.zeros(rotating_image.shape[:2], dtype=np.uint8),
                        rotating_result,
                    )
                except Exception as error:
                    self._log(
                        run,
                        "WARNING",
                        f"影格 {pair.frame_id} 的環繞觀測未採用：{error}",
                    )
            reconstructed.append({
                "pair": pair,
                "top": top_result,
                "side": side_result,
                "top_point": top_point,
                "side_point": side_point,
                "stereo_point": stereo_point,
                "world_point": world_point,
                "refined_world_point": refined_world_point,
                "rotating": rotating_result,
                "rotating_point": rotating_point,
                "rotating_error": rotating_error,
                "rotating_used": rotating_used,
            })
            self._set_state(
                run,
                stage="triangulating",
                current_frame=pair.frame_id,
                progress=0.72 + 0.10 * index / max(total, 1),
            )
        if not reconstructed:
            raise AnalysisError("沒有同時具備有效俯視與側視位置的影格，無法三角化。")

        self._check_cancel(cancel_event)
        self._set_state(
            run,
            stage="calculating_reprojection_error",
            progress=0.84,
        )
        stereo_points = np.asarray(
            [item["stereo_point"] for item in reconstructed],
            dtype=np.float64,
        )
        top_observed = np.asarray(
            [item["top_point"] for item in reconstructed],
            dtype=np.float64,
        )
        side_observed = np.asarray(
            [item["side_point"] for item in reconstructed],
            dtype=np.float64,
        )
        top_errors = reprojection_errors(
            top_projection,
            stereo_points,
            top_observed,
        )
        side_errors = reprojection_errors(
            side_projection,
            stereo_points,
            side_observed,
        )
        statistics = summarize_reprojection_errors(
            top_errors,
            side_errors,
            high_error_threshold_px=threshold,
        )
        trajectory_rows = []
        error_rows = []
        for item, top_error, side_error in zip(
            reconstructed,
            top_errors,
            side_errors,
        ):
            pair = item["pair"]
            top_result = item["top"]
            side_result = item["side"]
            world = item["world_point"]
            refined_world = item["refined_world_point"]
            rotating_point = item["rotating_point"]
            rotating_error = item["rotating_error"]
            rotating_used = item["rotating_used"]
            high_error = max(float(top_error), float(side_error)) > threshold
            baseline_overall = float((top_error + side_error) / 2.0)
            refined_overall = (
                float((top_error + side_error + rotating_error) / 3.0)
                if rotating_used and rotating_error is not None
                else baseline_overall
            )
            trajectory_rows.append({
                "frame_id": pair.frame_id,
                "cycle_id": pair.cycle_id,
                "timestamp": pair.top_timestamp or pair.side_timestamp,
                "top_x_px": item["top_point"][0],
                "top_y_px": item["top_point"][1],
                "side_x_px": item["side_point"][0],
                "side_y_px": item["side_point"][1],
                "rotating_x_px": (
                    rotating_point[0]
                    if rotating_point is not None
                    else None
                ),
                "rotating_y_px": (
                    rotating_point[1]
                    if rotating_point is not None
                    else None
                ),
                "rotating_angle_deg": pair.rotating_angle_deg,
                "x_mm": float(world[0]),
                "y_mm": float(world[1]),
                "z_mm": float(world[2]),
                "refined_x_mm": (
                    float(refined_world[0])
                    if refined_world is not None
                    else None
                ),
                "refined_y_mm": (
                    float(refined_world[1])
                    if refined_world is not None
                    else None
                ),
                "refined_z_mm": (
                    float(refined_world[2])
                    if refined_world is not None
                    else None
                ),
                "top_detection_type": self._category(top_result.detection_type),
                "side_detection_type": self._category(side_result.detection_type),
                "top_reprojection_error_px": float(top_error),
                "side_reprojection_error_px": float(side_error),
                "rotating_reprojection_error_px": rotating_error,
                "rotating_used": rotating_used,
                "valid": True,
            })
            error_rows.append({
                "frame_id": pair.frame_id,
                "top_error_px": float(top_error),
                "side_error_px": float(side_error),
                "rotating_error_px": rotating_error,
                "overall_error_px": baseline_overall,
                "refined_overall_error_px": refined_overall,
                "high_error": high_error,
            })

        self._check_cancel(cancel_event)
        self._set_state(run, stage="exporting", progress=0.94)
        artifacts = self._artifacts(run)
        artifacts.write_trajectory(trajectory_rows)
        artifacts.write_reprojection_errors(error_rows)
        reprojection_summary = {
            "top_mean_px": statistics.top_mean_px,
            "side_mean_px": statistics.side_mean_px,
            "overall_mean_px": statistics.overall_mean_px,
            "overall_std_px": statistics.overall_std_px,
            "maximum_error_px": statistics.maximum_error_px,
            "high_error_threshold_px": threshold,
            "high_error_count": statistics.high_error_count,
            "high_error_ratio": statistics.high_error_ratio,
        }
        artifacts.write_detection_summary(
            self._detection_summary(run, reprojection_summary)
        )
        self.repository.update_average_reprojection_error(
            run.analysis_id,
            statistics.overall_mean_px,
        )
        self._check_cancel(cancel_event)
        completed = self._set_state(
            run,
            status="completed",
            stage="completed",
            current_frame=run.total_frames,
            progress=1.0,
            clear_error=True,
        )
        self._log(
            completed,
            "INFO",
            f"分析完成，共輸出 {len(trajectory_rows)} 個有效三維點。",
        )
