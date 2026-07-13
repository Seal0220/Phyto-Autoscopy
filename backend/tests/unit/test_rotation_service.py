from __future__ import annotations

from app.core.config import AppSettings
from app.services.rotation_service import RotationService


def test_angle_sequence_is_inclusive() -> None:
    service = RotationService(AppSettings(), None, None, None)
    assert service.angle_sequence(0, 45, 15) == [0, 15, 30, 45]


def test_schedule_capture_sequence_includes_both_directions_when_enabled() -> None:
    service = RotationService(AppSettings(), None, None, None)

    assert service.schedule_capture_sequence(0, 45, 15, True) == [
        (0, "forward"),
        (15, "forward"),
        (30, "forward"),
        (45, "forward"),
        (30, "return"),
        (15, "return"),
        (0, "return"),
    ]


def test_schedule_capture_sequence_omits_return_capture_when_disabled() -> None:
    service = RotationService(AppSettings(), None, None, None)

    assert service.schedule_capture_sequence(0, 45, 15, False) == [
        (0, "forward"),
        (15, "forward"),
        (30, "forward"),
        (45, "forward"),
    ]


def test_schedule_capture_sequence_steps_from_nonzero_start_to_origin() -> None:
    service = RotationService(AppSettings(), None, None, None)

    assert service.schedule_capture_sequence(30, 60, 15, True) == [
        (30, "forward"),
        (45, "forward"),
        (60, "forward"),
        (45, "return"),
        (30, "return"),
        (15, "return"),
        (0.0, "return"),
    ]
