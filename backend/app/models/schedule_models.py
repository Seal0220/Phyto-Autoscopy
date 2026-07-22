from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TimeIntervalMode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    type: Literal["time_interval"]
    interval_seconds: float = Field(gt=0)


class ContinuousIntervalMode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    type: Literal["continuous_interval"]
    interval_seconds: float = Field(gt=0)


class AngleIntervalMode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    type: Literal["angle_interval"]
    interval_degrees: float = Field(gt=0)


class SpecificAnglesMode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    type: Literal["specific_angles"]
    angles: list[float] = Field(min_length=1)

    @field_validator("angles", mode="before")
    @classmethod
    def parse_comma_separated_angles(cls, value):
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value


class EqualDivisionsMode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    type: Literal["equal_divisions"]
    points: int = Field(ge=2, le=10000)


CaptureMode = Annotated[
    ContinuousIntervalMode
    | TimeIntervalMode
    | AngleIntervalMode
    | SpecificAnglesMode
    | EqualDivisionsMode,
    Field(discriminator="type"),
]


class SchedulePlan(BaseModel):
    rotation_enabled: bool = True
    duration_seconds: float = Field(gt=0)
    total_cycles: int | None = Field(default=None, ge=1)
    cycle_duration_seconds: float | None = Field(default=None, gt=0)
    cycle_interval_seconds: float = Field(default=0.0, ge=0)
    rotation_start_deg: float
    rotation_end_deg: float
    rotation_step_deg: float = Field(gt=0)
    angle_tolerance_deg: float = Field(ge=0)
    stabilization_delay_ms: int = Field(default=800, ge=0, le=60000)
    capture_on_return: bool
    return_to_origin: bool = True
    modes: list[CaptureMode] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_plan(self):
        if self.rotation_enabled:
            if self.total_cycles is None or self.cycle_duration_seconds is None:
                raise ValueError("啟用旋臂時必須設定總輪數與每輪時長。")
        elif any(
            not isinstance(mode, ContinuousIntervalMode)
            for mode in self.modes
        ):
            raise ValueError("未啟用旋臂時只能使用連續間隔擷取模式。")
        if self.rotation_end_deg < self.rotation_start_deg:
            raise ValueError("結束角度不可小於起始角度。")
        mode_ids = [mode.id for mode in self.modes]
        if len(mode_ids) != len(set(mode_ids)):
            raise ValueError("每個擷取模式的識別碼必須唯一。")
        for mode in self.modes:
            if isinstance(mode, SpecificAnglesMode):
                outside = [
                    angle
                    for angle in mode.angles
                    if angle < self.rotation_start_deg or angle > self.rotation_end_deg
                ]
                if outside:
                    raise ValueError(
                        "特定擷取角度必須位於共用起始與結束角度範圍內。"
                    )
        return self


class ScheduleStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rotation_enabled: bool | None = None
    duration_seconds: float | None = Field(default=None, gt=0)
    total_cycles: int | None = Field(default=None, ge=1)
    cycle_duration_seconds: float | None = Field(default=None, gt=0)
    cycle_interval_seconds: float | None = Field(default=None, ge=0)
    rotation_start_deg: float | None = None
    rotation_end_deg: float | None = None
    angle_tolerance_deg: float | None = Field(default=None, ge=0)
    stabilization_delay_ms: int | None = Field(
        default=None,
        ge=0,
        le=60000,
    )
    capture_on_return: bool | None = None
    return_to_origin: bool | None = None
    modes: list[CaptureMode] = Field(default_factory=list, max_length=20)


class ModeProgress(BaseModel):
    id: str
    type: str
    capture_count: int = 0


class ScheduleStatus(BaseModel):
    status: str
    rotation_enabled: bool = False
    record_id: str | None = None
    cycle_count: int = 0
    total_cycles: int | None = None
    cycle_duration_seconds: float | None = None
    rotation_step_deg: float | None = None
    last_error: str | None = None
    elapsed_seconds: float = 0
    duration_seconds: float | None = None
    current_angle_deg: float | None = None
    current_step_index: int = 0
    total_steps: int = 0
    capture_count: int = 0
    mode_progress: list[ModeProgress] = Field(default_factory=list)
