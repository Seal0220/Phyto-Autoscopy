from __future__ import annotations

import pytest

from app.core.config import MotorSettings
from app.core.exceptions import MotorError, MotorSafetyError
from app.hardware.motor.mock_motor import MockMotorController


def test_mock_motor_requires_engage_before_move() -> None:
    controller = MockMotorController(MotorSettings())
    with pytest.raises(MotorError):
        controller.move_to_angle(10)


def test_mock_motor_moves_within_limits() -> None:
    controller = MockMotorController(MotorSettings())
    controller.engage()
    status = controller.move_to_angle(10)
    assert status.command_position_deg == 10
    assert status.engaged is True


def test_mock_motor_rejects_out_of_range_angle() -> None:
    controller = MockMotorController(MotorSettings())
    controller.engage()
    with pytest.raises(MotorSafetyError):
        controller.move_to_angle(361)
