from __future__ import annotations

from app.core.config import AppSettings
from app.services.rotation_service import RotationService


def test_angle_sequence_is_inclusive() -> None:
    service = RotationService(AppSettings(), None, None, None)
    assert service.angle_sequence(0, 45, 15) == [0, 15, 30, 45]
