from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
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
    session_service: Any
    capture_service: Any
    rotation_service: Any
    preview_service: Any
    experiment_service: Any
    health_service: Any
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    recent_errors: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.recent_errors.append(message)
        self.recent_errors[:] = self.recent_errors[-20:]


def get_context(request: Request) -> AppContext:
    return request.app.state.context
