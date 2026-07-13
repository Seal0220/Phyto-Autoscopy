from __future__ import annotations

from threading import Event, Thread

import pytest

from app.core.config import MotorSettings
from app.core.exceptions import MotorError, MotorSafetyError, OperationCancelledError
from app.hardware.motor.mock_motor import MockMotorController
from app.hardware.motor.phidget_stepper import PhidgetStepperController


class FakePhidgetStepper:
    def __init__(self, position: float) -> None:
        self.position = position
        self.position_offsets: list[float] = []

    def getPosition(self) -> float:
        return self.position

    def addPositionOffset(self, offset: float) -> None:
        self.position_offsets.append(offset)
        self.position += offset

    def getIsMoving(self) -> bool:
        return False


class BlockingPhidgetStepper:
    def __init__(self) -> None:
        self.position = 0.0
        self.moving = False
        self.started = Event()
        self.engaged = True

    def setTargetPosition(self, target: float) -> None:
        if target == self.position:
            self.moving = False
        else:
            self.moving = True
            self.started.set()

    def getPosition(self) -> float:
        return self.position

    def getIsMoving(self) -> bool:
        return self.moving

    def setEngaged(self, engaged: bool) -> None:
        self.engaged = engaged


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


def test_mock_motor_sets_current_position_as_zero_origin() -> None:
    controller = MockMotorController(MotorSettings())
    controller.engage()
    controller.move_to_angle(10)

    status = controller.set_origin()

    assert status.command_position_deg == 0.0


def test_mock_motor_returns_to_zero_origin() -> None:
    controller = MockMotorController(MotorSettings())
    controller.engage()
    controller.move_to_angle(10)

    status = controller.return_origin()

    assert status.command_position_deg == 0.0


def test_phidget_motor_offsets_current_position_to_zero_origin() -> None:
    controller = PhidgetStepperController(MotorSettings())
    current_position_steps = controller.profile.degrees_to_steps(10.0)
    fake_stepper = FakePhidgetStepper(current_position_steps)
    controller._stepper = fake_stepper

    status = controller.set_origin()

    assert fake_stepper.position_offsets == [-current_position_steps]
    assert status.command_position_deg == 0.0


def test_mock_motor_rejects_out_of_range_angle() -> None:
    controller = MockMotorController(MotorSettings())
    controller.engage()
    with pytest.raises(MotorSafetyError):
        controller.move_to_angle(361)


@pytest.mark.parametrize("stop_method", ["stop", "emergency_stop"])
def test_phidget_move_can_be_cancelled_concurrently(stop_method: str) -> None:
    controller = PhidgetStepperController(MotorSettings())
    stepper = BlockingPhidgetStepper()
    controller._stepper = stepper
    controller.state.connected = True
    controller.state.engaged = True
    outcome: list[BaseException] = []

    def move() -> None:
        try:
            controller.move_to_angle(10)
        except BaseException as exc:
            outcome.append(exc)

    worker = Thread(target=move)
    worker.start()
    assert stepper.started.wait(timeout=1)

    getattr(controller, stop_method)()
    worker.join(timeout=1)

    assert worker.is_alive() is False
    assert len(outcome) == 1
    assert isinstance(outcome[0], OperationCancelledError)
    assert controller.state.moving is False
