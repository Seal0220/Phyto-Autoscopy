from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any

from fastapi import Request

from app.core.config import AppSettings


@dataclass
class AppContext:
    settings: AppSettings
    database: Any
    camera_manager: Any
    motor_controller: Any
    storage_service: Any
    metadata_service: Any
    record_service: Any
    capture_service: Any
    rotation_service: Any
    image_preview_service: Any
    snapshot_service: Any
    schedule_service: Any
    health_service: Any
    calibration_service: Any = None
    analysis_service: Any = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    recent_errors: list[str] = field(default_factory=list)
    _error_lock: RLock = field(default_factory=RLock, init=False, repr=False)
    _settings_lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def add_error(self, message: str) -> None:
        with self._error_lock:
            self.recent_errors.append(message)
            self.recent_errors[:] = self.recent_errors[-20:]

    def get_recent_errors(self) -> list[str]:
        with self._error_lock:
            return list(self.recent_errors)

    def clear_errors(self) -> None:
        with self._error_lock:
            self.recent_errors.clear()


def get_context(request: Request) -> AppContext:
    return request.app.state.context
