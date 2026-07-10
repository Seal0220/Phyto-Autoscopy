from __future__ import annotations

import argparse
from pathlib import Path

from app.core.config import load_settings
from app.hardware.cameras.camera_manager import OpenCVCameraManager
from app.hardware.cameras.mock_camera import MockCameraManager


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("camera_id", choices=["top", "fixed_side", "rotating_arm"])
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--output", default="data/temp/test_camera.jpg")
    args = parser.parse_args()

    settings = load_settings()
    manager = MockCameraManager(settings) if args.mock else OpenCVCameraManager(settings)
    manager.start()
    frame = manager.capture(args.camera_id)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(frame.data)
    manager.close_all()
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
