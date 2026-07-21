from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from app.analysis.run_metadata import utc_now_iso
from app.calibration.board_detection import detect_board
from app.calibration.board_generation import fixed_board_values
from app.core.exceptions import CalibrationError, CameraError
from app.models.calibration_models import (
    CalibrationBoardCreateRequest,
    CalibrationBoardProfile,
    CalibrationDetection,
    CalibrationLockRequest,
    UnifiedCalibrationStatus,
)
CAMERA_IDS = ("top", "side", "rotating")


class CalibrationService:
    def __init__(
        self,
        settings: object,
        repository: object,
        camera_manager: object,
        snapshot_service: object,
        capture_service: object,
        intrinsic_service: object,
        validation_service: object,
        lock_service: object,
        storage_service: object,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.camera_manager = camera_manager
        self.snapshot_service = snapshot_service
        self.capture_service = capture_service
        self.intrinsic_service = intrinsic_service
        self.validation_service = validation_service
        self.lock_service = lock_service
        self.storage_service = storage_service
        self._detections: dict[str, CalibrationDetection] = {}
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
        return None

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
        lock = self.lock_service.status()
        latest_values = [item.updated_at for item in intrinsics]
        calibration_errors = [
            (item.updated_at, item.last_error)
            for camera_id in CAMERA_IDS
            for item in self.repository.list_intrinsic_runs(camera_id)
            if item.last_error
        ]
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

    def close(self) -> None:
        self.lock_service.close()
