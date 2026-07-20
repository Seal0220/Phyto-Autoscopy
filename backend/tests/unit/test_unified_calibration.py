from __future__ import annotations

from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from pydantic import ValidationError

from app.calibration.extrinsic_solver import _camera_matrix_for_detection
from app.calibration.motion_model import rotating_camera_pose
from app.calibration.observation_graph import observation_graph_status
from app.calibration.rotation_axis_solver import fit_rotation_axis
from app.calibration.world_alignment import default_world_alignment
from app.core.config import AppSettings, CameraConfig, PathSettings
from app.core.exceptions import CalibrationError
from app.database.connection import Database
from app.database.schema import initialize_schema
from app.models.calibration_models import (
    CalibrationBoardProfile,
    CalibrationLockRequest,
    CalibrationMotionModel,
    CalibrationWorldAlignment,
    CameraIntrinsics,
    ExtrinsicCameraConfiguration,
    ExtrinsicProfile,
)
from app.repositories.calibration_repository import CalibrationRepository
from app.services.calibration_lock_service import CalibrationLockService
from app.services.calibration_storage_service import CalibrationStorageService
from app.services.calibration_validation_service import CalibrationValidationService
from app.services.extrinsic_calibration_service import ExtrinsicCalibrationService
from app.services.unified_calibration_service import CalibrationService


NOW = "2026-07-20T00:00:00+00:00"


def settings_for(tmp_path) -> AppSettings:
    return AppSettings(
        paths=PathSettings(
            captures_dir=tmp_path / "captures",
            snapshots_dir=tmp_path / "snapshots",
            calibration_dir=tmp_path / "calibration",
            analysis_dir=tmp_path / "analysis",
            database_path=tmp_path / "database" / "test.sqlite3",
            logs_dir=tmp_path / "logs",
            temp_dir=tmp_path / "temp",
        ),
        cameras={
            camera_id: CameraConfig(
                device_name=f"camera-{camera_id}",
                device_index=index,
                width=1280,
                height=720,
            )
            for index, camera_id in enumerate(("top", "side", "rotating"))
        },
    )


def repository_for(tmp_path):
    database = Database(tmp_path / "database" / "test.sqlite3")
    initialize_schema(database)
    repository = CalibrationRepository(database)
    board = CalibrationBoardProfile(
        board_profile_id="board-test",
        name="測試校正板",
        board_type="charuco",
        squares_x=8,
        squares_y=6,
        square_length_mm=30,
        marker_length_mm=22,
        created_at=NOW,
        updated_at=NOW,
    )
    repository.create_board(board)
    return database, repository


def intrinsics(
    camera_id: str,
    *,
    width: int = 1280,
    height: int = 720,
    updated_at: str = NOW,
) -> CameraIntrinsics:
    return CameraIntrinsics(
        camera_id=camera_id,
        camera_model="opencv",
        width=width,
        height=height,
        camera_matrix=[
            [900.0, 0.0, width / 2],
            [0.0, 900.0, height / 2],
            [0.0, 0.0, 1.0],
        ],
        distortion_coefficients=[0.0, 0.0, 0.0, 0.0, 0.0],
        reprojection_error_px=0.3,
        median_reprojection_error_px=0.25,
        maximum_reprojection_error_px=0.7,
        validation_error_px=0.4,
        sample_count=12,
        board_profile_id="board-test",
        quality_status="acceptable",
        source_run_id=f"run-{camera_id}",
        created_at=NOW,
        updated_at=updated_at,
    )


def profile(
    profile_id: str,
    *,
    status: str = "valid",
) -> ExtrinsicProfile:
    return ExtrinsicProfile(
        profile_id=profile_id,
        name=profile_id,
        status=status,
        board_profile_id="board-test",
        camera_ids=["top"],
        cameras=[
            ExtrinsicCameraConfiguration(
                camera_id="top",
                height_mm=500,
            )
        ],
        motion_model=CalibrationMotionModel(),
        world_alignment=CalibrationWorldAlignment(),
        quality_status="acceptable" if status == "valid" else "failed",
        created_at=NOW,
        updated_at=NOW,
    )


