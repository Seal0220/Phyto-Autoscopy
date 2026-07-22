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
    model_config = ConfigDict(extra="ignore")

    captures_dir: Path = Path("data/captures")
    snapshots_dir: Path = Path("data/snapshots")
    calibration_dir: Path = Path("data/calibration")
    analysis_dir: Path = Path("data/analysis")
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
    capture_interval_seconds: float = Field(default=60.0, gt=0)
    duration_seconds: float = Field(default=14400.0, gt=0)
    total_cycles: int = Field(default=48, ge=1)
    cycle_duration_seconds: float = Field(default=300.0, gt=0)
    cycle_interval_seconds: float = Field(default=0.0, ge=0)
    rotation_enabled: bool = True
    rotation_start_deg: float = 0.0
    rotation_end_deg: float = 360.0
    rotation_step_deg: float = 1.0
    angle_tolerance_deg: float = 0.5
    stabilization_delay_ms: int = 800
    capture_on_return: bool = True
    return_to_origin: bool = True


class AnalysisMethodSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["top_side"] = "top_side"
    reference: str = "Ruiz-Melero et al. 2024"


class SynchronizationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_key: Literal["cycle_id"] = "cycle_id"
    timestamp_tolerance_ms: int = Field(default=1000, ge=0)
    manual_frame_offset: int = 0
    keep_unpaired_frames: bool = True


class SegmentationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal["mog2"] = "mog2"
    history: int | None = Field(default=None, ge=1)
    variance_threshold: float | None = Field(default=None, gt=0)
    detect_shadows: bool = False
    learning_rate: float | None = Field(default=None, ge=-1, le=1)
    initialization_frames: int | None = Field(default=None, ge=1)
    opening_kernel_size: int | None = Field(default=None, ge=1)
    closing_kernel_size: int | None = Field(default=None, ge=1)
    erosion_kernel_size: int | None = Field(default=None, ge=1)
    minimum_top_contour_area_px: float | None = Field(default=None, ge=0)
    minimum_side_contour_area_px: float | None = Field(default=None, ge=0)

    @field_validator(
        "opening_kernel_size",
        "closing_kernel_size",
        "erosion_kernel_size",
    )
    @classmethod
    def kernel_must_be_odd(cls, value: int | None) -> int | None:
        if value is not None and value % 2 == 0:
            raise ValueError("Morphology kernel 大小必須是正奇數。")
        return value


class LightingChangeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lighting_change_area_px: float | None = Field(default=None, ge=0)
    lighting_change_est_time_frames: int | None = Field(default=None, ge=1)


class DetectionRoiSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roi: list[int] | None = None
    plant_base: list[float] | None = None
    num_selected_points: int | None = Field(default=None, ge=1)
    update_roi: bool = True
    roi_update_margin_px: int | None = Field(default=None, ge=0)

    @field_validator("roi")
    @classmethod
    def validate_roi(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return value
        if len(value) != 4:
            raise ValueError("ROI 必須為 [x, y, width, height]。")
        if value[0] < 0 or value[1] < 0 or value[2] <= 0 or value[3] <= 0:
            raise ValueError("ROI 位置不可為負值，且寬高必須大於零。")
        return value

    @field_validator("plant_base")
    @classmethod
    def validate_plant_base(
        cls,
        value: list[float] | None,
    ) -> list[float] | None:
        if value is not None and len(value) != 2:
            raise ValueError("植物基部必須為 [x, y]。")
        return value


class SideDetectionSettings(DetectionRoiSettings):
    maximum_epipolar_distance_px: float | None = Field(default=None, gt=0)
    minimum_path_connectivity: Literal[4, 8] | None = None
    minimum_path_edge_weight: Literal["inverse_distance_transform"] | None = None


class InterpolationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal["linear"] = "linear"
    maximum_gap_seconds: float | None = Field(default=None, gt=0)


class ReprojectionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    high_error_threshold_px: float = Field(
        default=10.0,
        ge=10.0,
        le=10.0,
    )


class AnalysisSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: AnalysisMethodSettings = Field(default_factory=AnalysisMethodSettings)
    synchronization: SynchronizationSettings = Field(default_factory=SynchronizationSettings)
    segmentation: SegmentationSettings = Field(default_factory=SegmentationSettings)
    lighting_change: LightingChangeSettings = Field(default_factory=LightingChangeSettings)
    top_detection: DetectionRoiSettings = Field(default_factory=DetectionRoiSettings)
    side_detection: SideDetectionSettings = Field(default_factory=SideDetectionSettings)
    interpolation: InterpolationSettings = Field(default_factory=InterpolationSettings)
    reprojection: ReprojectionSettings = Field(default_factory=ReprojectionSettings)


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
        "calibration.json",
        "pose_alignment.json",
        "logging.json",
    ):
        data = deep_merge(data, read_json_file(root / file_name))

    mock_mode = os.environ.get("PHYTO_AUTOSCOPY_MOCK")
    if mock_mode is not None:
        data.setdefault("hardware", {})["mock_mode"] = _truthy(mock_mode)

    return AppSettings.model_validate(data)


def save_settings_group(group: str, payload: dict[str, Any], config_dir: str | Path | None = None) -> None:
    file_map = {
        "cameras": "cameras.json",
        "motor": "motor.json",
        "schedule": "schedule.json",
        "analysis": "analysis.json",
        "calibration": "calibration.json",
        "pose_alignment": "pose_alignment.json",
        "logging": "logging.json",
        "default": "default.json",
    }
    if group not in file_map:
        raise ConfigError(f"找不到設定群組：{group}")

    root = get_config_dir(config_dir)
    write_json_file(root / file_map[group], payload)
