from __future__ import annotations

import logging

from app.core.exceptions import CameraError, StorageError, public_error_detail
from app.hardware.cameras.camera_image import encode_lossless_capture
from app.models.camera_models import SnapshotResult
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)


class SnapshotService:
    def __init__(self, camera_manager, storage: StorageService) -> None:
        self.camera_manager = camera_manager
        self.storage = storage

    def snapshot_camera(self, camera_id: str) -> SnapshotResult:
        frame = self.camera_manager.capture(camera_id)
        image_data = encode_lossless_capture(frame)
        status = self.camera_manager.get_status(camera_id)
        try:
            path = self.storage.save_snapshot(
                camera_id,
                frame.timestamp,
                image_data,
            )
        except (OSError, ValueError) as exc:
            logger.exception("Failed to persist camera snapshot: %s", camera_id)
            raise StorageError("儲存影像快照失敗。") from exc
        return SnapshotResult(
            camera_id=camera_id,
            camera_name=status.camera_name,
            timestamp=frame.timestamp.isoformat(),
            file_path=path.name,
        )

    def snapshot_all(self) -> list[SnapshotResult]:
        camera_ids = [
            status.camera_id
            for status in self.camera_manager.get_statuses()
            if status.enabled
        ]
        if not camera_ids:
            raise CameraError("目前沒有已啟用的相機可供擷取快照。")
        results: list[SnapshotResult] = []
        failures: list[str] = []
        for camera_id in camera_ids:
            try:
                results.append(self.snapshot_camera(camera_id))
            except Exception as exc:
                failures.append(f"{camera_id}（{public_error_detail(exc)}）")
        if failures:
            raise CameraError(
                f"擷取全部快照未完整完成；成功 {len(results)} 台，"
                f"失敗 {len(failures)} 台：{', '.join(failures)}"
            )
        return results