def test_intrinsics_are_unique_and_reapplying_archives_previous_value(
    tmp_path,
) -> None:
    database, repository = repository_for(tmp_path)
    try:
        repository.upsert_intrinsics(intrinsics("top"))
        replacement = intrinsics(
            "top",
            width=1920,
            height=1080,
            updated_at="2026-07-20T01:00:00+00:00",
        )
        repository.upsert_intrinsics(replacement)

        current = repository.get_intrinsics("top")
        history = database.fetchall(
            "SELECT * FROM camera_intrinsics_history WHERE camera_id='top'"
        )

        assert current is not None
        assert (current.width, current.height) == (1920, 1080)
        assert len(repository.list_intrinsics()) == 1
        assert len(history) == 1
    finally:
        database.close()


def test_extrinsic_profiles_are_multiple_but_only_one_can_be_active(
    tmp_path,
) -> None:
    database, repository = repository_for(tmp_path)
    try:
        repository.create_extrinsic_profile(profile("profile-a"))
        repository.create_extrinsic_profile(profile("profile-b"))
        repository.create_extrinsic_profile(
            profile("profile-invalid", status="invalid")
        )

        repository.activate_extrinsic_profile("profile-a", NOW)
        repository.activate_extrinsic_profile(
            "profile-b",
            "2026-07-20T01:00:00+00:00",
        )

        assert len(repository.list_extrinsic_profiles()) == 3
        assert repository.get_extrinsic_profile("profile-a").status == "valid"
        assert repository.get_active_extrinsic_profile().profile_id == "profile-b"
        with pytest.raises(CalibrationError, match="只有通過品質驗證"):
            repository.activate_extrinsic_profile("profile-invalid", NOW)
        with pytest.raises(CalibrationError, match="不可直接刪除"):
            repository.delete_extrinsic_profile("profile-b")
    finally:
        database.close()


def test_resolution_change_is_reported_and_intrinsics_are_scaled_before_use(
    tmp_path,
) -> None:
    database, repository = repository_for(tmp_path)
    try:
        stored = intrinsics("top", width=640, height=480)
        repository.upsert_intrinsics(stored)
        validation = CalibrationValidationService(
            settings_for(tmp_path),
            repository,
        ).intrinsics_status()[0]
        scaled = _camera_matrix_for_detection(
            {
                "image_width": 1280,
                "image_height": 720,
            },
            stored,
        )

        assert validation.status == "valid"
        assert validation.quality["resolution_requires_scaling"] is True
        assert scaled[0, 0] == pytest.approx(1800.0)
        assert scaled[1, 1] == pytest.approx(1350.0)
        assert scaled[0, 2] == pytest.approx(640.0)
        assert scaled[1, 2] == pytest.approx(360.0)
    finally:
        database.close()


def test_observation_graph_accepts_indirect_camera_connectivity() -> None:
    observations = [
        SimpleNamespace(
            accepted=True,
            detections={
                "top": {"board_detected": True},
                "rotating": {"board_detected": True},
            },
        ),
        SimpleNamespace(
            accepted=True,
            detections={
                "side": {"board_detected": True},
                "rotating": {"board_detected": True},
            },
        ),
    ]

    result = observation_graph_status(
        ["top", "side", "rotating"],
        observations,
    )

    assert result["connected"] is True
    assert result["edge_count"] == 2
    assert result["components"] == [["rotating", "side", "top"]]


def test_rotation_axis_fits_multiple_motor_angles(monkeypatch) -> None:
    observations = []
    poses = {}
    for index, angle in enumerate((0.0, 90.0, 180.0, 270.0)):
        radians = np.deg2rad(angle)
        pose = np.eye(4, dtype=np.float64)
        pose[:3, 3] = [100.0 * np.cos(radians), 100.0 * np.sin(radians), 30.0]
        pose[:3, :3], _ = cv2.Rodrigues(
            np.asarray([0.0, 0.0, radians], dtype=np.float64)
        )
        observation_id = f"observation-{index}"
        poses[observation_id] = pose
        observations.append(SimpleNamespace(
            observation_id=observation_id,
            motor_angle_deg=angle,
            detections={
                "rotating": {
                    "board_detected": True,
                    "observation_id": observation_id,
                }
            },
        ))

    monkeypatch.setattr(
        "app.calibration.rotation_axis_solver.camera_pose_from_detection",
        lambda detection, _intrinsics: poses[detection["observation_id"]],
    )

    result = fit_rotation_axis(observations, SimpleNamespace())

    assert result["arm_radius_mm"] == pytest.approx(100.0, abs=1e-6)
    assert result["axis_fit_residual_mm"] == pytest.approx(0.0, abs=1e-6)
    assert len(result["fitted_angles_deg"]) == 4
    assert np.linalg.norm(result["rotation_axis_direction"]) == pytest.approx(1.0)


