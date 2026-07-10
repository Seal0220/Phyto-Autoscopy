from __future__ import annotations

from app.core.config import AppSettings
from app.hardware.cameras.mock_camera import MockCameraManager


def test_mock_camera_capture_returns_jpeg_bytes() -> None:
    manager = MockCameraManager(AppSettings())
    frame = manager.capture("top")
    assert frame.data.startswith(b"\xff\xd8")
    assert frame.content_type == "image/jpeg"
