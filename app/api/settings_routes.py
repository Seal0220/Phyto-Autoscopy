from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.config import get_config_dir, read_json_file, save_settings_group
from app.core.exceptions import ConfigError
from app.core.state import AppContext, get_context
from app.models.settings_models import SettingsGroupUpdate
from app.repositories.settings_repository import SettingsRepository

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings(context: AppContext = Depends(get_context)) -> dict:
    return context.settings.model_dump(mode="json")


@router.get("/{group}")
def get_settings_group(group: str, context: AppContext = Depends(get_context)) -> dict:
    file_map = {
        "default": "default.json",
        "cameras": "cameras.json",
        "motor": "motor.json",
        "experiment": "experiments.json",
        "logging": "logging.json",
    }
    if group not in file_map:
        raise ConfigError(f"Unknown settings group: {group}")
    return read_json_file(get_config_dir() / file_map[group])


@router.post("/reload")
def reload_settings() -> dict:
    return {"detail": "Restart the Python process to reload JSON settings safely."}


@router.post("/reset")
def reset_settings() -> dict:
    return {"detail": "Reset is intentionally manual for hardware safety."}


@router.post("/{group}")
def update_settings_group(
    group: str,
    update: SettingsGroupUpdate,
    context: AppContext = Depends(get_context),
) -> dict:
    save_settings_group(group, update.payload)
    SettingsRepository(context.database).snapshot(group, update.payload)
    return {"updated": group, "restart_recommended": True}
