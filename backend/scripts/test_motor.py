from __future__ import annotations

import argparse

from _bootstrap import bootstrap

bootstrap()

from app.core.config import load_settings
from app.hardware.motor.mock_motor import MockMotorController
from app.hardware.motor.phidget_stepper import PhidgetStepperController


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--angle", type=float, default=5.0)
    args = parser.parse_args()

    settings = load_settings()
    controller = MockMotorController(settings.motor) if args.mock else PhidgetStepperController(settings.motor)
    controller.engage()
    print(controller.move_to_angle(args.angle))
    print(controller.return_origin())
    print(controller.disengage())
    controller.close()


if __name__ == "__main__":
    main()
