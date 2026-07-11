from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SettingsGroupUpdate(BaseModel):
    payload: dict[str, Any]
