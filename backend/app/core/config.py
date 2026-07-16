from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.constants import CAMERA_ROLES
from app.core.exceptions import ConfigError


BACKEND_ROOT = Path(__file__).resolve().parents[2]


class ProjectSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = "Phyto-Autoscopy"
    name_zh: str = "綠色自視症"
    device_name: str = "CHLOROCULUS"
    device_version: str = "0.1"


class HardwareSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mock_mode: bool = False
    camera_scan_max_index: int = Field(default=10, ge=1, le=64)


class PathSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    captures_dir: Path = Path("data/captures")
    snapshots_dir: Path = Path("data/snapshots")
    calibration_dir: Path = Path("data/calibration")
    database_path: Path = Path("data/database/phyto_autoscopy.sqlite3")
    logs_dir: Path = Path("data/logs")
    temp_dir: Path = Path("data/temp")


class CameraConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    device_name: str
    device_index: int | None = Field(default=None, ge=0)
    width: int = 1280
    height: int = 960
    preview_fps: int = Field(default=5, ge=1, le=60)
    capture_fps: int = Field(default=10, ge=1, le=60)
    jpeg_quality: int = 95
    enabled: bool = True


def default_camera_configs() -> dict[str, CameraConfig]:
    return {
        "top": CameraConfig(
            device_name="CHLOROCULUS EYE-TOP",
            device_index=0,
        ),
        "side": CameraConfig(
            device_name="CHLOROCULUS EYE-SIDE",
            device_index=1,
        ),
        "rotating": CameraConfig(
            device_name="CHLOROCULUS EYE-ARM",
            device_index=2,
        ),
    }


class MotorSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = "CHLOROCULUS_ARM_MOTOR"
    controller: str = "phidget_stepper_bipolar_hc"
    full_step_angle_deg: float = 0.9
    microstep_division: int = 16
    current_limit_amp: float = 1.5
    maximum_current_limit_amp: float = 2.4
    holding_current_amp: float = 0.3
    velocity_limit_deg_s: float = 3.0
    maximum_velocity_limit_deg_s: float = 6.0
    acceleration_deg_s2: float = 3.0
    maximum_acceleration_deg_s2: float = 6.0
    minimum_angle_deg: float = 0.0
    maximum_angle_deg: float = 360.0
    movement_timeout_seconds: int = 180
    stabilization_delay_ms: int = 800

    @field_validator("maximum_angle_deg")
    @classmethod
    def maximum_must_exceed_minimum(cls, value: float, info: Any) -> float:
        minimum = info.data.get("minimum_angle_deg", 0.0)
        if value <= minimum:
            raise ValueError("最大角度必須大於最小角度。")
        return value


class ScheduleSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    project_name: str = "Phyto-Autoscopy"
    project_name_zh: str = "綠色自視症"
    device_name: str = "CHLOROCULUS"
    capture_interval_seconds: int = 60
    duration_minutes: int = 240
    capture_top: bool = True
    capture_side: bool = True
    capture_rotating: bool = True
    rotation_enabled: bool = True
    rotation_start_deg: float = 0.0
    rotation_end_deg: float = 360.0
    rotation_step_deg: float = 1.0
    angle_tolerance_deg: float = 0.5
    stabilization_delay_ms: int = 800
    capture_on_return: bool = True
    return_to_origin: bool = True


class LoggingSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    level: str = "INFO"
    file_name: str = "phyto_autoscopy.log"


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    project: ProjectSettings = Field(default_factory=ProjectSettings)
    hardware: HardwareSettings = Field(default_factory=HardwareSettings)
    paths: PathSettings = Field(default_factory=PathSettings)
    cameras: dict[str, CameraConfig] = Field(default_factory=default_camera_configs)
    motor: MotorSettings = Field(default_factory=MotorSettings)
    schedule: ScheduleSettings = Field(default_factory=ScheduleSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    @field_validator("cameras")
    @classmethod
    def require_camera_roles(
        cls,
        value: dict[str, CameraConfig],
    ) -> dict[str, CameraConfig]:
        required = set(CAMERA_ROLES)
        missing = sorted(required.difference(value))
        if missing:
            raise ValueError(f"缺少必要相機設定：{', '.join(missing)}")
        enabled_indices: dict[int, str] = {}
        for camera_id, config in value.items():
            if not config.enabled:
                continue
            if config.device_index is None:
                raise ValueError(
                    f"已啟用相機必須選擇裝置：{camera_id}"
                )
            previous = enabled_indices.get(config.device_index)
            if previous is not None:
                raise ValueError(
                    "已啟用相機不可共用裝置索引："
                    f"{previous} 與 {camera_id} 都使用 {config.device_index}"
                )
            enabled_indices[config.device_index] = camera_id
        return value


def _truthy(value: str | None) -> bool:
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on"}


def read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"找不到設定檔：{path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"設定檔格式錯誤：{path}") from exc
    except (OSError, UnicodeError) as exc:
        raise ConfigError(f"無法讀取設定檔：{path}") from exc


def write_json_file(path: Path, payload: dict[str, Any]) -> None:
    temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(path)
    except (OSError, TypeError, ValueError) as exc:
        raise ConfigError(f"無法儲存設定檔：{path}") from exc
    finally:
        temporary_path.unlink(missing_ok=True)


def deep_merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def get_config_dir(config_dir: str | Path | None = None) -> Path:
    configured = config_dir or os.environ.get("PHYTO_AUTOSCOPY_CONFIG_DIR") or "config"
    path = Path(configured)
    return path if path.is_absolute() else BACKEND_ROOT / path


def load_settings(config_dir: str | Path | None = None) -> AppSettings:
    root = get_config_dir(config_dir)
    data = read_json_file(root / "default.json")

    for file_name in ("cameras.json", "motor.json"):
        data = deep_merge(data, read_json_file(root / file_name))

    data = deep_merge(data, read_json_file(root / "schedule.json"))
    data = deep_merge(data, read_json_file(root / "logging.json"))

    mock_mode = os.environ.get("PHYTO_AUTOSCOPY_MOCK")
    if mock_mode is not None:
        data.setdefault("hardware", {})["mock_mode"] = _truthy(mock_mode)

    return AppSettings.model_validate(data)


def save_settings_group(group: str, payload: dict[str, Any], config_dir: str | Path | None = None) -> None:
    file_map = {
        "cameras": "cameras.json",
        "motor": "motor.json",
        "schedule": "schedule.json",
        "logging": "logging.json",
        "default": "default.json",
    }
    if group not in file_map:
        raise ConfigError(f"找不到設定群組：{group}")

    root = get_config_dir(config_dir)
    write_json_file(root / file_map[group], payload)
