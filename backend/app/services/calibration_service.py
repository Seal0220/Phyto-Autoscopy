from __future__ import annotations

import hashlib
import logging
import shutil
import sqlite3
from pathlib import Path
from threading import RLock
from uuid import uuid4

import cv2
import numpy as np

from app.analysis.calibration import (
    calibrate_stereo_from_points,
    compare_camera_projection_models_from_points,
    detect_chessboard_corners,
    require_matching_image_sizes,
    validate_camera_matrix,
    validate_distortion_coefficients,
    validate_finite_matrix,
)
from app.analysis.export.csv_export import write_csv_atomic
from app.analysis.export.json_export import write_json_atomic
from app.analysis.calibration.rotating_calibration import (
    calibrate_rotating_rig_from_points,
)
from app.analysis.reconstruction.coordinate_system import validate_rigid_transform
from app.analysis.run_metadata import next_dated_identifier, utc_now_iso
from app.core.config import AppSettings
from app.core.exceptions import CalibrationError
from app.models.calibration_models import (
    CalibrationCreateRequest,
    CalibrationProfile,
    CalibrationReport,
)
from app.repositories.calibration_repository import CalibrationRepository


logger = logging.getLogger(__name__)


_CALIBRATION_IMAGE_EXTENSIONS = {
    ".bmp",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
}