def test_world_alignment_and_height_data_are_validated() -> None:
    aligned = default_world_alignment(
        CalibrationWorldAlignment(
            origin_offset_mm=[10.0, -5.0, 2.0],
            platform_height_mm=80.0,
        ),
        np.eye(4),
    )

    assert aligned.transform_world_from_rig[0][3] == pytest.approx(10.0)
    assert aligned.transform_world_from_rig[1][3] == pytest.approx(-5.0)
    assert aligned.unit == "mm"
    with pytest.raises(ValidationError):
        ExtrinsicCameraConfiguration(camera_id="top", height_mm=-1)
    with pytest.raises(ValidationError, match="結束角度"):
        CalibrationMotionModel(usable_angle_range_deg=[90, 45])


def test_rotating_motion_model_evaluates_angle_and_height() -> None:
    mount = np.eye(4, dtype=np.float64)
    mount[:3, 3] = [100.0, 0.0, 20.0]
    model = CalibrationMotionModel(
        arm_height_mm=450.0,
        rotation_axis_origin_mm=[0.0, 0.0, 0.0],
        rotation_axis_direction=[0.0, 0.0, 1.0],
        motor_zero_offset_deg=0.0,
        mount_transform_from_camera=mount.tolist(),
        lift_axis_direction=[0.0, 0.0, 1.0],
        height_reference_mm=450.0,
    )

    reference = rotating_camera_pose(model, 0.0, 450.0)
    rotated = rotating_camera_pose(model, 90.0, 500.0)

    assert np.allclose(reference, mount)
    assert rotated[0, 3] == pytest.approx(0.0, abs=1e-8)
    assert rotated[1, 3] == pytest.approx(100.0, abs=1e-8)
    assert rotated[2, 3] == pytest.approx(70.0, abs=1e-8)
    with pytest.raises(ValueError, match="必須介於"):
        rotating_camera_pose(model, 361.0, 450.0)


class ScheduleStub:
    def __init__(self, status: str = "idle") -> None:
        self.value = status

    def get_status(self):
        return SimpleNamespace(status=self.value)


class LockOwnerStub:
    def ensure_owner(self, owner: str) -> None:
        assert owner == "operator-a"


def test_calibration_lock_is_mutually_exclusive_and_runs_release_cleanup() -> None:
    schedule = ScheduleStub()
    service = CalibrationLockService(schedule)
    released = []
    service.set_release_callback(
        lambda previous, reason: released.append((previous.owner, reason))
    )

    acquired = service.acquire(
        "operator-a",
        CalibrationLockRequest(mode="unified"),
    )

    assert acquired.locked is True
    with pytest.raises(CalibrationError, match="另一位操作人員"):
        service.acquire(
            "operator-b",
            CalibrationLockRequest(mode="unified"),
        )
    with pytest.raises(CalibrationError, match="暫時無法"):
        service.ensure_unlocked()
    service.release("operator-a")
    assert released == [("operator-a", "released")]

    schedule.value = "running"
    with pytest.raises(CalibrationError, match="排程進行中"):
        service.acquire(
            "operator-a",
            CalibrationLockRequest(mode="unified"),
        )


def test_calibration_lock_release_stops_and_restores_motor_state() -> None:
    calls = []
    motor = SimpleNamespace(
        stop=lambda: calls.append("stop"),
        emergency_stop=lambda: calls.append("emergency-stop"),
        disengage=lambda: calls.append("disengage"),
    )
    service = CalibrationService.__new__(CalibrationService)
    service.motor_controller = motor
    service._calibration_engaged_motor = True

    service.on_lock_released(SimpleNamespace(), "released")

    assert calls == ["stop", "disengage"]
    assert service._calibration_engaged_motor is False


