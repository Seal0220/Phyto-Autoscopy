from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from time import monotonic

from app.core.exceptions import CameraError

logger = logging.getLogger(__name__)


class ImagePreviewService:
    def __init__(self, camera_manager) -> None:
        self.camera_manager = camera_manager

    async def mjpeg_stream(
        self,
        camera_id: str,
        first_frame=None,
        first_sequence: int | None = None,
        frame_undistorter=None,
    ) -> AsyncIterator[bytes]:
        control_settings = self.camera_manager.settings.camera_control
        frame = first_frame
        sequence = first_sequence
        recovery_started_at: float | None = None
        begin_preview = getattr(self.camera_manager, "begin_preview", None)
        end_preview = getattr(self.camera_manager, "end_preview", None)
        wait_for_frame = getattr(self.camera_manager, "wait_for_frame", None)
        if begin_preview is not None:
            begin_preview(camera_id)
        try:
            while True:
                status = self.camera_manager.get_status(camera_id)
                if not status.enabled:
                    return
                if frame is None:
                    try:
                        if wait_for_frame is not None:
                            frame, sequence = await asyncio.to_thread(
                                wait_for_frame,
                                camera_id,
                                after_sequence=sequence,
                                timeout=control_settings.frame_wait_seconds,
                            )
                        else:
                            frame = await asyncio.to_thread(
                                self.camera_manager.capture,
                                camera_id,
                            )
                        recovery_started_at = None
                    except CameraError:
                        # The worker owns reconnection and publishes the
                        # actionable state.  Give an established stream a
                        # bounded window to resume without becoming permanent.
                        now = monotonic()
                        if recovery_started_at is None:
                            recovery_started_at = now
                        if (
                            now - recovery_started_at
                            >= control_settings.stream_recovery_grace_seconds
                        ):
                            return
                        await asyncio.sleep(
                            control_settings.stream_retry_seconds
                        )
                        continue
                    except Exception:
                        logger.exception(
                            "相機 %s 影像串流發生未預期錯誤。",
                            camera_id,
                        )
                        return
                frame_data = frame.data
                if frame_undistorter is not None:
                    frame_data = await asyncio.to_thread(
                        frame_undistorter.apply,
                        frame_data,
                    )
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + frame_data
                    + b"\r\n"
                )
                frame = None
                preview_fps = max(1, status.preview_fps or 1)
                await asyncio.sleep(1.0 / preview_fps)
        finally:
            if end_preview is not None:
                end_preview(camera_id)
