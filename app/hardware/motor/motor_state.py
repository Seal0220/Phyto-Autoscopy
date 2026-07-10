from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MotorRuntimeState:
    connected: bool = False
    engaged: bool = False
    moving: bool = False
    emergency_stopped: bool = False
    command_position_deg: float = 0.0
    last_error: str | None = None