def test_calibration_lock_release_uses_emergency_stop_when_stop_fails() -> None:
    calls = []

    def fail_stop() -> None:
        calls.append("stop")
        raise RuntimeError("motor timeout")

    motor = SimpleNamespace(
        stop=fail_stop,
        emergency_stop=lambda: calls.append("emergency-stop"),
        disengage=lambda: calls.append("disengage"),
    )
    service = CalibrationService.__new__(CalibrationService)
    service.motor_controller = motor
    service._calibration_engaged_motor = False

    service.on_lock_released(SimpleNamespace(), "expired")

    assert calls == ["stop", "emergency-stop"]


def test_extrinsic_activation_rolls_back_files_when_database_update_fails(
    tmp_path,
    monkeypatch,
) -> None:
    settings = settings_for(tmp_path)
    database, repository = repository_for(tmp_path)
    try:
        repository.create_extrinsic_profile(profile("profile-a"))
        repository.create_extrinsic_profile(profile("profile-b"))
        repository.activate_extrinsic_profile("profile-a", NOW)
        storage = CalibrationStorageService(settings, repository)
        storage.reconcile()
        service = ExtrinsicCalibrationService(
            settings,
            repository,
            capture_service=None,
            lock_service=LockOwnerStub(),
            storage_service=storage,
        )
        monkeypatch.setattr(
            repository,
            "activate_extrinsic_profile",
            lambda *_args: (_ for _ in ()).throw(
                RuntimeError("database write failed")
            ),
        )

        with pytest.raises(RuntimeError, match="database write failed"):
            service.activate("profile-b", "operator-a")

        stored_a = ExtrinsicProfile.model_validate_json(
            (
                settings.paths.calibration_dir
                / "extrinsics"
                / "profile-a"
                / "profile.json"
            ).read_text(encoding="utf-8")
        )
        stored_b = ExtrinsicProfile.model_validate_json(
            (
                settings.paths.calibration_dir
                / "extrinsics"
                / "profile-b"
                / "profile.json"
            ).read_text(encoding="utf-8")
        )
        assert stored_a.is_active is True
        assert stored_a.status == "active"
        assert stored_b.is_active is False
        assert stored_b.status == "valid"
        assert repository.get_active_extrinsic_profile().profile_id == "profile-a"
    finally:
        database.close()


def test_calibration_storage_rebuilds_corrupt_json_from_sqlite(
    tmp_path,
) -> None:
    settings = settings_for(tmp_path)
    database, repository = repository_for(tmp_path)
    try:
        stored_intrinsics = intrinsics("top")
        stored_profile = profile("profile-storage")
        repository.upsert_intrinsics(stored_intrinsics)
        repository.create_extrinsic_profile(stored_profile)
        storage = CalibrationStorageService(settings, repository)
        intrinsics_path = settings.paths.calibration_dir / "intrinsics" / "top.json"
        profile_path = (
            settings.paths.calibration_dir
            / "extrinsics"
            / stored_profile.profile_id
            / "profile.json"
        )
        intrinsics_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        intrinsics_path.write_text("", encoding="utf-8")
        profile_path.write_text("{broken", encoding="utf-8")

        storage.reconcile()

        assert CameraIntrinsics.model_validate_json(
            intrinsics_path.read_text(encoding="utf-8")
        ).camera_id == "top"
        assert ExtrinsicProfile.model_validate_json(
            profile_path.read_text(encoding="utf-8")
        ).profile_id == stored_profile.profile_id
        assert storage.synchronized is True
    finally:
        database.close()


def test_calibration_storage_failure_preserves_sqlite_and_reports_recovery(
    tmp_path,
    monkeypatch,
) -> None:
    settings = settings_for(tmp_path)
    database, repository = repository_for(tmp_path)
    try:
        stored_intrinsics = intrinsics("top")
        repository.upsert_intrinsics(stored_intrinsics)
        storage = CalibrationStorageService(settings, repository)
        monkeypatch.setattr(
            "app.services.calibration_storage_service.write_json_atomic",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                OSError("磁碟空間不足")
            ),
        )

        with pytest.raises(CalibrationError, match="重新同步"):
            storage.write_intrinsics(stored_intrinsics)

        assert repository.get_intrinsics("top") == stored_intrinsics
        assert storage.synchronized is False
        assert "SQLite" in storage.last_error
        assert "磁碟空間不足" in storage.last_error
    finally:
        database.close()
