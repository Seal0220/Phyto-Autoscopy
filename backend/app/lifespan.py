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
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.calibration_repository import CalibrationRepository
from app.repositories.record_repository import RecordRepository
from app.services.calibration_service import CalibrationService
from app.services.capture_service import CaptureService
from app.services.analysis_service import AnalysisService
from app.services.schedule_service import ScheduleService
from app.services.health_service import HealthService
from app.services.metadata_service import MetadataService
from app.services.image_preview_service import ImagePreviewService
from app.services.rotation_service import RotationService
from app.services.record_service import RecordService
from app.services.storage_service import StorageService
from app.services.snapshot_service import SnapshotService


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

    record_repository = RecordRepository(database)
    capture_repository = CaptureRepository(database)
    analysis_repository = AnalysisRepository(database)
    calibration_repository = CalibrationRepository(database)

    metadata_service = MetadataService(storage, capture_repository)
    record_service = RecordService(settings, storage, record_repository)
    record_service.recover_interrupted_records()
    capture_service = CaptureService(
        settings,
        camera_manager,
        motor_controller,
        storage,
        metadata_service,
        record_service,
    )
    rotation_service = RotationService(
        settings,
        motor_controller,
        capture_service,
        record_service,
    )
    image_preview_service = ImagePreviewService(camera_manager)
    snapshot_service = SnapshotService(camera_manager, storage)
    schedule_service = ScheduleService(
        settings,
        record_service,
        motor_controller,
        capture_service,
        rotation_service,
        storage,
    )
    health_service = HealthService(settings)
    calibration_service = CalibrationService(
        settings,
        calibration_repository,
    )
    analysis_service = AnalysisService(
        settings,
        analysis_repository,
        record_repository,
        capture_repository,
        calibration_repository,
        calibration_service=calibration_service,
    )

    context = AppContext(
        settings=settings,
        database=database,
        camera_manager=camera_manager,
        motor_controller=motor_controller,
        storage_service=storage,
        metadata_service=metadata_service,
        record_service=record_service,
        capture_service=capture_service,
        rotation_service=rotation_service,
        image_preview_service=image_preview_service,
        snapshot_service=snapshot_service,
        schedule_service=schedule_service,
        health_service=health_service,
        calibration_service=calibration_service,
        analysis_service=analysis_service,
    )
    app.state.context = context
    schedule_service.error_reporter = context.add_error
    analysis_service.error_reporter = context.add_error
    analysis_service.recover_interrupted_runs()

    try:
        yield
    finally:
        shutdown_context(context)
