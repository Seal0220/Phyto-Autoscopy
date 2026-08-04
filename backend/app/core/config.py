from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

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
    model_config = ConfigDict(
        extra="ignore",
        validate_default=True,
    )

    captures_dir: Path = Path("data/captures")
    snapshots_dir: Path = Path("data/snapshots")
    calibration_dir: Path = Path("data/calibration")
    analysis_dir: Path = Path("data/analysis")
    database_path: Path = Path("data/database/phyto_autoscopy.sqlite3")
    logs_dir: Path = Path("data/logs")
    temp_dir: Path = Path("data/temp")

    @field_validator(
        "captures_dir",
        "snapshots_dir",
        "calibration_dir",
        "analysis_dir",
        "database_path",
        "logs_dir",
        "temp_dir",
        mode="before",
    )
    @classmethod
    def normalize_path(cls, value: str | Path) -> Path:
        path = Path(value).expanduser()
        if not path.parts or ".." in path.parts:
            raise ValueError("資料路徑不可為空白或包含上層目錄。")
        return path


def path_settings_config_payload(
    settings: PathSettings,
) -> dict[str, str]:
    payload: dict[str, str] = {}
    for field_name in PathSettings.model_fields:
        path = getattr(settings, field_name)
        if path.is_absolute():
            raise ConfigError("所有資料儲存位置都必須使用專案相對路徑。")
        payload[field_name] = path.as_posix()
    return payload


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
    installation_height_mm: float | None = Field(
        default=None,
        ge=0,
        le=10000,
    )
    horizontal_distance_to_origin_mm: float | None = Field(
        default=None,
        ge=0,
        le=10000,
    )
    arm_height_mm: float | None = Field(
        default=None,
        ge=0,
        le=10000,
    )


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
    gear_ratio: float = Field(default=1.0, gt=0)
    current_limit_amp: float = 1.5
    maximum_current_limit_amp: float = 2.4
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
    capture_interval_seconds: float = Field(default=60.0, gt=0)
    duration_seconds: float = Field(default=14400.0, gt=0)
    total_cycles: int = Field(default=48, ge=1)
    cycle_interval_seconds: float = Field(default=0.0, ge=0)
    rotation_enabled: bool = True
    rotation_start_deg: float = 0.0
    rotation_end_deg: float = 355.0
    rotation_step_deg: float = 1.0
    angle_tolerance_deg: float = 0.5
    stabilization_delay_ms: int = 800
    capture_on_return: bool = True
    return_to_origin: bool = True


class AnalysisSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ReconstructionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: Literal["gsplat_3dgs", "graphdeco_3dgs"] = "gsplat_3dgs"
    available_backends: list[Literal["gsplat_3dgs", "graphdeco_3dgs"]] = Field(
        default_factory=lambda: ["gsplat_3dgs", "graphdeco_3dgs"]
    )
    device: Literal["cuda"] = "cuda"
    fallback_device: None = None
    quality_preset: Literal["preview", "standard", "high"] = "standard"
    save_checkpoint: bool = True
    export_gaussians: bool = True
    export_point_cloud: bool = True
    export_plant_point_cloud: bool = True
    export_render_preview: bool = True
    use_pose_refinement: bool = True
    use_plant_mask: bool = True


class CalibrationQualitySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_error_per_image: bool = True
    store_point_coverage: bool = True


class CalibrationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quality: CalibrationQualitySettings = Field(default_factory=CalibrationQualitySettings)


class ArucoMarkerCenterSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x_mm: float
    y_mm: float
    z_mm: float = 0.0
    orientation_deg: float = Field(default=0.0, ge=-360.0, le=360.0)


class ArucoWorldReferenceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dictionary: Literal[
        "DICT_4X4_50",
        "DICT_5X5_100",
        "DICT_6X6_250",
        "DICT_7X7_250",
    ] = "DICT_5X5_100"
    left_rear_id: int = Field(default=0, ge=0, le=9999)
    right_rear_id: int = Field(default=1, ge=0, le=9999)
    left_front_id: int = Field(default=2, ge=0, le=9999)
    right_front_id: int = Field(default=3, ge=0, le=9999)
    marker_size_mm: float = Field(default=50.0, gt=0, le=1000)
    left_right_center_distance_mm: float = Field(default=300.0, gt=0, le=10000)
    rear_front_center_distance_mm: float = Field(default=300.0, gt=0, le=10000)
    marker_orientation_deg: float = Field(default=0.0, ge=-360.0, le=360.0)
    world_origin: Literal[
        "layout_center",
        "left_rear",
        "right_rear",
        "left_front",
        "right_front",
    ] = "layout_center"
    x_axis_direction: Literal["right", "left"] = "right"
    y_axis_direction: Literal["front", "rear"] = "front"
    z_axis_direction: Literal["up", "down"] = "up"
    advanced_mode: bool = False
    marker_centers_world_mm: dict[str, ArucoMarkerCenterSettings] = Field(
        default_factory=dict
    )

    @model_validator(mode="after")
    def validate_world_reference(self) -> "ArucoWorldReferenceSettings":
        marker_ids = (
            self.left_rear_id,
            self.right_rear_id,
            self.left_front_id,
            self.right_front_id,
        )
        if len(set(marker_ids)) != 4:
            raise ValueError("四個 ArUco marker ID 不可重複。")
        if not self.dictionary.startswith("DICT_"):
            raise ValueError("ArUco dictionary 名稱格式無效。")
        capacity_text = self.dictionary.rsplit("_", 1)[-1]
        if capacity_text.isdigit():
            capacity = int(capacity_text)
            if any(marker_id >= capacity for marker_id in marker_ids):
                raise ValueError(
                    f"{self.dictionary} 的 marker ID 必須小於 {capacity}。"
                )
        required_positions = {
            "left_rear",
            "right_rear",
            "left_front",
            "right_front",
        }
        unknown_positions = set(self.marker_centers_world_mm).difference(
            required_positions
        )
        if unknown_positions:
            raise ValueError("進階 marker 世界座標包含未知位置。")
        if self.advanced_mode and set(self.marker_centers_world_mm) != required_positions:
            raise ValueError("進階模式必須指定四個 marker 中心的世界座標。")
        return self


class PoseAlignmentSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aruco_world: ArucoWorldReferenceSettings = Field(
        default_factory=ArucoWorldReferenceSettings
    )
    minimum_pnp_inliers: int = Field(default=4, ge=4, le=10000)
    maximum_aruco_reprojection_error_px: float = Field(
        default=5.0,
        gt=0,
        le=100,
    )
    minimum_sfm_matches: int = Field(default=16, ge=8, le=10000)
    pose_estimation_version: str = Field(
        default="aruco_world_v2",
        min_length=1,
        max_length=64,
    )


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
    analysis: AnalysisSettings = Field(default_factory=AnalysisSettings)
    reconstruction: ReconstructionSettings = Field(
        default_factory=ReconstructionSettings
    )
    calibration: CalibrationSettings = Field(default_factory=CalibrationSettings)
    pose_alignment: PoseAlignmentSettings = Field(default_factory=PoseAlignmentSettings)
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
            if config.device_index is None:
                if not config.enabled:
                    continue
                raise ValueError(
                    f"已啟用相機必須選擇裝置：{camera_id}"
                )
            previous = enabled_indices.get(config.device_index)
            if previous is not None:
                raise ValueError(
                    "相機不可共用裝置索引："
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

    for file_name in (
        "schedule.json",
        "analysis.json",
        "reconstruction.json",
        "calibration.json",
        "pose_alignment.json",
        "logging.json",
    ):
        data = deep_merge(data, read_json_file(root / file_name))

    mock_mode = os.environ.get("PHYTO_AUTOSCOPY_MOCK")
    if mock_mode is not None:
        data.setdefault("hardware", {})["mock_mode"] = _truthy(mock_mode)

    settings = AppSettings.model_validate(data)
    path_settings_config_payload(settings.paths)
    return settings


def save_settings_group(group: str, payload: dict[str, Any], config_dir: str | Path | None = None) -> None:
    file_map = {
        "cameras": "cameras.json",
        "motor": "motor.json",
        "schedule": "schedule.json",
        "analysis": "analysis.json",
        "reconstruction": "reconstruction.json",
        "calibration": "calibration.json",
        "pose_alignment": "pose_alignment.json",
        "logging": "logging.json",
        "default": "default.json",
    }
    if group not in file_map:
        raise ConfigError(f"找不到設定群組：{group}")

    root = get_config_dir(config_dir)
    write_json_file(root / file_map[group], payload)
