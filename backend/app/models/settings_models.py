from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SettingsGroupUpdate(BaseModel):
    payload: dict[str, Any]


class SettingsBatchUpdate(BaseModel):
    payloads: dict[str, dict[str, Any]] = Field(min_length=1, max_length=8)
