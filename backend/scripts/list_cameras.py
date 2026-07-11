from __future__ import annotations

from _bootstrap import bootstrap

bootstrap()

from app.core.config import load_settings
from app.hardware.cameras.camera_identifier import scan_opencv_indices


def main() -> None:
    settings = load_settings()
    for result in scan_opencv_indices(settings.hardware.camera_scan_max_index):
        print(result)


if __name__ == "__main__":
    main()
