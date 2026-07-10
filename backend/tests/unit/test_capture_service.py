from __future__ import annotations

from app.core.config import AppSettings, HardwareSettings, PathSettings
from app.database.connection import Database
from app.database.schema import initialize_schema
from app.hardware.cameras.mock_camera import MockCameraManager
from app.hardware.motor.mock_motor import MockMotorController
from app.repositories.capture_repository import CaptureRepository
from app.repositories.session_repository import SessionRepository
from app.services.capture_service import CaptureService
from app.services.metadata_service import MetadataService
from app.services.session_service import SessionService
from app.services.storage_service import StorageService


def test_capture_service_writes_image_and_metadata(tmp_path) -> None:
    settings = AppSettings(
        hardware=HardwareSettings(mock_mode=True),
        paths=PathSettings(
            captures_dir=tmp_path / "captures",
            database_path=tmp_path / "database.sqlite3",
            logs_dir=tmp_path / "logs",
            temp_dir=tmp_path / "temp",
        ),
    )
    database = Database(settings.paths.database_path)
    initialize_schema(database)
    storage = StorageService(settings)
    storage.ensure_base_dirs()
    sessions = SessionService(settings, storage, SessionRepository(database))
    metadata = MetadataService(storage, CaptureRepository(database))
    service = CaptureService(
        settings,
        MockCameraManager(settings),
        MockMotorController(settings.motor),
        storage,
        metadata,
        sessions,
    )

    result = service.capture_camera("top")

    assert result.status == "success"
    assert (storage.session_dir(result.session_id) / result.file_path).exists()
    assert "top/" in result.file_path
    assert storage.metadata_path(result.session_id).exists()
    database.close()
