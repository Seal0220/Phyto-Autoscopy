from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import cv2
import numpy as np

from app.analysis.run_metadata import utc_now_iso
from app.calibration.board_detection import detect_board
from app.calibration.board_generation import fixed_board_values
from app.core.exceptions import CalibrationError, CameraError
from app.models.analysis_models import (
    AnalysisCalibrationProfile,
    AnalysisWorldCoordinateSystem,
)
from app.models.calibration_models import (
    CalibrationBoardCreateRequest,
    CalibrationBoardProfile,
    CalibrationDetection,
    CalibrationLockRequest,
    ExtrinsicProfile,
    UnifiedCalibrationStatus,
)
CAMERA_IDS = ("top", "side", "rotating")


class CalibrationService:
    def __init__(
        self,
        settings: object,
        repository: object,
        camera_manager: object,
        motor_controller: object,
        snapshot_service: object,
        capture_service: object,
        intrinsic_service: object,
        extrinsic_service: object,
        validation_service: object,
        lock_service: object,
        storage_service: object,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.camera_manager = camera_manager
        self.motor_controller = motor_controller
        self.snapshot_service = snapshot_service
        self.capture_service = capture_service
        self.intrinsic_service = intrinsic_service
        self.extrinsic_service = extrinsic_service
        self.validation_service = validation_service
        self.lock_service = lock_service
        self.storage_service = storage_service
        self._detections: dict[str, CalibrationDetection] = {}
        self._calibration_engaged_motor = False
        self.storage_service.ensure_layout()
        self._ensure_default_board()
        try:
            self.storage_service.reconcile()
        except CalibrationError:
            # SQLite remains authoritative and the status endpoint exposes the
            # projection error so an operator can repair it without losing data.
            pass

    def _ensure_default_board(self) -> None:
        if self.repository.list_boards():
            return
        now = utc_now_iso()
        board = CalibrationBoardProfile(
            board_profile_id="default_charuco",
            created_at=now,
            updated_at=now,
            **fixed_board_values("a4", "landscape", 8, 6),
        )
        self.repository.create_board(board)
        try:
            self.storage_service.write_board(board)
        except CalibrationError:
            pass

    def on_lock_released(
        self,
        _previous_status: object,
        _reason: str,
    ) -> None:
        try:
            self.motor_controller.stop()
        except Exception:
            self.motor_controller.emergency_stop()
        if self._calibration_engaged_motor:
            try:
                self.motor_controller.disengage()
            finally:
                self._calibration_engaged_motor = False

    def list_boards(self) -> list[CalibrationBoardProfile]:
        return self.repository.list_boards()

    def get_board(self, board_profile_id: str) -> CalibrationBoardProfile:
        board = self.repository.get_board(board_profile_id)
        if board is None:
            raise CalibrationError("找不到指定的校正板設定。")
        return board

    def create_board(
        self,
        request: CalibrationBoardCreateRequest,
    ) -> CalibrationBoardProfile:
        existing = {item.board_profile_id for item in self.repository.list_boards()}
        prefix = "board"
        index = 1
        while f"{prefix}_{index:03d}" in existing:
            index += 1
        now = utc_now_iso()
        board = CalibrationBoardProfile(
            board_profile_id=f"{prefix}_{index:03d}",
            created_at=now,
            updated_at=now,
            **fixed_board_values(
                request.paper_size,
                request.paper_orientation,
                request.squares_x,
                request.squares_y,
            ),
        )
        self.storage_service.write_board(board)
        try:
            self.repository.create_board(board)
        except Exception:
            (
                self.settings.paths.calibration_dir
                / "boards"
                / f"{board.board_profile_id}.json"
            ).unlink(missing_ok=True)
            raise
        return board

    def status(self, owner: str | None = None) -> UnifiedCalibrationStatus:
        intrinsics = self.validation_service.intrinsics_status()
        active = self.extrinsic_service.get_active()
        motor = self.motor_controller.status()
        lock = self.lock_service.status()
        latest_values = [item.updated_at for item in intrinsics]
        if active is not None:
            latest_values.append(active.updated_at)
        calibration_errors = [
            (item.updated_at, item.last_error)
            for camera_id in CAMERA_IDS
            for item in self.repository.list_intrinsic_runs(camera_id)
            if item.last_error
        ]
        calibration_errors.extend(
            (item.updated_at, item.last_error)
            for item in self.extrinsic_service.list_profiles()
            if item.last_error
        )
        latest_calibration_error = max(
            calibration_errors,
            key=lambda item: item[0],
            default=(None, None),
        )[1]
        recent_error = next(
            (
                item
                for item in [
                    latest_calibration_error,
                    self.storage_service.last_error,
                    active.last_error if active else None,
                    motor.last_error,
                    *(status.last_error for status in self.camera_manager.get_statuses()),
                ]
                if item
            ),
            None,
        )
        return UnifiedCalibrationStatus(
            lock=lock,
            lock_owned_by_requester=bool(
                owner and lock.locked and lock.owner == owner
            ),
            cameras=[
                item.model_dump(mode="json")
                for item in self.camera_manager.get_statuses()
            ],
            intrinsics=intrinsics,
            active_extrinsic=active,
            motor=motor.model_dump(mode="json"),
            arm_height_mm=(active.motion_model.arm_height_mm if active else None),
            motor_angle_deg=motor.command_position_deg,
            detections=dict(self._detections),
            latest_calibration_at=max(latest_values) if latest_values else None,
            recent_error=recent_error,
            storage_synchronized=self.storage_service.synchronized,
            storage_error=self.storage_service.last_error,
        )

    def reconcile_storage(self, owner: str) -> UnifiedCalibrationStatus:
        self.lock_service.ensure_owner(owner)
        self.storage_service.reconcile()
        return self.status(owner)

    def detect(
        self,
        camera_id: str,
        board_profile_id: str,
        owner: str,
    ) -> CalibrationDetection:
        self.lock_service.ensure_owner(owner)
        board = self.repository.get_board(board_profile_id)
        if board is None:
            raise CalibrationError(f"找不到校正板：{board_profile_id}")
        status = self.camera_manager.get_status(camera_id)
        if not status.enabled or not status.connected:
            detection = CalibrationDetection(
                camera_id=camera_id,
                captured_at=utc_now_iso(),
                connected=status.connected,
                enabled=status.enabled,
                board_detected=False,
                warnings=[f"相機 {camera_id} 尚未連線，請先重新連線。"],
            )
        else:
            frame, result = self.capture_service.analyze_camera(camera_id, board)
            detection = CalibrationDetection(
                camera_id=camera_id,
                captured_at=self.capture_service.timestamp(frame),
                connected=True,
                enabled=True,
                board_detected=result.board_detected,
                marker_count=result.marker_count,
                corner_count=result.corner_count,
                capture_ready=result.capture_ready,
                sharpness=result.sharpness,
                mean_brightness=result.mean_brightness,
                overexposed_ratio=result.overexposed_ratio,
                underexposed_ratio=result.underexposed_ratio,
                warnings=list(result.warnings),
            )
        self._detections[camera_id] = detection
        return detection

    @staticmethod
    def _mjpeg_frame(data: bytes) -> bytes:
        return (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n"
            + data
            + b"\r\n"
        )

    def _remember_detection(
        self,
        camera_id: str,
        captured_at: str,
        result: object,
    ) -> None:
        self._detections[camera_id] = CalibrationDetection(
            camera_id=camera_id,
            captured_at=captured_at,
            connected=True,
            enabled=True,
            board_detected=result.board_detected,
            marker_count=result.marker_count,
            corner_count=result.corner_count,
            capture_ready=result.capture_ready,
            sharpness=result.sharpness,
            mean_brightness=result.mean_brightness,
            overexposed_ratio=result.overexposed_ratio,
            underexposed_ratio=result.underexposed_ratio,
            warnings=list(result.warnings),
        )

    async def calibration_mjpeg_stream(
        self,
        camera_id: str,
        board_profile_id: str,
        first_frame: object,
        first_sequence: int,
        frame_undistorter: object | None = None,
    ) -> AsyncIterator[bytes]:
        board = self.repository.get_board(board_profile_id)
        if board is None:
            raise CalibrationError(f"找不到校正板：{board_profile_id}")
        frame = first_frame
        sequence = first_sequence
        begin_preview = getattr(self.camera_manager, "begin_preview", None)
        end_preview = getattr(self.camera_manager, "end_preview", None)
        if begin_preview is not None:
            begin_preview(camera_id)
        consecutive_errors = 0
        try:
            while True:
                status = self.camera_manager.get_status(camera_id)
                if not status.enabled:
                    return
                try:
                    result = await asyncio.to_thread(
                        detect_board,
                        frame.data,
                        board,
                        include_preview=True,
                    )
                    self._remember_detection(
                        camera_id,
                        self.capture_service.timestamp(frame),
                        result,
                    )
                    frame_data = result.preview_jpeg or frame.data
                    if frame_undistorter is not None:
                        frame_data = await asyncio.to_thread(
                            frame_undistorter.apply,
                            frame_data,
                        )
                    yield self._mjpeg_frame(frame_data)
                    frame, sequence = await asyncio.to_thread(
                        self.camera_manager.wait_for_frame,
                        camera_id,
                        after_sequence=sequence,
                        timeout=3.0,
                    )
                except CameraError as error:
                    consecutive_errors += 1
                    self._detections[camera_id] = CalibrationDetection(
                        camera_id=camera_id,
                        captured_at=utc_now_iso(),
                        connected=False,
                        enabled=status.enabled,
                        warnings=[
                            f"相機 {camera_id} 串流暫時中斷：{error}。系統正在等待重新連線。"
                        ],
                    )
                    if consecutive_errors >= 10:
                        return
                    await asyncio.sleep(min(3.0, 0.4 * consecutive_errors))
                    try:
                        frame, sequence = await asyncio.to_thread(
                            self.camera_manager.wait_for_frame,
                            camera_id,
                            after_sequence=sequence,
                            timeout=3.0,
                        )
                    except CameraError:
                        continue
                else:
                    consecutive_errors = 0
        finally:
            if end_preview is not None:
                end_preview(camera_id)

    def reconnect_camera(
        self,
        camera_id: str,
        owner: str,
    ):
        self.lock_service.ensure_owner(owner)
        return self.camera_manager.reconnect(camera_id)

    def snapshot_camera(
        self,
        camera_id: str,
        owner: str,
    ):
        self.lock_service.ensure_owner(owner)
        return self.snapshot_service.snapshot_camera(camera_id)

    def move_motor(
        self,
        angle_deg: float,
        owner: str,
    ):
        self.lock_service.ensure_owner(owner)
        return self.motor_controller.move_to_angle(angle_deg)

    def engage_motor(self, owner: str):
        self.lock_service.ensure_owner(owner)
        status = self.motor_controller.engage()
        self._calibration_engaged_motor = True
        return status

    def disengage_motor(self, owner: str):
        self.lock_service.ensure_owner(owner)
        status = self.motor_controller.disengage()
        self._calibration_engaged_motor = False
        return status

    def return_motor_origin(self, owner: str):
        self.lock_service.ensure_owner(owner)
        return self.motor_controller.return_origin()

    def set_motor_origin(self, owner: str):
        self.lock_service.ensure_owner(owner)
        return self.motor_controller.set_origin()

    def stop_motor(self, owner: str):
        self.lock_service.ensure_owner(owner)
        return self.motor_controller.stop()

    def emergency_stop(self):
        return self.motor_controller.emergency_stop()

    @staticmethod
    def _projection_model(value: str) -> str:
        return "fisheye" if value == "opencv_fisheye" else "brown_pinhole"

    @staticmethod
    def _top_side_geometry(
        top: object,
        side: object,
        rig_from_top: np.ndarray,
        rig_from_side: np.ndarray,
    ) -> dict:
        side_from_top = np.linalg.inv(rig_from_side) @ rig_from_top
        rotation = side_from_top[:3, :3]
        translation = side_from_top[:3, 3]
        translation_column = translation.reshape(3, 1)
        if np.linalg.norm(translation) <= 1e-9:
            raise CalibrationError("俯視角與側視角外參基線為零，無法供分析使用。")

        top_matrix = np.asarray(top.camera_matrix, dtype=np.float64)
        side_matrix = np.asarray(side.camera_matrix, dtype=np.float64)
        canonical_size = (int(top.width), int(top.height))
        side_matrix_for_rectification = side_matrix.copy()
        side_matrix_for_rectification[0, :] *= top.width / float(side.width)
        side_matrix_for_rectification[1, :] *= top.height / float(side.height)
        side_matrix_for_rectification[2, :] = [0.0, 0.0, 1.0]

        try:
            (
                top_rectification,
                side_rectification,
                top_projection,
                side_projection,
                disparity_to_depth,
                top_roi,
                side_roi,
            ) = cv2.stereoRectify(
                top_matrix,
                np.zeros(5, dtype=np.float64),
                side_matrix_for_rectification,
                np.zeros(5, dtype=np.float64),
                canonical_size,
                rotation,
                translation_column,
                flags=cv2.CALIB_ZERO_DISPARITY,
                alpha=0,
            )
        except cv2.error as error:
            raise CalibrationError(
                f"俯視角與側視角的分析幾何計算失敗：{error}"
            ) from error

        translation_cross = np.asarray(
            [
                [0.0, -translation[2], translation[1]],
                [translation[2], 0.0, -translation[0]],
                [-translation[1], translation[0], 0.0],
            ],
            dtype=np.float64,
        )
        essential = translation_cross @ rotation
        fundamental = (
            np.linalg.inv(side_matrix).T
            @ essential
            @ np.linalg.inv(top_matrix)
        )
        norm = np.linalg.norm(fundamental)
        if norm <= 1e-12 or not np.isfinite(fundamental).all():
            raise CalibrationError("俯視角與側視角的 Fundamental Matrix 無效。")
        fundamental /= norm
        return {
            "rotation_matrix": rotation.astype(float).tolist(),
            "translation_vector": translation.astype(float).tolist(),
            "essential_matrix": essential.astype(float).tolist(),
            "fundamental_matrix": fundamental.astype(float).tolist(),
            "top_projection_matrix": top_projection.astype(float).tolist(),
            "side_projection_matrix": side_projection.astype(float).tolist(),
            "top_rectification_rotation": top_rectification.astype(float).tolist(),
            "side_rectification_rotation": side_rectification.astype(float).tolist(),
            "disparity_to_depth_matrix": disparity_to_depth.astype(float).tolist(),
            "top_valid_pixel_roi": [int(value) for value in top_roi],
            "side_valid_pixel_roi": [int(value) for value in side_roi],
        }

    def _analysis_adapter(
        self,
        profile: ExtrinsicProfile,
    ) -> AnalysisCalibrationProfile:
        intrinsics = {
            camera_id: self.repository.get_intrinsics(camera_id)
            for camera_id in profile.camera_ids
        }
        missing = [camera_id for camera_id, value in intrinsics.items() if value is None]
        if missing:
            raise CalibrationError(
                f"外參校正檔缺少相機內參：{', '.join(missing)}"
            )
        invalid = [
            camera_id
            for camera_id, value in intrinsics.items()
            if value.status != "valid"
        ]
        if invalid:
            raise CalibrationError(
                f"外參校正檔使用的相機內參可能已失效：{', '.join(invalid)}"
            )
        cameras = {camera.camera_id: camera for camera in profile.cameras}
        top = intrinsics.get("top")
        side = intrinsics.get("side")
        top_camera = cameras.get("top")
        side_camera = cameras.get("side")
        geometry = {}
        if top and side and top_camera and side_camera:
            rig_from_top = np.asarray(top_camera.transform_rig_from_camera, dtype=np.float64)
            rig_from_side = np.asarray(side_camera.transform_rig_from_camera, dtype=np.float64)
            geometry = self._top_side_geometry(
                top,
                side,
                rig_from_top,
                rig_from_side,
            )
        image_sizes = {
            camera_id: [value.width, value.height]
            for camera_id, value in intrinsics.items()
            if value is not None
        }
        world_matrix = profile.world_alignment.transform_world_from_rig
        if top_camera and top_camera.transform_rig_from_camera and world_matrix:
            world_matrix = (
                np.asarray(world_matrix) @ np.asarray(top_camera.transform_rig_from_camera)
            ).astype(float).tolist()
        return AnalysisCalibrationProfile(
            calibration_id=profile.profile_id,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
            status=profile.status,
            valid=profile.status in {"valid", "active"},
            output_path=(self.settings.paths.calibration_dir / "extrinsics" / profile.profile_id).as_posix(),
            top_camera_identifier="top",
            side_camera_identifier="side",
            rotating_camera_identifier="rotating",
            image_width=top.width if top else None,
            image_height=top.height if top else None,
            camera_projection_models={
                camera_id: self._projection_model(value.camera_model)
                for camera_id, value in intrinsics.items()
                if value is not None
            },
            camera_image_sizes=image_sizes,
            top_camera_matrix=top.camera_matrix if top else None,
            top_distortion_coefficients=top.distortion_coefficients if top else None,
            side_camera_matrix=side.camera_matrix if side else None,
            side_distortion_coefficients=side.distortion_coefficients if side else None,
            rotating_camera_matrix=(
                intrinsics["rotating"].camera_matrix
                if intrinsics.get("rotating") else None
            ),
            rotating_distortion_coefficients=(
                intrinsics["rotating"].distortion_coefficients
                if intrinsics.get("rotating") else None
            ),
            **geometry,
            world_transform_matrix=world_matrix,
            world_coordinate_system=AnalysisWorldCoordinateSystem(
                origin="植物平台中心",
                x_axis=profile.world_alignment.x_axis_definition,
                y_axis=profile.world_alignment.y_axis_definition,
                z_axis=profile.world_alignment.z_axis_definition,
            ),
            rotating_axis_origin_mm=profile.motion_model.rotation_axis_origin_mm,
            rotating_axis_direction=profile.motion_model.rotation_axis_direction,
            rotating_zero_angle_deg=(
                -profile.motion_model.motor_zero_offset_deg
                if profile.motion_model.motor_zero_offset_deg is not None else None
            ),
            rotating_angle_direction=(
                1 if profile.motion_model.rotation_axis_direction else None
            ),
            rotating_axis_from_camera_matrix=profile.motion_model.mount_transform_from_camera,
            rotating_pose_residual_mean_px=profile.quality.get("rotation_axis_fit_error_mm"),
            rotating_pose_residual_max_px=profile.quality.get("rotation_axis_fit_error_mm"),
            rotating_pose_samples=profile.quality.get("rotation_samples", []),
            notes=profile.notes,
            last_error=profile.last_error,
        )

    def list_profiles(self) -> list[AnalysisCalibrationProfile]:
        active = self.extrinsic_service.get_active()
        return [self._analysis_adapter(active)] if active is not None else []

    def analysis_profile(
        self,
        profile: ExtrinsicProfile,
    ) -> AnalysisCalibrationProfile:
        return self._analysis_adapter(profile)

    def get_profile(self, profile_id: str) -> AnalysisCalibrationProfile:
        active = self.extrinsic_service.get_active()
        if active is None or active.profile_id != profile_id:
            raise CalibrationError("分析只能使用目前啟用的外參校正檔。")
        return self._analysis_adapter(active)

    def close(self) -> None:
        self.lock_service.close()