class CalibrationService:
    def __init__(
        self,
        settings: AppSettings,
        repository: CalibrationRepository,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self._lock = RLock()

    @property
    def project_root(self) -> Path:
        return Path.cwd().resolve()

    def _allowed_image_roots(self) -> tuple[Path, ...]:
        return (
            self.settings.paths.captures_dir.resolve(),
            self.settings.paths.calibration_dir.resolve(),
        )

    def _safe_image_path(self, value: str) -> Path:
        candidate = Path(value)
        resolved = (
            candidate.resolve()
            if candidate.is_absolute()
            else (self.project_root / candidate).resolve()
        )
        if not any(
            resolved == root or root in resolved.parents
            for root in self._allowed_image_roots()
        ):
            raise CalibrationError("校正影像必須位於擷取或校正資料目錄內。")
        calibration_root = self.settings.paths.calibration_dir.resolve()
        if calibration_root in resolved.parents:
            relative_to_calibration = resolved.relative_to(calibration_root)
            if "previews" in relative_to_calibration.parts:
                raise CalibrationError("校正角點預覽不能當作校正來源影像。")
        if not resolved.is_file():
            raise CalibrationError(f"找不到校正影像：{value}")
        if resolved.suffix.lower() not in _CALIBRATION_IMAGE_EXTENSIONS:
            raise CalibrationError(f"不支援的校正影像格式：{value}")
        return resolved

    def _stored_image_path(self, value: str) -> str:
        resolved = self._safe_image_path(value)
        try:
            return resolved.relative_to(self.project_root).as_posix()
        except ValueError:
            return str(resolved)

    @staticmethod
    def _flatten_selected_images(selected_images: dict[str, list]) -> list[str]:
        paths = [
            *selected_images.get("top", []),
            *selected_images.get("side", []),
        ]
        paths.extend(
            path
            for pair in selected_images.get("stereo", [])
            for path in pair
        )
        paths.extend(
            item["path"] if isinstance(item, dict) else item
            for item in selected_images.get("rotating", [])
        )
        return list(dict.fromkeys(str(path) for path in paths))

    def _image_fingerprint(self, value: str) -> dict[str, int | str]:
        path = self._safe_image_path(value)
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        stat = path.stat()
        return {
            "size_bytes": stat.st_size,
            "modified_time_ns": stat.st_mtime_ns,
            "sha256": digest.hexdigest(),
        }

    def _selected_image_fingerprints(
        self,
        selected_images: dict[str, list],
    ) -> dict[str, dict]:
        return {
            path: self._image_fingerprint(path)
            for path in self._flatten_selected_images(selected_images)
        }

    @staticmethod
    def _write_bytes_atomic(path: Path, payload: bytes) -> None:
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_bytes(payload)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def _profile_dir(self, profile: CalibrationProfile) -> Path:
        path = Path(profile.output_path).resolve()
        root = self.settings.paths.calibration_dir.resolve()
        if path.parent != root or path.name != profile.calibration_id:
            raise CalibrationError("相機校正設定檔儲存位置無效。")
        return path

    def _write_profile(self, profile: CalibrationProfile) -> None:
        directory = self._profile_dir(profile)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "previews").mkdir(parents=True, exist_ok=True)
        write_json_atomic(
            directory / "selected_images.json",
            profile.selected_images,
        )
        self._write_error_csv(profile)
        self._write_intrinsics(profile, "top")
        self._write_intrinsics(profile, "side")
        self._write_intrinsics(profile, "rotating")
        self._write_stereo_extrinsics(profile)
        rotating_rig_path = directory / "rotating_rig.json"
        if profile.supports_rotating:
            write_json_atomic(rotating_rig_path, {
                "axis_origin_mm": profile.rotating_axis_origin_mm,
                "axis_direction": profile.rotating_axis_direction,
                "zero_angle_deg": profile.rotating_zero_angle_deg,
                "angle_direction": profile.rotating_angle_direction,
                "world_from_camera_at_zero": (
                    profile.rotating_axis_from_camera_matrix
                ),
                "residual_mean_px": profile.rotating_pose_residual_mean_px,
                "residual_max_px": profile.rotating_pose_residual_max_px,
                "samples": profile.rotating_pose_samples,
            })
        else:
            rotating_rig_path.unlink(missing_ok=True)
        # calibration.json 最後替換，作為此輪檔案組更新完成的標記。
        write_json_atomic(
            directory / "calibration.json",
            profile.model_dump(mode="json"),
        )

    def _write_intrinsics(
        self,
        profile: CalibrationProfile,
        camera_id: str,
    ) -> None:
        matrix = getattr(profile, f"{camera_id}_camera_matrix")
        distortion = getattr(profile, f"{camera_id}_distortion_coefficients")
        output = self._profile_dir(profile) / f"{camera_id}_intrinsics.json"
        if matrix is None or distortion is None:
            output.unlink(missing_ok=True)
            return
        projection_model = profile.camera_projection_models.get(
            camera_id,
            "brown_pinhole",
        )
        distortion_order = profile.camera_distortion_orders.get(
            camera_id,
            profile.distortion_coefficient_order,
        )
        distortion_named = {
            name: float(distortion[index])
            for index, name in enumerate(distortion_order)
            if index < len(distortion)
        }
        image_size = profile.camera_image_sizes.get(
            camera_id,
            [profile.image_width, profile.image_height],
        )
        payload = {
            "image_width": image_size[0],
            "image_height": image_size[1],
            "chessboard_pattern": profile.chessboard_pattern,
            "square_size_mm": profile.square_size_mm,
            "camera_matrix": matrix,
            "projection_model": projection_model,
            "distortion_coefficients": distortion,
            "distortion_coefficient_order": distortion_order,
            "distortion_named": distortion_named,
            "model_evaluation": profile.camera_model_evaluations.get(
                camera_id,
                {},
            ),
            "rotation_vectors": getattr(profile, f"{camera_id}_rotation_vectors"),
            "translation_vectors": getattr(
                profile,
                f"{camera_id}_translation_vectors",
            ),
            "mean_reprojection_error": getattr(
                profile,
                f"{camera_id}_mean_reprojection_error",
            ),
            "reprojection_error_per_image": profile.reprojection_error_per_image.get(
                camera_id,
                [],
            ),
            "point_coverage": profile.point_coverage.get(camera_id),
        }
        write_json_atomic(output, payload)

    def _write_stereo_extrinsics(self, profile: CalibrationProfile) -> None:
        output = self._profile_dir(profile) / "stereo_extrinsics.json"
        fields = (
            "rotation_matrix",
            "translation_vector",
            "essential_matrix",
            "fundamental_matrix",
            "top_projection_matrix",
            "side_projection_matrix",
        )
        if any(getattr(profile, field) is None for field in fields):
            output.unlink(missing_ok=True)
            return
        write_json_atomic(
            output,
            {
                "image_width": profile.image_width,
                "image_height": profile.image_height,
                "chessboard_pattern": profile.stereo_chessboard_pattern,
                "square_size_mm": profile.stereo_square_size_mm,
                "rotation_matrix": profile.rotation_matrix,
                "translation_vector": profile.translation_vector,
                "essential_matrix": profile.essential_matrix,
                "fundamental_matrix": profile.fundamental_matrix,
                "top_rectification_rotation": profile.top_rectification_rotation,
                "side_rectification_rotation": profile.side_rectification_rotation,
                "top_projection_matrix": profile.top_projection_matrix,
                "side_projection_matrix": profile.side_projection_matrix,
                "disparity_to_depth_matrix": profile.disparity_to_depth_matrix,
                "top_valid_pixel_roi": profile.top_valid_pixel_roi,
                "side_valid_pixel_roi": profile.side_valid_pixel_roi,
                "stereo_mean_reprojection_error": (
                    profile.stereo_mean_reprojection_error
                ),
                "reprojection_error_per_pair": (
                    profile.reprojection_error_per_image.get("stereo", [])
                ),
                "point_coverage": profile.point_coverage.get("stereo"),
            },
        )

    def _write_error_csv(self, profile: CalibrationProfile) -> None:
        rows = []
        for camera_id in ("top", "side", "rotating", "stereo"):
            for item in profile.reprojection_error_per_image.get(camera_id, []):
                rows.append({"camera_id": camera_id, **item})
        fields = (
            "camera_id",
            "image_id",
            "pair_id",
            "point_count",
            "rms_error_px",
            "max_error_px",
            "top_rms_error_px",
            "side_rms_error_px",
            "combined_rms_error_px",
            "epipolar_rms_error_px",
        )
        write_csv_atomic(
            self._profile_dir(profile) / "reprojection_errors.csv",
            fields,
            rows,
        )

    def _persist(self, profile: CalibrationProfile) -> CalibrationProfile:
        previous = self.repository.get(profile.calibration_id)
        if previous is None:
            raise CalibrationError(
                f"相機校正設定檔不存在：{profile.calibration_id}"
            )
        profile.updated_at = utc_now_iso()
        try:
            self._write_profile(profile)
            self.repository.update(profile)
        except Exception as error:
            try:
                self._write_profile(previous)
            except Exception:
                logger.exception(
                    "Failed to restore calibration profile files: %s",
                    profile.calibration_id,
                )
            if isinstance(error, CalibrationError):
                raise
            raise CalibrationError("寫入相機校正設定檔失敗。") from error
        return profile

    def create(
        self,
        request: CalibrationCreateRequest,
    ) -> CalibrationProfile:
        with self._lock:
            root = self.settings.paths.calibration_dir.resolve()
            calibration_id = next_dated_identifier(root, "calibration")
            now = utc_now_iso()
            output_path = root / calibration_id
            top_paths = [
                self._stored_image_path(path)
                for path in request.top_image_paths
            ]
            side_paths = [
                self._stored_image_path(path)
                for path in request.side_image_paths
            ]
            top_sources = {
                self._safe_image_path(path)
                for path in top_paths
            }
            side_sources = {
                self._safe_image_path(path)
                for path in side_paths
            }
            if top_sources & side_sources:
                raise CalibrationError(
                    "俯視與側視單目校正影像不得重複使用同一檔案。"
                )
            stereo_pairs = [
                [
                    self._stored_image_path(pair[0]),
                    self._stored_image_path(pair[1]),
                ]
                for pair in request.stereo_image_pairs
            ]
            if any(
                self._safe_image_path(pair[0]) == self._safe_image_path(pair[1])
                for pair in stereo_pairs
            ):
                raise CalibrationError(
                    "雙目校正的俯視與側視影像不得是同一檔案。"
                )
            rotating_images = [
                {
                    "path": self._stored_image_path(item.path),
                    "angle_deg": float(item.angle_deg),
                }
                for item in request.rotating_images
            ]
            selected_images = {
                "top": top_paths,
                "side": side_paths,
                "stereo": stereo_pairs,
                "rotating": rotating_images,
            }
            individual_square = [
                request.square_size_mm_x,
                request.square_size_mm_y,
            ]
            stereo_square = [
                request.stereo_square_size_mm_x,
                request.stereo_square_size_mm_y,
            ]
            stereo_pattern = [
                request.stereo_pattern_columns,
                request.stereo_pattern_rows,
            ]
            paper_baseline = {
                "reference": "Ruiz-Melero et al. 2024",
                "individual_pattern": [10, 7],
                "individual_board_size_cm": [59.4, 84.1],
                "stereo_board_size_cm": [42.0, 59.4],
                "stereo_pattern": None,
                "square_size_mm": None,
            }
            profile = CalibrationProfile(
                calibration_id=calibration_id,
                created_at=now,
                updated_at=now,
                status="draft",
                valid=False,
                output_path=output_path.as_posix(),
                top_camera_identifier=request.top_camera_identifier,
                side_camera_identifier=request.side_camera_identifier,
                rotating_camera_identifier=request.rotating_camera_identifier,
                camera_model_name=request.camera_model_name,
                sensor_name=request.sensor_name,
                sensor_width_mm=request.sensor_width_mm,
                sensor_height_mm=request.sensor_height_mm,
                focal_length_mm=request.focal_length_mm,
                diagonal_fov_deg=request.diagonal_fov_deg,
                chessboard_pattern=[request.pattern_columns, request.pattern_rows],
                stereo_chessboard_pattern=stereo_pattern,
                square_size_mm=individual_square,
                stereo_square_size_mm=stereo_square,
                individual_board_size_cm=[
                    request.individual_board_width_cm,
                    request.individual_board_height_cm,
                ],
                stereo_board_size_cm=[
                    request.stereo_board_width_cm,
                    request.stereo_board_height_cm,
                ],
                paper_baseline=paper_baseline,
                actual_measurement_difference={
                    "individual_board_width_cm": (
                        request.individual_board_width_cm - 59.4
                    ),
                    "individual_board_height_cm": (
                        request.individual_board_height_cm - 84.1
                    ),
                    "stereo_board_width_cm": (
                        request.stereo_board_width_cm - 42.0
                    ),
                    "stereo_board_height_cm": (
                        request.stereo_board_height_cm - 59.4
                    ),
                    "individual_pattern_differs": [
                        request.pattern_columns,
                        request.pattern_rows,
                    ] != [10, 7],
                    "stereo_pattern_is_implementation_measurement": True,
                    "individual_square_size_mm": individual_square,
                    "stereo_square_size_mm": stereo_square,
                    "square_sizes_are_explicit_measurements": True,
                },
                selected_images=selected_images,
                camera_fingerprint={
                    camera_id: self.settings.cameras[camera_id].model_dump(mode="json")
                    for camera_id in (
                        ("top", "side", "rotating")
                        if rotating_images
                        else ("top", "side")
                    )
                },
                camera_projection_models={
                    camera_id: "brown_pinhole"
                    for camera_id in (
                        ("top", "side", "rotating")
                        if rotating_images
                        else ("top", "side")
                    )
                },
                selected_image_fingerprints=self._selected_image_fingerprints(
                    selected_images
                ),
                world_coordinate_system=request.world_coordinate_system,
                world_transform_matrix=request.world_transform_matrix,
                notes=request.notes,
            )
            try:
                output_path.mkdir(parents=True, exist_ok=False)
                self._write_profile(profile)
                self.repository.create(profile)
            except Exception as error:
                logger.exception("Failed to create calibration profile %s", calibration_id)
                shutil.rmtree(output_path, ignore_errors=True)
                if isinstance(error, CalibrationError):
                    raise
                raise CalibrationError("建立相機校正設定檔失敗。") from error
            return profile

    def _stale_reasons(self, profile: CalibrationProfile) -> list[str]:
        reasons = list(profile.manual_invalidation_reasons)
        camera_ids = ["top", "side"]
        if profile.selected_images.get("rotating"):
            camera_ids.append("rotating")
        for camera_id in camera_ids:
            current = self.settings.cameras.get(camera_id)
            saved = profile.camera_fingerprint.get(camera_id, {})
            if current is None:
                reasons.append(f"{camera_id} 相機角色已不存在。")
                continue
            for key, label in (
                ("device_name", "相機硬體名稱"),
                ("device_index", "裝置索引"),
            ):
                if saved.get(key) != getattr(current, key):
                    reasons.append(f"{camera_id} 的{label}已變更。")
        for image_path in self._flatten_selected_images(profile.selected_images):
            saved = profile.selected_image_fingerprints.get(image_path)
            if saved is None:
                reasons.append(f"校正來源影像缺少完整性指紋：{image_path}")
                continue
            try:
                current_path = self._safe_image_path(image_path)
                stat = current_path.stat()
            except (CalibrationError, OSError):
                reasons.append(f"校正來源影像已不存在或不安全：{image_path}")
                continue
            if stat.st_size != saved.get("size_bytes"):
                reasons.append(f"校正來源影像內容已變更：{image_path}")
                continue
            current = self._image_fingerprint(image_path)
            if current["sha256"] != saved.get("sha256"):
                reasons.append(f"校正來源影像內容已變更：{image_path}")
        return list(dict.fromkeys(reasons))

    @staticmethod
    def _has_only_resolution_invalidation(reasons: list[str]) -> bool:
        return bool(reasons) and all(
            "影像寬度已變更" in reason or "影像高度已變更" in reason
            for reason in reasons
        )

    def _with_stale_state(
        self,
        profile: CalibrationProfile,
    ) -> CalibrationProfile:
        reasons = self._stale_reasons(profile)
        update: dict = {"potentially_invalid_reasons": reasons}
        if reasons and profile.status in {"valid", "potentially_invalid"}:
            update.update({
                "status": "potentially_invalid",
                "valid": False,
                "last_error": "校正來源或相機設定已變更，請重新校正。",
            })
        elif (
            not reasons
            and profile.status == "potentially_invalid"
            and self._has_only_resolution_invalidation(
                profile.potentially_invalid_reasons
            )
        ):
            update.update({
                "status": "valid",
                "valid": True,
                "last_error": None,
            })
        return profile.model_copy(update=update)

    def list_profiles(self) -> list[CalibrationProfile]:
        return [self._with_stale_state(profile) for profile in self.repository.list()]

    def get_profile(self, calibration_id: str) -> CalibrationProfile:
        profile = self.repository.get(calibration_id)
        if profile is None:
            raise CalibrationError(f"找不到相機校正設定檔：{calibration_id}")
        return self._with_stale_state(profile)

    def _ensure_not_referenced(self, calibration_id: str) -> None:
        referenced = self.repository.database.fetchone(
            "SELECT 1 FROM analysis_runs WHERE calibration_id=? LIMIT 1",
            (calibration_id,),
        )
        if referenced:
            raise CalibrationError(
                "相機校正設定檔已被分析引用，不能覆寫校正結果；"
                "請建立新的相機校正設定檔。"
            )

    def list_source_images(self, limit: int = 500) -> list[dict]:
        if not 1 <= limit <= 1000:
            raise CalibrationError("校正來源影像數量限制必須介於 1 至 1000。")
        candidates: list[tuple[int, Path, Path, str]] = []
        seen_paths: set[Path] = set()
        for source_name, root in (
            ("captures", self.settings.paths.captures_dir.resolve()),
            ("calibration", self.settings.paths.calibration_dir.resolve()),
        ):
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if len(candidates) >= 5000:
                    break
                if path.suffix.lower() not in _CALIBRATION_IMAGE_EXTENSIONS:
                    continue
                try:
                    resolved = path.resolve()
                    if (
                        resolved in seen_paths
                        or root not in resolved.parents
                        or not resolved.is_file()
                    ):
                        continue
                    relative_to_source = resolved.relative_to(root)
                    if "previews" in relative_to_source.parts:
                        continue
                    stat = resolved.stat()
                except (OSError, ValueError):
                    continue
                seen_paths.add(resolved)
                candidates.append((stat.st_mtime_ns, resolved, root, source_name))
        candidates.sort(key=lambda item: (-item[0], str(item[1])))
        images: list[dict] = []
        for modified_time_ns, path, root, source_name in candidates:
            try:
                encoded = np.fromfile(path, dtype=np.uint8)
                image = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
                if image is None or image.ndim < 2:
                    continue
                stat = path.stat()
                stored_path = self._stored_image_path(str(path))
            except (CalibrationError, OSError, ValueError):
                continue
            images.append({
                "path": stored_path,
                "source": source_name,
                "name": path.name,
                "relative_path": path.relative_to(root).as_posix(),
                "size_bytes": stat.st_size,
                "modified_time_ns": modified_time_ns,
                "image_width": int(image.shape[1]),
                "image_height": int(image.shape[0]),
            })
            if len(images) >= limit:
                break
        return images

    def get_preview_path(
        self,
        calibration_id: str,
        preview_name: str,
    ) -> Path:
        normalized = Path(preview_name)
        if (
            not preview_name
            or normalized.is_absolute()
            or normalized.name != preview_name
            or normalized.suffix.lower() not in {".jpg", ".jpeg", ".png"}
        ):
            raise CalibrationError("校正預覽檔名無效。")
        profile = self.get_profile(calibration_id)
        preview_directory = (self._profile_dir(profile) / "previews").resolve()
        preview_path = (preview_directory / normalized.name).resolve()
        if preview_path.parent != preview_directory or not preview_path.is_file():
            raise CalibrationError(f"找不到校正預覽：{preview_name}")
        return preview_path

    def mark_potentially_invalid(
        self,
        calibration_id: str,
        reason: str,
    ) -> CalibrationProfile:
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise CalibrationError("校正失效原因不得為空。")
        if len(normalized_reason) > 500:
            raise CalibrationError("校正失效原因不得超過 500 字。")
        with self._lock:
            profile = self.get_profile(calibration_id)
            profile.manual_invalidation_reasons = list(dict.fromkeys([
                *profile.manual_invalidation_reasons,
                normalized_reason,
            ]))
            profile.potentially_invalid_reasons = self._stale_reasons(profile)
            profile.status = "potentially_invalid"
            profile.valid = False
            profile.last_error = "相機實體配置已變更，請重新校正。"
            return self._persist(profile)

    @staticmethod
    def _detection_payload(path: str, pattern: list[int]) -> dict:
        detection = detect_chessboard_corners(
            path,
            pattern,
            image_id=path,
        )
        return detection.to_dict(include_corners=True)

    def _write_corner_preview(
        self,
        profile: CalibrationProfile,
        image_path: str,
        detection: dict,
        pattern: list[int],
        output_name: str,
    ) -> None:
        encoded = np.fromfile(self._safe_image_path(image_path), dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image is None:
            raise CalibrationError(f"無法解碼校正影像：{image_path}")
        corners = detection.get("corners")
        if corners:
            cv2.drawChessboardCorners(
                image,
                tuple(pattern),
                np.asarray(corners, dtype=np.float32).reshape(-1, 1, 2),
                True,
            )
        success, preview = cv2.imencode(".jpg", image)
        if not success:
            raise CalibrationError(f"無法建立角點預覽：{image_path}")
        preview_path = self._profile_dir(profile) / "previews" / output_name
        self._write_bytes_atomic(preview_path, preview.tobytes())

    @staticmethod
    def _clear_stereo_solution(profile: CalibrationProfile) -> None:
        for name in (
            "rotation_matrix",
            "translation_vector",
            "essential_matrix",
            "fundamental_matrix",
            "top_projection_matrix",
            "side_projection_matrix",
            "top_rectification_rotation",
            "side_rectification_rotation",
            "disparity_to_depth_matrix",
            "top_valid_pixel_roi",
            "side_valid_pixel_roi",
            "stereo_mean_reprojection_error",
        ):
            setattr(profile, name, None)
        profile.reprojection_error_per_image.pop("stereo", None)
        profile.point_coverage.pop("stereo", None)

    @classmethod
    def _clear_intrinsics_solution(cls, profile: CalibrationProfile) -> None:
        for camera_id in ("top", "side", "rotating"):
            for suffix in (
                "camera_matrix",
                "distortion_coefficients",
                "mean_reprojection_error",
            ):
                setattr(profile, f"{camera_id}_{suffix}", None)
            setattr(profile, f"{camera_id}_rotation_vectors", [])
            setattr(profile, f"{camera_id}_translation_vectors", [])
            profile.reprojection_error_per_image.pop(camera_id, None)
            profile.point_coverage.pop(camera_id, None)
            profile.camera_image_sizes.pop(camera_id, None)
        for name in (
            "rotating_axis_origin_mm",
            "rotating_axis_direction",
            "rotating_zero_angle_deg",
            "rotating_angle_direction",
            "rotating_axis_from_camera_matrix",
            "rotating_pose_residual_mean_px",
            "rotating_pose_residual_max_px",
        ):
            setattr(profile, name, None)
        profile.rotating_pose_samples = []
        profile.camera_projection_models = {}
        profile.camera_model_evaluations = {}
        profile.camera_distortion_orders = {}
        profile.image_width = None
        profile.image_height = None
        cls._clear_stereo_solution(profile)

    def _clear_previews(self, profile: CalibrationProfile) -> None:
        preview_directory = self._profile_dir(profile) / "previews"
        if not preview_directory.exists():
            return
        for path in preview_directory.iterdir():
            if path.is_file():
                path.unlink()

    def detect_corners(self, calibration_id: str) -> CalibrationProfile:
        with self._lock:
            profile = self.get_profile(calibration_id)
            self._ensure_not_referenced(calibration_id)
            top = []
            side = []
            stereo = []
            rotating = []
            profile.corner_detections = {
                "top": top,
                "side": side,
                "stereo": stereo,
                "rotating": rotating,
            }
            self._clear_intrinsics_solution(profile)
            self._clear_previews(profile)
            profile.valid = False
            try:
                for camera_id, target in (("top", top), ("side", side)):
                    for index, path in enumerate(profile.selected_images[camera_id]):
                        absolute = str(self._safe_image_path(path))
                        detection = self._detection_payload(
                            absolute,
                            profile.chessboard_pattern,
                        )
                        detection["image_id"] = path
                        preview_name = f"{camera_id}_{index + 1:04d}.jpg"
                        detection["preview_name"] = preview_name
                        target.append(detection)
                        self._write_corner_preview(
                            profile,
                            path,
                            detection,
                            profile.chessboard_pattern,
                            preview_name,
                        )
                if profile.stereo_chessboard_pattern is None:
                    raise CalibrationError(
                        "雙目棋盤內角點規格尚未設定，不能由論文板面尺寸推導。"
                    )
                for index, pair in enumerate(profile.selected_images["stereo"]):
                    top_detection = self._detection_payload(
                        str(self._safe_image_path(pair[0])),
                        profile.stereo_chessboard_pattern,
                    )
                    side_detection = self._detection_payload(
                        str(self._safe_image_path(pair[1])),
                        profile.stereo_chessboard_pattern,
                    )
                    top_detection["image_id"] = pair[0]
                    side_detection["image_id"] = pair[1]
                    top_preview_name = f"stereo_{index + 1:04d}_top.jpg"
                    side_preview_name = f"stereo_{index + 1:04d}_side.jpg"
                    top_detection["preview_name"] = top_preview_name
                    side_detection["preview_name"] = side_preview_name
                    stereo.append({
                        "pair_id": f"stereo_{index + 1:04d}",
                        "top": top_detection,
                        "side": side_detection,
                        "usable": bool(
                            top_detection["found"] and side_detection["found"]
                        ),
                    })
                    self._write_corner_preview(
                        profile,
                        pair[0],
                        top_detection,
                        profile.stereo_chessboard_pattern,
                        top_preview_name,
                    )
                    self._write_corner_preview(
                        profile,
                        pair[1],
                        side_detection,
                        profile.stereo_chessboard_pattern,
                        side_preview_name,
                    )
                for index, item in enumerate(
                    profile.selected_images.get("rotating", [])
                ):
                    path = item["path"]
                    detection = self._detection_payload(
                        str(self._safe_image_path(path)),
                        profile.chessboard_pattern,
                    )
                    detection["image_id"] = path
                    detection["angle_deg"] = float(item["angle_deg"])
                    preview_name = f"rotating_{index + 1:04d}.jpg"
                    detection["preview_name"] = preview_name
                    rotating.append(detection)
                    self._write_corner_preview(
                        profile,
                        path,
                        detection,
                        profile.chessboard_pattern,
                        preview_name,
                    )
                if not any(item.get("found") for item in top):
                    raise CalibrationError("俯視校正影像未偵測到任何棋盤角點。")
                if not any(item.get("found") for item in side):
                    raise CalibrationError("側視校正影像未偵測到任何棋盤角點。")
                if not any(item.get("usable") for item in stereo):
                    raise CalibrationError("沒有雙目校正影像同時偵測到棋盤角點。")
                if rotating and len({
                    item["angle_deg"]
                    for item in rotating
                    if item.get("found")
                }) < 3:
                    raise CalibrationError(
                        "環繞校正至少需要三個不同角度成功偵測棋盤角點。"
                    )
                profile.selected_image_fingerprints = (
                    self._selected_image_fingerprints(profile.selected_images)
                )
                profile.status = "corners_detected"
                profile.valid = False
                profile.last_error = None
            except Exception as error:
                profile.status = "failed"
                profile.valid = False
                profile.last_error = str(error)
                self._persist(profile)
                if isinstance(error, CalibrationError):
                    raise
                raise CalibrationError(f"棋盤角點偵測失敗：{error}") from error
            return self._persist(profile)

    @staticmethod
    def _successful_detections(profile: CalibrationProfile, camera_id: str) -> list[dict]:
        return [
            item
            for item in profile.corner_detections.get(camera_id, [])
            if item.get("found") and item.get("corners")
        ]

    @staticmethod
    def _matching_detection_size(
        detections: list[dict],
        *,
        camera_id: str,
    ) -> tuple[int, int]:
        return require_matching_image_sizes(
            [
                (item["image_width"], item["image_height"])
                for item in detections
            ],
            names=[
                f"{camera_id}:{item.get('image_id', index)}"
                for index, item in enumerate(detections)
            ],
        )

    def solve_intrinsics(self, calibration_id: str) -> CalibrationProfile:
        with self._lock:
            profile = self.get_profile(calibration_id)
            self._ensure_not_referenced(calibration_id)
            self._clear_intrinsics_solution(profile)
            profile.valid = False
            try:
                if profile.square_size_mm is None:
                    raise CalibrationError("單目棋盤格實測尺寸尚未設定。")
                candidate_results = {}
                model_evaluations = {}
                image_sizes = {}
                camera_ids = ["top", "side"]
                if profile.selected_images.get("rotating"):
                    camera_ids.append("rotating")
                for camera_id in camera_ids:
                    detections = self._successful_detections(profile, camera_id)
                    if not detections:
                        raise CalibrationError(
                            f"{camera_id} 沒有成功偵測角點的校正影像。"
                        )
                    image_size = self._matching_detection_size(
                        detections,
                        camera_id=camera_id,
                    )
                    image_sizes[camera_id] = image_size
                    candidates, evaluations = compare_camera_projection_models_from_points(
                        [item["corners"] for item in detections],
                        image_size,
                        profile.chessboard_pattern,
                        profile.square_size_mm,
                        image_ids=[item["image_id"] for item in detections],
                        total_image_count=len(
                            profile.corner_detections.get(camera_id, [])
                        ),
                        diagonal_fov_deg=profile.diagonal_fov_deg,
                    )
                    candidate_results[camera_id] = candidates
                    model_evaluations[camera_id] = evaluations
                require_matching_image_sizes(
                    [image_sizes["top"], image_sizes["side"]],
                    names=["俯視校正影像", "側視校正影像"],
                )
                common_models = set(candidate_results["top"]).intersection(
                    candidate_results["side"]
                )

                def model_score(camera_id: str, model: str) -> float:
                    evaluation = model_evaluations[camera_id][model]
                    mean = float(evaluation["mean_reprojection_error_px"])
                    deviation = float(evaluation["per_image_error_std_px"])
                    return mean + deviation

                stereo_model = min(
                    common_models,
                    key=lambda model: (
                        model_score("top", model)
                        + model_score("side", model)
                    ),
                )
                selected_models = {
                    "top": stereo_model,
                    "side": stereo_model,
                }
                if "rotating" in candidate_results:
                    selected_models["rotating"] = min(
                        candidate_results["rotating"],
                        key=lambda model: model_score("rotating", model),
                    )
                results = {
                    camera_id: candidate_results[camera_id][model]
                    for camera_id, model in selected_models.items()
                }
                for camera_id, evaluations in model_evaluations.items():
                    for model, evaluation in evaluations.items():
                        evaluation["selected"] = (
                            selected_models.get(camera_id) == model
                        )
                profile.camera_projection_models = selected_models
                profile.camera_model_evaluations = model_evaluations
                profile.camera_distortion_orders = {
                    camera_id: (
                        ["k1", "k2", "k3", "k4"]
                        if model == "fisheye"
                        else ["k1", "k2", "p1", "p2", "k3"]
                    )
                    for camera_id, model in selected_models.items()
                }
                top_result = results["top"]
                side_result = results["side"]
                profile.image_width, profile.image_height = top_result.image_size
                profile.camera_image_sizes = {
                    camera_id: list(result.image_size)
                    for camera_id, result in results.items()
                }
                profile.top_camera_matrix = top_result.camera_matrix.tolist()
                profile.top_distortion_coefficients = (
                    top_result.distortion_coefficients.reshape(-1).tolist()
                )
                profile.side_camera_matrix = side_result.camera_matrix.tolist()
                profile.side_distortion_coefficients = (
                    side_result.distortion_coefficients.reshape(-1).tolist()
                )
                profile.top_rotation_vectors = [
                    item.reshape(-1).tolist()
                    for item in top_result.rotation_vectors
                ]
                profile.top_translation_vectors = [
                    item.reshape(-1).tolist()
                    for item in top_result.translation_vectors
                ]
                profile.side_rotation_vectors = [
                    item.reshape(-1).tolist()
                    for item in side_result.rotation_vectors
                ]
                profile.side_translation_vectors = [
                    item.reshape(-1).tolist()
                    for item in side_result.translation_vectors
                ]
                profile.top_mean_reprojection_error = (
                    top_result.mean_reprojection_error
                )
                profile.side_mean_reprojection_error = (
                    side_result.mean_reprojection_error
                )
                if "rotating" in results:
                    rotating_result = results["rotating"]
                    profile.rotating_camera_matrix = (
                        rotating_result.camera_matrix.tolist()
                    )
                    profile.rotating_distortion_coefficients = (
                        rotating_result.distortion_coefficients.reshape(-1).tolist()
                    )
                    profile.rotating_rotation_vectors = [
                        item.reshape(-1).tolist()
                        for item in rotating_result.rotation_vectors
                    ]
                    profile.rotating_translation_vectors = [
                        item.reshape(-1).tolist()
                        for item in rotating_result.translation_vectors
                    ]
                    profile.rotating_mean_reprojection_error = (
                        rotating_result.mean_reprojection_error
                    )
                profile.reprojection_error_per_image.update({
                    "top": list(top_result.reprojection_error_per_image),
                    "side": list(side_result.reprojection_error_per_image),
                })
                profile.point_coverage.update({
                    "top": top_result.point_coverage,
                    "side": side_result.point_coverage,
                })
                if "rotating" in results:
                    profile.reprojection_error_per_image["rotating"] = list(
                        results["rotating"].reprojection_error_per_image
                    )
                    profile.point_coverage["rotating"] = (
                        results["rotating"].point_coverage
                    )
                profile.status = "intrinsics_solved"
                profile.valid = False
                profile.last_error = None
            except Exception as error:
                profile.status = "failed"
                profile.valid = False
                profile.last_error = str(error)
                self._persist(profile)
                if isinstance(error, CalibrationError):
                    raise
                raise CalibrationError(f"單目相機校正失敗：{error}") from error
            return self._persist(profile)

    def solve_stereo(self, calibration_id: str) -> CalibrationProfile:
        with self._lock:
            profile = self.get_profile(calibration_id)
            self._ensure_not_referenced(calibration_id)
            self._clear_stereo_solution(profile)
            profile.valid = False
            try:
                if (
                    profile.stereo_chessboard_pattern is None
                    or profile.stereo_square_size_mm is None
                ):
                    raise CalibrationError(
                        "雙目棋盤內角點與棋盤格實測尺寸尚未設定。"
                    )
                required = (
                    profile.top_camera_matrix,
                    profile.top_distortion_coefficients,
                    profile.side_camera_matrix,
                    profile.side_distortion_coefficients,
                )
                if any(value is None for value in required):
                    raise CalibrationError("請先完成俯視與側視單目校正。")
                pairs = [
                    item
                    for item in profile.corner_detections.get("stereo", [])
                    if item.get("usable")
                ]
                if not pairs:
                    raise CalibrationError("沒有可用的雙目棋盤角點配對。")
                top_size = self._matching_detection_size(
                    [item["top"] for item in pairs],
                    camera_id="stereo:top",
                )
                side_size = self._matching_detection_size(
                    [item["side"] for item in pairs],
                    camera_id="stereo:side",
                )
                expected_size = (profile.image_width, profile.image_height)
                require_matching_image_sizes(
                    [expected_size, top_size, side_size],
                    names=["單目校正", "雙目俯視影像", "雙目側視影像"],
                )
                result = calibrate_stereo_from_points(
                    [item["top"]["corners"] for item in pairs],
                    [item["side"]["corners"] for item in pairs],
                    (
                        pairs[0]["top"]["image_width"],
                        pairs[0]["top"]["image_height"],
                    ),
                    (
                        pairs[0]["side"]["image_width"],
                        pairs[0]["side"]["image_height"],
                    ),
                    profile.stereo_chessboard_pattern,
                    profile.stereo_square_size_mm,
                    profile.top_camera_matrix,
                    profile.top_distortion_coefficients,
                    profile.side_camera_matrix,
                    profile.side_distortion_coefficients,
                    pair_ids=[item["pair_id"] for item in pairs],
                    total_pair_count=len(profile.corner_detections.get("stereo", [])),
                    projection_model=profile.camera_projection_models.get(
                        "top",
                        "brown_pinhole",
                    ),
                )
                payload = result.to_dict(include_corners=False)
                profile.rotation_matrix = payload["rotation_matrix"]
                profile.translation_vector = payload["translation_vector"]
                profile.essential_matrix = payload["essential_matrix"]
                profile.fundamental_matrix = payload["fundamental_matrix"]
                profile.top_projection_matrix = payload["top_projection_matrix"]
                profile.side_projection_matrix = payload["side_projection_matrix"]
                profile.top_rectification_rotation = payload[
                    "top_rectification_rotation"
                ]
                profile.side_rectification_rotation = payload[
                    "side_rectification_rotation"
                ]
                profile.disparity_to_depth_matrix = payload[
                    "disparity_to_depth_matrix"
                ]
                profile.top_valid_pixel_roi = payload["top_valid_pixel_roi"]
                profile.side_valid_pixel_roi = payload["side_valid_pixel_roi"]
                profile.stereo_mean_reprojection_error = result.rms_error
                profile.reprojection_error_per_image["stereo"] = list(
                    result.reprojection_error_per_pair
                )
                profile.point_coverage["stereo"] = result.point_coverage
                profile.potentially_invalid_reasons = self._stale_reasons(profile)
                profile.status = "stereo_solved"
                profile.valid = False
                profile.last_error = None
            except Exception as error:
                profile.status = "failed"
                profile.valid = False
                profile.last_error = str(error)
                self._persist(profile)
                if isinstance(error, CalibrationError):
                    raise
                raise CalibrationError(f"雙目相機校正失敗：{error}") from error
            return self._persist(profile)

    def solve_rotating(self, calibration_id: str) -> CalibrationProfile:
        with self._lock:
            profile = self.get_profile(calibration_id)
            self._ensure_not_referenced(calibration_id)
            profile.valid = False
            try:
                selected = profile.selected_images.get("rotating", [])
                if not selected:
                    raise CalibrationError("此校正沒有選擇環繞相機影像。")
                if (
                    profile.status not in {"stereo_solved", "rotating_solved"}
                    or profile.rotating_camera_matrix is None
                    or profile.rotating_distortion_coefficients is None
                    or profile.square_size_mm is None
                ):
                    raise CalibrationError(
                        "請先完成角點偵測、三相機內參與俯視加側視校正。"
                    )
                detections = self._successful_detections(profile, "rotating")
                if len({item.get("angle_deg") for item in detections}) < 3:
                    raise CalibrationError(
                        "環繞幾何校正至少需要三個不同角度的有效影像。"
                    )
                result = calibrate_rotating_rig_from_points(
                    detections,
                    camera_matrix=profile.rotating_camera_matrix,
                    distortion_coefficients=(
                        profile.rotating_distortion_coefficients
                    ),
                    pattern_size=profile.chessboard_pattern,
                    square_size_mm=profile.square_size_mm,
                    projection_model=profile.camera_projection_models.get(
                        "rotating",
                        "brown_pinhole",
                    ),
                )
                profile.rotating_axis_origin_mm = (
                    result.axis_origin_mm.astype(float).tolist()
                )
                profile.rotating_axis_direction = (
                    result.axis_direction.astype(float).tolist()
                )
                profile.rotating_zero_angle_deg = result.zero_angle_deg
                profile.rotating_angle_direction = result.angle_direction
                profile.rotating_axis_from_camera_matrix = (
                    result.world_from_camera_at_zero.astype(float).tolist()
                )
                profile.rotating_pose_residual_mean_px = result.residual_mean_px
                profile.rotating_pose_residual_max_px = result.residual_max_px
                profile.rotating_pose_samples = list(result.samples)
                profile.status = "rotating_solved"
                profile.valid = False
                profile.last_error = None
            except Exception as error:
                profile.status = "failed"
                profile.valid = False
                profile.last_error = str(error)
                self._persist(profile)
                if isinstance(error, CalibrationError):
                    raise
                raise CalibrationError(f"環繞相機幾何校正失敗：{error}") from error
            return self._persist(profile)

    @staticmethod
    def _validate_roi(
        roi: list[int] | None,
        *,
        name: str,
        image_size: tuple[int, int],
    ) -> None:
        if roi is None or len(roi) != 4:
            raise ValueError(f"{name} 必須包含 x、y、width、height。")
        x, y, width, height = (int(value) for value in roi)
        if min(x, y, width, height) < 0:
            raise ValueError(f"{name} 不得包含負數。")
        image_width, image_height = image_size
        if x + width > image_width or y + height > image_height:
            raise ValueError(f"{name} 超出影像範圍。")

    @staticmethod
    def _validate_error_values(profile: CalibrationProfile) -> None:
        means = [
            profile.top_mean_reprojection_error,
            profile.side_mean_reprojection_error,
            profile.stereo_mean_reprojection_error,
        ]
        groups = ["top", "side", "stereo"]
        if profile.selected_images.get("rotating"):
            means.append(profile.rotating_mean_reprojection_error)
            groups.append("rotating")
        if any(value is None for value in means):
            raise ValueError("校正平均重投影誤差不完整。")
        if any(not np.isfinite(value) or value < 0 for value in means):
            raise ValueError("校正平均重投影誤差包含無效數值。")
        for group in groups:
            items = profile.reprojection_error_per_image.get(group, [])
            if not items:
                raise ValueError(f"{group} 缺少逐影像重投影誤差。")
            for item in items:
                error_values = [
                    value
                    for key, value in item.items()
                    if key.endswith("error_px")
                ]
                if not error_values or any(
                    not np.isfinite(value) or value < 0
                    for value in error_values
                ):
                    raise ValueError(f"{group} 逐影像重投影誤差包含無效數值。")

    def _validate_profile_values(self, profile: CalibrationProfile) -> None:
        if profile.status not in {
            "stereo_solved",
            "rotating_solved",
            "valid",
            "potentially_invalid",
        }:
            raise ValueError("請先完成角點偵測、單目與雙目校正。")
        required = {
            "影像寬度": profile.image_width,
            "影像高度": profile.image_height,
            "單目棋盤內角點": profile.chessboard_pattern,
            "單目棋盤實測 square size": profile.square_size_mm,
            "雙目棋盤內角點": profile.stereo_chessboard_pattern,
            "雙目棋盤實測 square size": profile.stereo_square_size_mm,
            "俯視 Camera Matrix": profile.top_camera_matrix,
            "側視 Camera Matrix": profile.side_camera_matrix,
            "俯視畸變係數": profile.top_distortion_coefficients,
            "側視畸變係數": profile.side_distortion_coefficients,
            "R": profile.rotation_matrix,
            "t": profile.translation_vector,
            "E": profile.essential_matrix,
            "F": profile.fundamental_matrix,
            "R_top": profile.top_rectification_rotation,
            "R_side": profile.side_rectification_rotation,
            "P_top": profile.top_projection_matrix,
            "P_side": profile.side_projection_matrix,
            "Q": profile.disparity_to_depth_matrix,
            "世界座標轉換": profile.world_transform_matrix,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            raise ValueError(f"校正資料不完整：{', '.join(missing)}。")

        image_size = (int(profile.image_width), int(profile.image_height))
        if min(image_size) <= 0:
            raise ValueError("校正影像解析度必須大於 0。")

        def validate_camera_distortion(camera_id: str) -> None:
            coefficients = getattr(
                profile,
                f"{camera_id}_distortion_coefficients",
            )
            if profile.camera_projection_models.get(camera_id) == "fisheye":
                values = np.asarray(coefficients, dtype=np.float64).reshape(-1)
                if values.size != 4 or not np.isfinite(values).all():
                    raise ValueError(
                        f"{camera_id} Fisheye 畸變係數必須包含四個有效數值。"
                    )
                return
            validate_distortion_coefficients(
                coefficients,
                name=f"{camera_id}_distortion_coefficients",
            )

        validate_camera_matrix(profile.top_camera_matrix, name="top_camera_matrix")
        validate_camera_matrix(profile.side_camera_matrix, name="side_camera_matrix")
        validate_camera_distortion("top")
        validate_camera_distortion("side")
        if profile.selected_images.get("rotating"):
            if profile.status == "stereo_solved" or not profile.supports_rotating:
                raise ValueError("請先完成環繞相機旋轉軸與動態外參校正。")
            validate_camera_matrix(
                profile.rotating_camera_matrix,
                name="rotating_camera_matrix",
            )
            validate_camera_distortion("rotating")
            axis = validate_finite_matrix(
                profile.rotating_axis_direction,
                name="rotating_axis_direction",
            ).reshape(-1)
            if axis.size != 3 or not np.isclose(np.linalg.norm(axis), 1.0, atol=1e-5):
                raise ValueError("環繞旋轉軸方向必須是三維單位向量。")
            validate_finite_matrix(
                profile.rotating_axis_from_camera_matrix,
                name="rotating_axis_from_camera_matrix",
                shape=(4, 4),
            )
        rotation = validate_finite_matrix(
            profile.rotation_matrix,
            name="rotation_matrix",
            shape=(3, 3),
        )
        if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-6):
            raise ValueError("雙目旋轉矩陣不是正交矩陣。")
        if not np.isclose(np.linalg.det(rotation), 1.0, atol=1e-6):
            raise ValueError("雙目旋轉矩陣行列式必須為 1。")
        translation = validate_finite_matrix(
            profile.translation_vector,
            name="translation_vector",
        ).reshape(-1)
        if translation.size != 3 or np.linalg.norm(translation) <= 1e-9:
            raise ValueError("雙目平移向量必須是非零的三維向量。")
        for name, value, shape in (
            ("essential_matrix", profile.essential_matrix, (3, 3)),
            ("fundamental_matrix", profile.fundamental_matrix, (3, 3)),
            ("top_rectification_rotation", profile.top_rectification_rotation, (3, 3)),
            ("side_rectification_rotation", profile.side_rectification_rotation, (3, 3)),
            ("top_projection_matrix", profile.top_projection_matrix, (3, 4)),
            ("side_projection_matrix", profile.side_projection_matrix, (3, 4)),
            ("disparity_to_depth_matrix", profile.disparity_to_depth_matrix, (4, 4)),
        ):
            matrix = validate_finite_matrix(value, name=name, shape=shape)
            if name in {"essential_matrix", "fundamental_matrix"} and (
                np.linalg.norm(matrix) <= 1e-12
            ):
                raise ValueError(f"{name} 不得為零矩陣。")
        self._validate_roi(
            profile.top_valid_pixel_roi,
            name="top_valid_pixel_roi",
            image_size=image_size,
        )
        self._validate_roi(
            profile.side_valid_pixel_roi,
            name="side_valid_pixel_roi",
            image_size=image_size,
        )
        world_transform = validate_finite_matrix(
            profile.world_transform_matrix,
            name="world_transform_matrix",
            shape=(4, 4),
        )
        validate_rigid_transform(world_transform)
        self._validate_error_values(profile)
        groups = ["top", "side", "stereo"]
        if profile.selected_images.get("rotating"):
            groups.append("rotating")
        for group in groups:
            if not profile.point_coverage.get(group):
                raise ValueError(f"{group} 缺少校正點空間覆蓋紀錄。")

    def validate(self, calibration_id: str) -> CalibrationProfile:
        with self._lock:
            profile = self.get_profile(calibration_id)
            try:
                self._validate_profile_values(profile)
            except (TypeError, ValueError) as error:
                profile.status = "invalid"
                profile.valid = False
                profile.last_error = str(error)
                self._persist(profile)
                raise CalibrationError(str(error)) from error
            stale_reasons = self._stale_reasons(profile)
            profile.potentially_invalid_reasons = stale_reasons
            profile.valid = not stale_reasons
            profile.status = "valid" if profile.valid else "potentially_invalid"
            profile.last_error = None if profile.valid else "相機設定已變更，請重新校正。"
            return self._persist(profile)

    def report(self, calibration_id: str) -> CalibrationReport:
        profile = self.get_profile(calibration_id)
        detections = profile.corner_detections
        return CalibrationReport(
            profile=profile,
            image_count={
                "top": len(profile.selected_images.get("top", [])),
                "side": len(profile.selected_images.get("side", [])),
                "stereo": len(profile.selected_images.get("stereo", [])),
                "rotating": len(profile.selected_images.get("rotating", [])),
            },
            successful_corner_detections={
                "top": sum(item.get("found", False) for item in detections.get("top", [])),
                "side": sum(item.get("found", False) for item in detections.get("side", [])),
                "stereo": sum(item.get("usable", False) for item in detections.get("stereo", [])),
                "rotating": sum(
                    item.get("found", False)
                    for item in detections.get("rotating", [])
                ),
            },
            mean_reprojection_errors={
                "top": profile.top_mean_reprojection_error,
                "side": profile.side_mean_reprojection_error,
                "stereo": profile.stereo_mean_reprojection_error,
                "rotating": profile.rotating_mean_reprojection_error,
            },
            reprojection_error_per_image=profile.reprojection_error_per_image,
            point_coverage=profile.point_coverage,
            corner_detections=profile.corner_detections,
            valid=profile.valid,
            potentially_invalid_reasons=profile.potentially_invalid_reasons,
        )

    def delete(self, calibration_id: str) -> None:
        with self._lock:
            profile = self.get_profile(calibration_id)
            referenced = self.repository.database.fetchone(
                "SELECT 1 FROM analysis_runs WHERE calibration_id=? LIMIT 1",
                (calibration_id,),
            )
            if referenced:
                raise CalibrationError("相機校正設定檔已被分析引用，不能刪除。")
            directory = self._profile_dir(profile)
            tombstone = directory.with_name(
                f".{directory.name}.{uuid4().hex}.deleting"
            )
            try:
                if directory.exists():
                    directory.replace(tombstone)
                self.repository.delete(calibration_id)
            except Exception as error:
                if tombstone.exists():
                    tombstone.replace(directory)
                if isinstance(error, (sqlite3.IntegrityError, CalibrationError)):
                    raise CalibrationError(
                        "相機校正設定檔已被分析引用或不存在，不能刪除。"
                    ) from error
                raise CalibrationError("刪除相機校正設定檔失敗。") from error
            if tombstone.exists():
                try:
                    if tombstone.is_dir():
                        shutil.rmtree(tombstone)
                    else:
                        tombstone.unlink()
                except OSError:
                    logger.exception(
                        "Failed to remove deleted calibration directory: %s",
                        tombstone,
                    )
