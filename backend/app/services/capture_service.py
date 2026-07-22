from __future__ import annotations

from datetime import datetime

from app.core.config import AppSettings
from app.core.exceptions import CameraError, public_error_detail
from app.models.camera_models import CaptureResult
from app.models.capture_models import MetadataRecord
from app.services.metadata_service import MetadataService
from app.services.record_service import RecordService
from app.services.storage_service import StorageService


class CaptureService:
    def __init__(
        self,
        settings: AppSettings,
        camera_manager,
        motor_controller,
        storage: StorageService,
        metadata: MetadataService,
        records: RecordService,
    ) -> None:
        self.settings = settings
        self.camera_manager = camera_manager
        self.motor_controller = motor_controller
        self.storage = storage
        self.metadata = metadata
        self.records = records

    def capture_camera(
        self,
        camera_id: str,
        record_id: str | None = None,
        cycle_id: int | None = None,
        angle_deg: float | None = None,
        mode_folder: str | None = None,
        capture_index: int | None = None,
        continuous: bool = False,
    ) -> CaptureResult:
        record = self.records.get_capture_record(record_id)
        frame = self.camera_manager.capture(camera_id)
        status = self.camera_manager.get_status(camera_id)
        motor_status = self.motor_controller.status()
        if mode_folder is not None:
            path = self.storage.next_mode_capture_path(
                record.record_id,
                mode_folder,
                camera_id,
                cycle_id or 1,
                capture_index or 1,
                0.0 if angle_deg is None else angle_deg,
                frame.timestamp,
                continuous,
                record.record_path,
            )
        else:
            path = self.storage.next_capture_path(
                record.record_id,
                camera_id,
                cycle_id,
                angle_deg,
                record.record_path,
            )
        self.storage.save_bytes(path, frame.data)
        relative_path = self.storage.relative_to_record(
            record.record_id,
            path,
            record.record_path,
        )

        metadata_record = MetadataRecord(
            project_name=self.settings.project.name,
            project_name_zh=self.settings.project.name_zh,
            device_name=self.settings.project.device_name,
            record_id=record.record_id,
            cycle_id=cycle_id,
            camera_id=camera_id,
            camera_name=status.camera_name,
            timestamp=frame.timestamp.isoformat(),
            angle_deg=angle_deg,
            motor_position_deg=motor_status.command_position_deg,
            file_path=relative_path,
            status="success",
        )
        try:
            self.metadata.append(metadata_record, record.record_path)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return CaptureResult(**metadata_record.model_dump())

    def capture_all(self, record_id: str | None = None) -> list[CaptureResult]:
        camera_ids = [
            status.camera_id
            for status in self.camera_manager.get_statuses()
            if status.enabled
        ]
        if not camera_ids:
            raise CameraError("目前沒有已啟用的相機可供擷取。")
        results: list[CaptureResult] = []
        failures: list[str] = []
        for camera_id in camera_ids:
            try:
                results.append(
                    self.capture_camera(camera_id, record_id=record_id)
                )
            except Exception as exc:
                failures.append(f"{camera_id}（{public_error_detail(exc)}）")
        if failures:
            raise CameraError(
                f"擷取全部未完整完成；成功 {len(results)} 台，"
                f"失敗 {len(failures)} 台：{', '.join(failures)}"
            )
        return results

    def capture_camera_for_modes(
        self,
        camera_id: str,
        record_id: str,
        cycle_id: int,
        angle_deg: float,
        mode_outputs: list[tuple[str, int, bool]],
        snapshot_at: datetime,
    ) -> dict[str, CaptureResult]:
        """Capture one physical frame and persist a copy for every due schedule mode."""
        record = self.records.get_capture_record(record_id)
        frame = self.camera_manager.capture(camera_id)
        status = self.camera_manager.get_status(camera_id)
        motor_status = self.motor_controller.status()
        results: dict[str, CaptureResult] = {}

        for mode_folder, capture_index, continuous in mode_outputs:
            mode_cycle_id = 0 if continuous else cycle_id
            path = self.storage.next_mode_capture_path(
                record.record_id,
                mode_folder,
                camera_id,
                mode_cycle_id,
                capture_index,
                angle_deg,
                snapshot_at,
                continuous,
                record.record_path,
            )
            self.storage.save_bytes(path, frame.data)
            relative_path = self.storage.relative_to_record(
                record.record_id,
                path,
                record.record_path,
            )
            metadata_record = MetadataRecord(
                project_name=self.settings.project.name,
                project_name_zh=self.settings.project.name_zh,
                device_name=self.settings.project.device_name,
                record_id=record.record_id,
                cycle_id=mode_cycle_id,
                camera_id=camera_id,
                camera_name=status.camera_name,
                timestamp=frame.timestamp.isoformat(),
                angle_deg=angle_deg,
                motor_position_deg=motor_status.command_position_deg,
                file_path=relative_path,
                status="success",
            )
            try:
                self.metadata.append(
                    metadata_record,
                    record.record_path,
                    mode_folder,
                )
            except Exception:
                path.unlink(missing_ok=True)
                raise
            results[mode_folder] = CaptureResult(**metadata_record.model_dump())
        return results
