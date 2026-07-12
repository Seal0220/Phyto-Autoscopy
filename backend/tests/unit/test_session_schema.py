from __future__ import annotations

from app.database.connection import Database
from app.database.schema import initialize_schema


def test_initialize_schema_adds_ended_at_to_existing_sessions(tmp_path) -> None:
    database = Database(tmp_path / "legacy.sqlite3")
    database.execute(
        """
        CREATE TABLE sessions (
            session_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL,
            session_path TEXT NOT NULL
        )
        """
    )

    initialize_schema(database)

    columns = {
        row["name"]
        for row in database.fetchall("PRAGMA table_info(sessions)")
    }
    assert "ended_at" in columns
    database.close()
