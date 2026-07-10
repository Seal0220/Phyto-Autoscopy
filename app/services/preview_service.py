from __future__ import annotations

import time
from collections.abc import Iterator


class PreviewService:
    def __init__(self, camera_manager) -> None:
        self.camera_manager = camera_manager

    def mjpeg_stream(self, camera_id: str) -> Iterator[bytes]:
        while True:
            frame = self.camera_manager.capture(camera_id)
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + frame.data
                + b"\r\n"
            )
            time.sleep(0.2)
