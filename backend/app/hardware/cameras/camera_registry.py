from __future__ import annotations

from app.core.config import AppSettings, CameraConfig
from app.core.constants import CAMERA_ROLES
from app.core.exceptions import CameraError


class CameraRegistry:
    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def roles(self) -> tuple[str, ...]:
        return CAMERA_ROLES

    def get(self, camera_id: str) -> CameraConfig:
        try:
            return self._settings.cameras[camera_id]
        except KeyError as exc:
            raise CameraError(f"找不到相機：{camera_id}") from exc

    def all(self) -> dict[str, CameraConfig]:
        return dict(self._settings.cameras)
