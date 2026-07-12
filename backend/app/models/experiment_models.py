from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SecondsIntervalMode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    type: Literal["seconds_interval"]
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
    SecondsIntervalMode | AngleIntervalMode | SpecificAnglesMode | EqualDivisionsMode,
    Field(discriminator="type"),
]


class ExperimentPlan(BaseModel):
    duration_seconds: float = Field(gt=0)
    rotation_start_deg: float
    rotation_end_deg: float
    rotation_step_deg: float = Field(gt=0)
    angle_tolerance_deg: float = Field(ge=0)
    modes: list[CaptureMode] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_plan(self):
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


class ExperimentStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duration_seconds: float | None = Field(default=None, gt=0)
    rotation_start_deg: float | None = None
    rotation_end_deg: float | None = None
    rotation_step_deg: float | None = Field(default=None, gt=0)
    angle_tolerance_deg: float | None = Field(default=None, ge=0)
    modes: list[CaptureMode] = Field(default_factory=list, max_length=20)


class ModeProgress(BaseModel):
    id: str
    type: str
    capture_count: int = 0


class ExperimentStatus(BaseModel):
    status: str
    session_id: str | None = None
    cycle_count: int = 0
    last_error: str | None = None
    elapsed_seconds: float = 0
    duration_seconds: float | None = None
    current_angle_deg: float | None = None
    current_step_index: int = 0
    total_steps: int = 0
    capture_count: int = 0
    mode_progress: list[ModeProgress] = Field(default_factory=list)
