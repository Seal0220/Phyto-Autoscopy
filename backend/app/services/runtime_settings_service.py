from __future__ import annotations

import logging

from pydantic import ValidationError

from app.core.config import AppSettings, deep_merge
from app.core.exceptions import ConfigError
from app.core.logging_config import configure_logging
from app.core.state import AppContext
from app.hardware.motor.motor_profile import MotorProfile
from app.hardware.motor.motor_safety import MotorSafety
from app.services.schedule_lock import ensure_manual_changes_allowed

logger = logging.getLogger(__name__)


def build_candidate_settings(context: AppContext, group: str, payload: dict) -> AppSettings:
    """Validate a settings group against the complete running configuration."""
    current = context.settings.model_dump(mode="python")
    if group == "default":
        candidate_data = deep_merge(current, payload)
    elif group in {"cameras", "motor", "schedule", "logging"}:
        candidate_data = current
        candidate_data[group] = payload.get(group, {})
    else:
        raise ConfigError(f"找不到設定群組：{group}")
    try:
        return AppSettings.model_validate(candidate_data)
    except ValidationError as exc:
        raise ConfigError("設定內容格式錯誤，請檢查欄位與數值範圍。") from exc


def _assign_settings(target: AppSettings, source: AppSettings) -> None:
    for name in AppSettings.model_fields:
        setattr(target, name, getattr(source, name))


def _apply_runtime_dependencies(context: AppContext, group: str) -> None:
    if group == "default":
        context.storage_service.ensure_base_dirs()

    if group in {"cameras", "default"}:
        context.camera_manager.settings = context.settings
        reconfigure = getattr(context.camera_manager, "reconfigure", None)
        if reconfigure is not None:
            reconfigure()
        else:
            context.camera_manager.scan()

    if group in {"motor", "default"}:
        controller = context.motor_controller
        controller.settings = context.settings.motor
        controller.safety = MotorSafety(context.settings.motor)
        if hasattr(controller, "profile"):
            controller.profile = MotorProfile(context.settings.motor)
        if hasattr(controller, "_apply_profile"):
            controller._apply_profile()

    if group in {"logging", "default"}:
        configure_logging(context.settings)


def apply_runtime_settings(context: AppContext, candidate: AppSettings, group: str) -> None:
    """Apply settings transactionally to all long-lived runtime dependencies."""
    with context._settings_lock:
        ensure_manual_changes_allowed(context)
        if group == "motor" and context.motor_controller.status().moving:
            raise ConfigError("馬達移動中，不能更新馬達設定。")

        previous = AppSettings.model_validate(
            context.settings.model_dump(mode="python")
        )
        if group == "default" and previous.hardware.mock_mode != candidate.hardware.mock_mode:
            raise ConfigError("硬體模式無法在服務執行中切換，請手動重新啟動服務。")
        if group == "default" and previous.paths.database_path != candidate.paths.database_path:
            raise ConfigError("資料庫位置無法在服務執行中切換，請手動重新啟動服務。")
        paths_changed = (
            group == "default"
            and previous.paths.model_dump() != candidate.paths.model_dump()
        )
        active_record_id = (
            context.record_service.active_record_id
            if paths_changed
            else None
        )

        try:
            # Preserve the AppSettings object identity because every service holds it.
            _assign_settings(context.settings, candidate)
            _apply_runtime_dependencies(context, group)
            if active_record_id:
                context.record_service.update_status(
                    active_record_id,
                    "completed",
                )
        except Exception as exc:
            _assign_settings(context.settings, previous)
            try:
                _apply_runtime_dependencies(context, group)
            except Exception:
                logger.exception("Failed to restore runtime settings after apply failure")
            raise ConfigError("套用設定失敗，已還原原設定。") from exc
