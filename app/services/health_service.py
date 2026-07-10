from __future__ import annotations

import shutil

from app.core.config import AppSettings
from app.models.system_models import DiskStatus


class HealthService:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def disk_status(self) -> DiskStatus:
        usage = shutil.disk_usage(self.settings.paths.captures_dir)
        return DiskStatus(
            path=str(self.settings.paths.captures_dir),
            total_bytes=usage.total,
            used_bytes=usage.used,
            free_bytes=usage.free,
        )
