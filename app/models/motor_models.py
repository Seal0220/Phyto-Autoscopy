from __future__ import annotations

from pydantic import BaseModel, Field


class MotorStatus(BaseModel):
    name: str
    controller: str
    connected: bool
    engaged: bool
    moving: bool
    emergency_stopped: bool
    command_position_deg: float
    origin_deg: float
    minimum_angle_deg: float
    maximum_angle_deg: float
    velocity_limit_deg_s: float
    acceleration_deg_s2: float
    current_limit_amp: float
    holding_current_amp: float
    last_error: str | None = None


class MoveRequest(BaseModel):
    angle_deg: float = Field(ge=-3600, le=3600)


class MotorSettingsUpdate(BaseModel):
    current_limit_amp: float | None = Field(default=None, gt=0)
    holding_current_amp: float | None = Field(default=None, ge=0)
    velocity_limit_deg_s: float | None = Field(default=None, gt=0)
    acceleration_deg_s2: float | None = Field(default=None, gt=0)
