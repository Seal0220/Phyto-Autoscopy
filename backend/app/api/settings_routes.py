from __future__ import annotations

import logging
from copy import deepcopy

from fastapi import APIRouter, Depends
from pydantic import ValidationError

from app.core.config import (
    AppSettings,
    get_config_dir,
    read_json_file,
    save_settings_group,
)
from app.core.exceptions import ConfigError
from app.core.state import AppContext, get_context
from app.models.settings_models import SettingsBatchUpdate, SettingsGroupUpdate
from app.repositories.settings_repository import SettingsRepository
from app.services.runtime_settings_service import apply_runtime_settings, build_candidate_settings
from app.services.schedule_lock import ensure_manual_changes_allowed

router = APIRouter(prefix="/api/settings", tags=["settings"])
logger = logging.getLogger(__name__)

SETTINGS_FILES = {
    "default": "default.json",
    "cameras": "cameras.json",
    "motor": "motor.json",
    "schedule": "schedule.json",
    "analysis": "analysis.json",
    "calibration": "calibration.json",
    "pose_alignment": "pose_alignment.json",
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
    payload = _normalized_settings_payload(
        group,
        read_json_file(get_config_dir() / SETTINGS_FILES[group]),
    )
    if group == "default":
        payload["paths"] = context.settings.paths.model_dump(mode="json")
    return payload


@router.post("/reset")
def reset_settings() -> dict:
    return {"detail": "為了硬體安全，重設必須手動執行。"}


@router.post("/batch")
def update_settings_batch(
    update: SettingsBatchUpdate,
    context: AppContext = Depends(get_context),
) -> dict:
    groups = set(update.payloads)
    if groups != {"cameras", "schedule"}:
        raise ConfigError("批次設定只接受攝影機與排程設定。")

    ensure_manual_changes_allowed(context)
    with context._settings_lock:
        previous_payloads = {
            group: read_json_file(get_config_dir() / SETTINGS_FILES[group])
            for group in groups
        }
        candidate_data = context.settings.model_dump(mode="python")
        for group, payload in update.payloads.items():
            candidate_data[group] = payload.get(group, {})

        try:
            candidate = AppSettings.model_validate(candidate_data)
        except ValidationError as exc:
            raise ConfigError("設定內容格式錯誤，請檢查欄位與數值範圍。") from exc

        saved_groups: list[str] = []
        try:
            for group, payload in update.payloads.items():
                save_settings_group(group, payload)
                saved_groups.append(group)
            apply_runtime_settings(context, candidate, "schedule")
        except Exception:
            for group in reversed(saved_groups):
                try:
                    save_settings_group(group, previous_payloads[group])
                except Exception:
                    logger.exception("Failed to restore settings group: %s", group)
            raise

        for group, payload in update.payloads.items():
            try:
                SettingsRepository(context.database).snapshot(group, payload)
            except Exception:
                logger.exception("Failed to record settings snapshot: %s", group)

    return {
        "updated": sorted(groups),
        "applied": True,
    }


@router.post("/{group}")
def update_settings_group(
    group: str,
    update: SettingsGroupUpdate,
    context: AppContext = Depends(get_context),
) -> dict:
    ensure_manual_changes_allowed(context)
    with context._settings_lock:
        if group not in SETTINGS_FILES:
            raise ConfigError(f"找不到設定群組：{group}")
        config_path = get_config_dir() / SETTINGS_FILES[group]
        previous_payload = read_json_file(config_path)
        normalized_payload = _normalized_settings_payload(group, update.payload)
        candidate = build_candidate_settings(context, group, normalized_payload)
        if group == "default":
            normalized_payload["paths"] = candidate.paths.model_dump(mode="json")

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
    return {
        "updated": group,
        "applied": True,
        "payload": normalized_payload,
    }
