from __future__ import annotations

import logging
from copy import deepcopy

from fastapi import APIRouter, Depends

from app.core.config import get_config_dir, read_json_file, save_settings_group
from app.core.exceptions import ConfigError
from app.core.state import AppContext, get_context
from app.models.settings_models import SettingsGroupUpdate
from app.repositories.settings_repository import SettingsRepository
from app.services.runtime_settings_service import apply_runtime_settings, build_candidate_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])
logger = logging.getLogger(__name__)

SETTINGS_FILES = {
    "default": "default.json",
    "cameras": "cameras.json",
    "motor": "motor.json",
    "schedule": "schedule.json",
    "analysis": "analysis.json",
    "calibration": "calibration.json",
    "logging": "logging.json",
}


def _normalized_settings_payload(group: str, payload: dict) -> dict:
    return deepcopy(payload)


@router.get("")
def get_settings(context: AppContext = Depends(get_context)) -> dict:
    return context.settings.model_dump(mode="json")


@router.get("/{group}")
def get_settings_group(group: str, context: AppContext = Depends(get_context)) -> dict:
    if group not in SETTINGS_FILES:
        raise ConfigError(f"找不到設定群組：{group}")
    return _normalized_settings_payload(
        group,
        read_json_file(get_config_dir() / SETTINGS_FILES[group]),
    )


@router.post("/reset")
def reset_settings() -> dict:
    return {"detail": "為了硬體安全，重設必須手動執行。"}


@router.post("/{group}")
def update_settings_group(
    group: str,
    update: SettingsGroupUpdate,
    context: AppContext = Depends(get_context),
) -> dict:
    with context._settings_lock:
        if group not in SETTINGS_FILES:
            raise ConfigError(f"找不到設定群組：{group}")
        config_path = get_config_dir() / SETTINGS_FILES[group]
        previous_payload = read_json_file(config_path)
        normalized_payload = _normalized_settings_payload(group, update.payload)
        candidate = build_candidate_settings(context, group, normalized_payload)

        save_settings_group(group, normalized_payload)
        try:
            apply_runtime_settings(context, candidate, group)
        except Exception:
            try:
                save_settings_group(group, previous_payload)
            except Exception as rollback_error:
                logger.exception("Failed to restore settings file: %s", config_path)
                raise ConfigError("設定套用失敗，且無法還原原設定檔。") from rollback_error
            raise

        try:
            SettingsRepository(context.database).snapshot(group, normalized_payload)
        except Exception:
            logger.exception("Failed to record settings snapshot: %s", group)
    return {"updated": group, "applied": True}
