from __future__ import annotations

from app.core.config import AppSettings
from app.models.camera_models import CaptureResult
from app.models.capture_models import MetadataRecord
from app.services.metadata_service import MetadataService
from app.services.session_service import SessionService
from app.services.storage_service import StorageService


class CaptureService:
    def __init__(
        self,
        settings: AppSettings,
        camera_manager,
        motor_controller,
        storage: StorageService,
        metadata: MetadataService,
        sessions: SessionService,
    ) -> None:
        self.settings = settings
        self.camera_manager = camera_manager
        self.motor_controller = motor_controller
        self.storage = storage
        self.metadata = metadata
        self.sessions = sessions

    def capture_camera(
        self,
        camera_id: str,
        session_id: str | None = None,
        cycle_id: int | None = None,
        angle_deg: float | None = None,
    ) -> CaptureResult:
        session = (
            self.sessions.ensure_active_session()
            if session_id is None
            else self.sessions.get_session(session_id)
        )
        frame = self.camera_manager.capture(camera_id)
        status = self.camera_manager.get_status(camera_id)
        motor_status = self.motor_controller.status()
        path = self.storage.next_capture_path(session.session_id, camera_id, cycle_id, angle_deg)
        self.storage.save_bytes(path, frame.data)
        relative_path = self.storage.relative_to_session(session.session_id, path)

        record = MetadataRecord(
            project_name=self.settings.project.name,
            project_name_zh=self.settings.project.name_zh,
            device_name=self.settings.project.device_name,
            session_id=session.session_id,
            cycle_id=cycle_id,
            camera_id=camera_id,
            camera_name=status.camera_name,
            timestamp=frame.timestamp.isoformat(),
            angle_deg=angle_deg,
            motor_position_deg=motor_status.command_position_deg,
            file_path=relative_path,
            status="success",
        )
        self.metadata.append(record)
        return CaptureResult(**record.model_dump())

    def capture_all(self, session_id: str | None = None) -> list[CaptureResult]:
        return [
            self.capture_camera(camera_id, session_id=session_id)
            for camera_id in ("top", "fixed_side", "rotating_arm")
        ]
