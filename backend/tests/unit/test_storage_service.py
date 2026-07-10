from __future__ import annotations

from app.core.config import AppSettings, PathSettings
from app.services.storage_service import StorageService


def test_rotating_arm_path_uses_cycle_and_angle(tmp_path) -> None:
    settings = AppSettings(paths=PathSettings(captures_dir=tmp_path))
    storage = StorageService(settings)
    storage.create_session_layout("session_test_001")
    path = storage.next_capture_path("session_test_001", "rotating_arm", cycle_id=2, angle_deg=15)
    assert path.name == "angle_015.0.jpg"
    assert path.parent.name == "cycle_000002"
