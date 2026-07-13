from __future__ import annotations

import logging
import time
from collections.abc import Iterator

logger = logging.getLogger(__name__)


class ImagePreviewService:
    def __init__(self, camera_manager) -> None:
        self.camera_manager = camera_manager

    def mjpeg_stream(self, camera_id: str, first_frame=None) -> Iterator[bytes]:
        frame = first_frame
        consecutive_failures = 0
        while True:
            status = self.camera_manager.get_status(camera_id)
            if not status.enabled:
                return
            if frame is None:
                try:
                    frame = self.camera_manager.capture(camera_id)
                    consecutive_failures = 0
                except Exception:
                    consecutive_failures += 1
                    logger.warning(
                        "Camera preview capture failed; retrying: %s",
                        camera_id,
                        exc_info=True,
                    )
                    if consecutive_failures >= 3:
                        return
                    time.sleep(1.0)
                    continue
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + frame.data
                + b"\r\n"
            )
            frame = None
            preview_fps = max(1, status.preview_fps or 1)
            time.sleep(1.0 / preview_fps)
