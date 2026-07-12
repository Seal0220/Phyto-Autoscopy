from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.config import get_config_dir, read_json_file, save_settings_group
from app.core.exceptions import ConfigError
from app.core.state import AppContext, get_context
from app.models.settings_models import SettingsGroupUpdate
from app.repositories.settings_repository import SettingsRepository
from app.services.runtime_settings_service import apply_runtime_settings, build_candidate_settings

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
        raise ConfigError(f"找不到設定群組：{group}")
    return read_json_file(get_config_dir() / file_map[group])


@router.post("/reset")
def reset_settings() -> dict:
    return {"detail": "為了硬體安全，重設必須手動執行。"}


@router.post("/{group}")
def update_settings_group(
    group: str,
    update: SettingsGroupUpdate,
    context: AppContext = Depends(get_context),
) -> dict:
    candidate = build_candidate_settings(context, group, update.payload)
    apply_runtime_settings(context, candidate, group)
    save_settings_group(group, update.payload)
    SettingsRepository(context.database).snapshot(group, update.payload)
    return {"updated": group, "applied": True}
