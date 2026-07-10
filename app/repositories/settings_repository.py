from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.database.connection import Database


class SettingsRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def snapshot(self, group_name: str, payload: dict[str, Any]) -> None:
        self.database.execute(
            """
            INSERT INTO settings_snapshots(created_at, group_name, payload_json)
            VALUES (?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                group_name,
                json.dumps(payload, ensure_ascii=False),
            ),
        )
