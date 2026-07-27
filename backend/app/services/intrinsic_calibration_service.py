from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil
from threading import RLock

import cv2
import numpy as np

from app.analysis.run_metadata import next_dated_identifier, utc_now_iso
from app.calibration.camera_models import OpenCVCompatibilityError
from app.calibration.intrinsic_solver import solve_intrinsic_run
from app.calibration.quality_metrics import is_duplicate_pose, sample_coverage
from app.core.exceptions import CalibrationError
from app.models.calibration_models import (
    CameraIntrinsics,
    IntrinsicRun,
    IntrinsicRunCreateRequest,
    IntrinsicSample,
)


class IntrinsicCalibrationService:
    def __init__(
        self,
        settings: object,
        repository: object,
        capture_service: object,
        lock_service: object,
        storage_service: object,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.capture_service = capture_service
        self.lock_service = lock_service
        self.storage_service = storage_service
        self._run_state_lock = RLock()

    @property
    def root(self) -> Path:
        return self.settings.paths.calibration_dir / "intrinsics"

    def list_intrinsics(self) -> list[CameraIntrinsics]:
        return self.repository.list_intrinsics()

    def get_intrinsics(self, camera_id: str) -> CameraIntrinsics:
        intrinsics = self.repository.get_intrinsics(camera_id)
        if intrinsics is None:
            raise CalibrationError(f"相機 {camera_id} 尚未建立內參。")
        return intrinsics

    def get_run(self, run_id: str) -> IntrinsicRun:
        run = self.repository.get_intrinsic_run(run_id)
        if run is None:
            raise CalibrationError(f"找不到內參校正工作：{run_id}")
        return run

    def list_runs(self, camera_id: str) -> list[IntrinsicRun]:
        if camera_id not in self.settings.cameras:
            raise CalibrationError(f"找不到相機：{camera_id}")
        return self.repository.list_intrinsic_runs(camera_id)

    def create_run(
        self,
        camera_id: str,
        request: IntrinsicRunCreateRequest,
        owner: str,
    ) -> IntrinsicRun:
        self.lock_service.ensure_owner(owner)
        if camera_id not in self.settings.cameras:
            raise CalibrationError(f"找不到相機：{camera_id}")
        camera = self.settings.cameras[camera_id]
        if not camera.enabled:
            raise CalibrationError(f"相機 {camera_id} 尚未啟用，無法開始內參校正。")
        if self.repository.get_board(request.board_profile_id) is None:
            raise CalibrationError(f"找不到校正板：{request.board_profile_id}")
        run_id = next_dated_identifier(self.root / "runs", f"intrinsic_{camera_id}")
        now = utc_now_iso()
        run = IntrinsicRun(
            run_id=run_id,
            camera_id=camera_id,
            board_profile_id=request.board_profile_id,
            capture_mode=request.capture_mode,
            requested_camera_model=request.camera_model,
            minimum_interval_seconds=request.minimum_interval_seconds,
            created_at=now,
            updated_at=now,
        )
        directory = self.root / "runs" / run_id
        directory.mkdir(parents=True, exist_ok=False)
        try:
            self._write_run(run)
            self.repository.create_intrinsic_run(run)
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise
        return run

    def _write_run(self, run: IntrinsicRun) -> None:
        self.storage_service.write_intrinsic_run(run)

    def _persist_run(
        self,
        previous: IntrinsicRun,
        updated: IntrinsicRun,
    ) -> None:
        self._write_run(updated)
        try:
            self.repository.update_intrinsic_run(updated)
        except Exception:
            self._write_run(previous)
            raise

    def _delete_sample_files(
        self,
        run_id: str,
        sample_id: str,
    ) -> None:
        directory = self.root / "runs" / run_id
        for path in (
            directory / "captures" / f"{sample_id}.jpg",
            directory / "previews" / f"{sample_id}.jpg",
        ):
            path.unlink(missing_ok=True)

    @staticmethod
    def _last_accepted_at(run: IntrinsicRun) -> datetime | None:
        accepted = [sample for sample in run.samples if sample.accepted]
        if not accepted:
            return None
        try:
            return datetime.fromisoformat(accepted[-1].captured_at)
        except ValueError:
            return None

    def capture(
        self,
        camera_id: str,
        run_id: str,
        owner: str,
    ) -> IntrinsicRun:
        self.lock_service.ensure_owner(owner)
        run = self.get_run(run_id)
        if run.camera_id != camera_id:
            raise CalibrationError(f"內參工作 {run_id} 不屬於相機 {camera_id}。")
        if run.status not in {"capturing", "ready", "failed"}:
            raise CalibrationError("目前內參校正工作狀態不可擷取新樣本。")
        board = self.repository.get_board(run.board_profile_id)
        if board is None:
            raise CalibrationError(f"找不到校正板：{run.board_profile_id}")
        frame, detection = self.capture_service.analyze_camera(
            camera_id,
            board,
            include_preview=True,
        )
        sample_id = f"sample_{len(run.samples) + 1:04d}"
        rejection_reason = None
        if not detection.capture_ready:
            rejection_reason = detection.warnings[0] if detection.warnings else "目前影像不符合擷取條件。"
        if rejection_reason is None and run.capture_mode == "automatic":
            previous_at = self._last_accepted_at(run)
            if previous_at is not None:
                elapsed = (
                    frame.timestamp.astimezone(timezone.utc)
                    - previous_at.astimezone(timezone.utc)
                ).total_seconds()
                if elapsed < run.minimum_interval_seconds:
                    rejection_reason = "尚未達到自動擷取的最小時間間隔。"
            if rejection_reason is None and is_duplicate_pose(
                detection.pose_signature,
                [sample.pose_signature for sample in run.samples if sample.accepted],
            ):
                rejection_reason = "目前校正板姿態與既有樣本過於相近，已略過重複樣本。"
        accepted = rejection_reason is None
        image_path = ""
        if accepted:
            image_path, _ = self.capture_service.save_intrinsic_frame(
                run_id,
                sample_id,
                frame,
                detection.preview_jpeg,
            )
        sample = IntrinsicSample(
            sample_id=sample_id,
            camera_id=camera_id,
            captured_at=self.capture_service.timestamp(frame),
            image_path=image_path,
            accepted=accepted,
            rejection_reason=rejection_reason,
            resolution=list(detection.image_size),
            marker_count=detection.marker_count,
            corner_count=detection.corner_count,
            sharpness=detection.sharpness,
            mean_brightness=detection.mean_brightness,
            overexposed_ratio=detection.overexposed_ratio,
            underexposed_ratio=detection.underexposed_ratio,
            board_center=list(detection.board_center) if detection.board_center else None,
            board_scale=detection.board_scale,
            pose_signature=list(detection.pose_signature) if detection.pose_signature else None,
            object_points=detection.object_points.astype(float).tolist(),
            image_points=detection.image_points.astype(float).tolist(),
        )
        samples = [*run.samples, sample]
        coverage = sample_coverage(samples)
        updated = run.model_copy(
            update={
                "samples": samples,
                "coverage": coverage,
                "status": "ready" if coverage["ready"] else "capturing",
                "updated_at": utc_now_iso(),
                "last_error": rejection_reason if not accepted else None,
            },
            deep=True,
        )
        try:
            with self._run_state_lock:
                self.lock_service.ensure_owner(owner)
                current = self.get_run(run_id)
                if current.status == "cancelled":
                    raise CalibrationError("內參校正已停止。")
                self._persist_run(current, updated)
        except Exception:
            if accepted:
                self._delete_sample_files(run_id, sample_id)
            raise
        return updated

    def solve(
        self,
        camera_id: str,
        run_id: str,
        owner: str,
    ) -> IntrinsicRun:
        self.lock_service.ensure_owner(owner)
        run = self.get_run(run_id)
        if run.camera_id != camera_id:
            raise CalibrationError(f"內參工作 {run_id} 不屬於相機 {camera_id}。")
        solving = run.model_copy(
            update={
                "status": "solving",
                "updated_at": utc_now_iso(),
                "last_error": None,
            },
            deep=True,
        )
        self._persist_run(run, solving)
        try:
            candidates, selected = solve_intrinsic_run(solving)
        except Exception as error:
            detail = str(error) or "內參求解未收斂。"
            failed = solving.model_copy(
                update={
                    "status": "failed",
                    "updated_at": utc_now_iso(),
                    "last_error": detail,
                },
                deep=True,
            )
            self._persist_run(solving, failed)
            if isinstance(error, (OpenCVCompatibilityError, AttributeError)):
                raise CalibrationError(
                    f"相機 {camera_id} 內參計算失敗：OpenCV 校正模組不相容。"
                    "請重新執行 start.bat --setup 後再試。"
                ) from error
            raise CalibrationError(
                f"相機 {camera_id} 內參計算失敗：{detail} "
                "請補拍不同位置的清晰樣本後重試。"
            ) from error
        try:
            self.lock_service.ensure_owner(owner)
        except CalibrationError as error:
            cancelled = solving.model_copy(
                update={
                    "status": "cancelled",
                    "updated_at": utc_now_iso(),
                    "last_error": "校正操作鎖已釋放，內參計算結果未套用。",
                },
                deep=True,
            )
            self._persist_run(solving, cancelled)
            raise error
        solved = solving.model_copy(
            update={
                "status": "solved",
                "candidate_results": candidates,
                "selected_result": selected,
                "updated_at": utc_now_iso(),
                "last_error": None,
            },
            deep=True,
        )
        self._persist_run(solving, solved)
        return solved

    def _write_undistorted_preview(
        self,
        run: IntrinsicRun,
        result: dict,
    ) -> str | None:
        sample = next((item for item in reversed(run.samples) if item.accepted and item.image_path), None)
        if sample is None:
            return None
        image = cv2.imread(sample.image_path, cv2.IMREAD_COLOR)
        if image is None:
            return None
        matrix = np.asarray(result["camera_matrix"], dtype=np.float64)
        distortion = np.asarray(result["distortion_coefficients"], dtype=np.float64)
        if result["camera_model"] == "opencv_fisheye":
            size = (image.shape[1], image.shape[0])
            maps = cv2.fisheye.initUndistortRectifyMap(
                matrix,
                distortion,
                np.eye(3),
                matrix,
                size,
                cv2.CV_16SC2,
            )
            undistorted = cv2.remap(image, maps[0], maps[1], cv2.INTER_LINEAR)
        else:
            undistorted = cv2.undistort(image, matrix, distortion)
        path = (
            self.root
            / "previews"
            / f"{run.camera_id}_{run.run_id}_undistorted.jpg"
        )
        encoded, payload = cv2.imencode(".jpg", undistorted, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not encoded:
            return None
        self.capture_service.storage_service.save_bytes(path, payload.tobytes())
        return path.as_posix()

    def apply(
        self,
        camera_id: str,
        run_id: str,
        owner: str,
    ) -> CameraIntrinsics:
        self.lock_service.ensure_owner(owner)
        run = self.get_run(run_id)
        result = run.selected_result
        if run.camera_id != camera_id or run.status != "solved" or not result:
            raise CalibrationError("只有已完成計算且屬於該相機的內參工作可以套用。")
        if result.get("quality_status") == "failed":
            raise CalibrationError("內參品質未達最低門檻，請補拍樣本後重新計算。")
        now = utc_now_iso()
        preview_path = self._write_undistorted_preview(run, result)
        self.lock_service.ensure_owner(owner)
        quality = {
            "coverage": result["coverage"],
            "per_image_errors": result["per_image_errors"],
            "candidate_models": run.candidate_results,
            "undistorted_preview_path": preview_path,
        }
        intrinsics = CameraIntrinsics(
            camera_id=camera_id,
            camera_model=result["camera_model"],
            width=int(result["width"]),
            height=int(result["height"]),
            camera_matrix=result["camera_matrix"],
            distortion_coefficients=result["distortion_coefficients"],
            reprojection_error_px=float(result["reprojection_error_px"]),
            median_reprojection_error_px=float(result["median_reprojection_error_px"]),
            maximum_reprojection_error_px=float(result["maximum_reprojection_error_px"]),
            validation_error_px=float(result["validation_error_px"]),
            sample_count=int(result["sample_count"]),
            board_profile_id=run.board_profile_id,
            quality_status=result["quality_status"],
            quality=quality,
            source_run_id=run.run_id,
            created_at=now,
            updated_at=now,
            status="valid",
        )
        applied = run.model_copy(
            update={
                "status": "applied",
                "updated_at": now,
                "last_error": None,
            },
            deep=True,
        )
        previous_intrinsics = self.repository.get_intrinsics(camera_id)
        current_intrinsics = [
            item
            for item in self.repository.list_intrinsics()
            if item.camera_id != camera_id
        ]
        next_intrinsics = [*current_intrinsics, intrinsics]
        try:
            self.storage_service.write_intrinsics(intrinsics)
            self._write_run(applied)
            self.storage_service.write_index(
                intrinsics=next_intrinsics,
            )
            self.repository.apply_intrinsics(intrinsics, applied)
        except Exception:
            try:
                if previous_intrinsics is None:
                    (self.root / f"{camera_id}.json").unlink(missing_ok=True)
                else:
                    self.storage_service.write_intrinsics(previous_intrinsics)
                self._write_run(run)
                self.storage_service.write_index()
            finally:
                if preview_path:
                    Path(preview_path).unlink(missing_ok=True)
            raise
        return intrinsics

    def cancel_run(
        self,
        camera_id: str,
        run_id: str,
        owner: str,
    ) -> IntrinsicRun | None:
        with self._run_state_lock:
            run = self.repository.get_intrinsic_run(run_id)
            if run is None:
                return None
            if run.camera_id != camera_id:
                raise CalibrationError(
                    f"內參工作 {run_id} 不屬於相機 {camera_id}。"
                )

            if run.status == "cancelled":
                lock_status = self.lock_service.status()
                if lock_status.locked and lock_status.owner == owner:
                    self.lock_service.release(owner)
                return run

            lock_status = self.lock_service.status()
            if lock_status.locked and lock_status.owner != owner:
                raise CalibrationError("目前校正操作鎖屬於其他操作人員。")
            cancelled = run.model_copy(
                update={
                    "status": "cancelled",
                    "updated_at": utc_now_iso(),
                    "last_error": None,
                },
                deep=True,
            )
            self._persist_run(run, cancelled)
            if lock_status.locked:
                self.lock_service.release(owner)
            return cancelled
