from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import load_settings
from app.core.logging_config import configure_logging
from app.core.shutdown import shutdown_context
from app.core.state import AppContext
from app.database.connection import Database
from app.database.schema import initialize_schema
from app.hardware.cameras.camera_manager import OpenCVCameraManager
from app.hardware.cameras.mock_camera import MockCameraManager
from app.hardware.motor.mock_motor import MockMotorController
from app.hardware.motor.phidget_stepper import PhidgetStepperController
from app.repositories.capture_repository import CaptureRepository
from app.repositories.session_repository import SessionRepository
from app.services.capture_service import CaptureService
from app.services.experiment_service import ExperimentService
from app.services.health_service import HealthService
from app.services.metadata_service import MetadataService
from app.services.preview_service import PreviewService
from app.services.rotation_service import RotationService
from app.services.session_service import SessionService
from app.services.storage_service import StorageService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    configure_logging(settings)

    database = Database(settings.paths.database_path)
    initialize_schema(database)

    storage = StorageService(settings)
    storage.ensure_base_dirs()

    camera_manager = (
        MockCameraManager(settings)
        if settings.hardware.mock_mode
        else OpenCVCameraManager(settings)
    )
    camera_manager.start()

    motor_controller = (
        MockMotorController(settings.motor)
        if settings.hardware.mock_mode
        else PhidgetStepperController(settings.motor)
    )

    session_repository = SessionRepository(database)
    capture_repository = CaptureRepository(database)

    metadata_service = MetadataService(storage, capture_repository)
    session_service = SessionService(settings, storage, session_repository)
    capture_service = CaptureService(
        settings,
        camera_manager,
        motor_controller,
        storage,
        metadata_service,
        session_service,
    )
    rotation_service = RotationService(
        settings,
        motor_controller,
        capture_service,
        session_service,
    )
    preview_service = PreviewService(camera_manager)
    experiment_service = ExperimentService(settings, session_service)
    health_service = HealthService(settings)

    context = AppContext(
        settings=settings,
        database=database,
        camera_manager=camera_manager,
        motor_controller=motor_controller,
        storage_service=storage,
        metadata_service=metadata_service,
        session_service=session_service,
        capture_service=capture_service,
        rotation_service=rotation_service,
        preview_service=preview_service,
        experiment_service=experiment_service,
        health_service=health_service,
    )
    app.state.context = context

    try:
        yield
    finally:
        shutdown_context(context)
