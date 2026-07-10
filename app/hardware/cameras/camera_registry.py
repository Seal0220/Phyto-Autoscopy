from __future__ import annotations

from app.core.config import AppSettings, CameraConfig
from app.core.constants import CAMERA_ROLES


class CameraRegistry:
    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def roles(self) -> tuple[str, ...]:
        return CAMERA_ROLES

    def get(self, camera_id: str) -> CameraConfig:
        return self._settings.cameras[camera_id]

    def all(self) -> dict[str, CameraConfig]:
        return dict(self._settings.cameras)
