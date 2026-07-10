from __future__ import annotations

import argparse

from app.core.config import load_settings
from app.hardware.motor.mock_motor import MockMotorController
from app.hardware.motor.phidget_stepper import PhidgetStepperController


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    settings = load_settings()
    controller = MockMotorController(settings.motor) if args.mock else PhidgetStepperController(settings.motor)
    controller.connect()
    print(controller.set_origin())
    controller.close()


if __name__ == "__main__":
    main()
