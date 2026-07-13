from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.config import AppSettings, MotorSettings
from app.core.exceptions import CameraError, MotorError
from app.hardware.cameras.camera_types import CameraFrame
from app.hardware.motor.phidget_stepper import PhidgetStepperController
from app.services.capture_service import CaptureService
from app.services.health_service import HealthService
from app.services.image_preview_service import ImagePreviewService
from app.services.rotation_service import RotationService


class RecoveringPreviewManager:
    def __init__(self) -> None:
        self.capture_calls = 0

    def get_status(self, _camera_id: str):
        return SimpleNamespace(enabled=True, preview_fps=4)

    def capture(self, camera_id: str) -> CameraFrame:
        self.capture_calls += 1
        if self.capture_calls == 1:
            raise CameraError("相機暫時離線。")
        return CameraFrame(
            camera_id=camera_id,
            data=b"jpeg",
            timestamp=datetime.now(timezone.utc),
        )


class TimeoutStepper:
    def __init__(self) -> None:
        self.targets: list[float] = []

    def setTargetPosition(self, target: float) -> None:
        self.targets.append(target)

    def getPosition(self) -> float:
        return 0.0

    def getIsMoving(self) -> bool:
        return True


def test_preview_stream_retries_and_uses_preview_fps(monkeypatch) -> None:
    manager = RecoveringPreviewManager()
    sleeps: list[float] = []
    monkeypatch.setattr(
        "app.services.image_preview_service.time.sleep",
        sleeps.append,
    )

    frame = next(ImagePreviewService(manager).mjpeg_stream("top"))

    assert b"jpeg" in frame
    assert manager.capture_calls == 2
    assert sleeps == [1.0]


def test_capture_all_attempts_every_enabled_camera_before_reporting_failure() -> None:
    service = CaptureService.__new__(CaptureService)
    service.camera_manager = SimpleNamespace(
        get_statuses=lambda: [
            SimpleNamespace(camera_id="top", enabled=True),
            SimpleNamespace(camera_id="side", enabled=True),
            SimpleNamespace(camera_id="rotating", enabled=True),
        ]
    )
    attempted: list[str] = []

    def capture(camera_id: str, record_id=None):
        attempted.append(camera_id)
        if camera_id == "top":
            raise CameraError("相機未連線。")
        return SimpleNamespace(camera_id=camera_id)

    service.capture_camera = capture

    with pytest.raises(CameraError, match="成功 2 台，失敗 1 台"):
        service.capture_all()

    assert attempted == ["top", "side", "rotating"]


def test_phidget_timeout_clears_moving_without_locking() -> None:
    settings = MotorSettings(movement_timeout_seconds=0)
    controller = PhidgetStepperController(settings)
    stepper = TimeoutStepper()
    controller._stepper = stepper
    controller.state.connected = True
    controller.state.engaged = True

    with pytest.raises(MotorError, match="馬達移動逾時"):
        controller.move_to_angle(10)

    assert controller.state.moving is False
    assert len(stepper.targets) == 2


def test_rotation_failure_best_effort_returns_to_start() -> None:
    settings = AppSettings()
    settings.motor.stabilization_delay_ms = 0
    moves: list[float] = []
    motor = SimpleNamespace(
        move_to_angle=lambda angle: moves.append(angle),
        status=lambda: SimpleNamespace(engaged=True),
    )
    capture = SimpleNamespace(
        capture_camera=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            CameraError("擷取失敗。")
        )
    )
    records = SimpleNamespace(
        get_capture_record=lambda _record_id: SimpleNamespace(record_id="record-test")
    )
    service = RotationService(settings, motor, capture, records)

    with pytest.raises(CameraError, match="擷取失敗"):
        service.capture_cycle(start_deg=5, end_deg=10, step_deg=5)

    assert moves == [5, 5]


def test_disk_status_returns_safe_fallback(monkeypatch, tmp_path) -> None:
    settings = AppSettings()
    settings.paths.captures_dir = tmp_path / "records"
    monkeypatch.setattr(
        "app.services.health_service.shutil.disk_usage",
        lambda _path: (_ for _ in ()).throw(OSError("private disk error")),
    )

    status = HealthService(settings).disk_status()

    assert status.total_bytes == 0
    assert status.error == "無法讀取影像儲存空間狀態。"
