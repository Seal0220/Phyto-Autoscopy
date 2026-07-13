from __future__ import annotations

import logging
import shutil

from app.core.config import AppSettings
from app.models.system_models import DiskStatus

logger = logging.getLogger(__name__)


class HealthService:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def disk_status(self) -> DiskStatus:
        path = self.settings.paths.captures_dir
        try:
            path.mkdir(parents=True, exist_ok=True)
            usage = shutil.disk_usage(path)
        except OSError:
            logger.exception("Failed to read capture storage usage: %s", path)
            return DiskStatus(
                path=str(path),
                total_bytes=0,
                used_bytes=0,
                free_bytes=0,
                error="無法讀取影像儲存空間狀態。",
            )
        return DiskStatus(
            path=str(path),
            total_bytes=usage.total,
            used_bytes=usage.used,
            free_bytes=usage.free,
        )
