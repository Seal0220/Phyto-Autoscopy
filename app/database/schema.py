from __future__ import annotations

from app.database.connection import Database


def initialize_schema(database: Database) -> None:
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL,
            session_path TEXT NOT NULL
        )
        """
    )
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS captures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            cycle_id INTEGER,
            camera_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            angle_deg REAL,
            motor_position_deg REAL,
            file_path TEXT NOT NULL,
            status TEXT NOT NULL,
            error_message TEXT,
            FOREIGN KEY(session_id) REFERENCES sessions(session_id)
        )
        """
    )
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS settings_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            group_name TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
