from __future__ import annotations

from app.core.config import AppSettings, deep_merge
from app.core.exceptions import ConfigError
from app.core.logging_config import configure_logging
from app.core.state import AppContext
from app.hardware.motor.motor_profile import MotorProfile
from app.hardware.motor.motor_safety import MotorSafety


def build_candidate_settings(context: AppContext, group: str, payload: dict) -> AppSettings:
    """Validate a settings group against the complete running configuration."""
    current = context.settings.model_dump(mode="python")
    if group == "default":
        candidate_data = deep_merge(current, payload)
    elif group in {"cameras", "motor", "experiment", "logging"}:
        candidate_data = current
        candidate_data[group] = payload.get(group, {})
    else:
        raise ConfigError(f"Unknown settings group: {group}")
    return AppSettings.model_validate(candidate_data)


def apply_runtime_settings(context: AppContext, candidate: AppSettings, group: str) -> None:
    """Apply validated configuration to the objects already serving requests."""
    if group == "motor" and context.motor_controller.status().moving:
        raise ConfigError("馬達移動中，不能更新馬達設定。")

    # Keep the original AppSettings instance: all long-lived services reference it.
    for name in AppSettings.model_fields:
        setattr(context.settings, name, getattr(candidate, name))

    if group in {"cameras", "default"}:
        context.camera_manager.settings = context.settings
        # Device index and enabled state take effect immediately in the live status.
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
