from __future__ import annotations

import sqlite3

from app.database.connection import Database


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone() is not None


def _columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        row["name"]
        for row in connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    }


def _migrate_legacy_record_schema(connection: sqlite3.Connection) -> None:
    """Rename the former business-session schema without moving user files."""
    if _table_exists(connection, "sessions") and not _table_exists(connection, "records"):
        connection.execute("ALTER TABLE sessions RENAME TO records")

    if _table_exists(connection, "records"):
        record_columns = _columns(connection, "records")
        if "session_id" in record_columns and "record_id" not in record_columns:
            connection.execute(
                "ALTER TABLE records RENAME COLUMN session_id TO record_id"
            )
        record_columns = _columns(connection, "records")
        if "session_path" in record_columns and "record_path" not in record_columns:
            connection.execute(
                "ALTER TABLE records RENAME COLUMN session_path TO record_path"
            )

    if _table_exists(connection, "captures"):
        capture_columns = _columns(connection, "captures")
        if "session_id" in capture_columns and "record_id" not in capture_columns:
            connection.execute(
                "ALTER TABLE captures RENAME COLUMN session_id TO record_id"
            )


def initialize_schema(database: Database) -> None:
    with database.transaction() as connection:
        _migrate_legacy_record_schema(connection)

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS records (
                record_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL,
                record_path TEXT NOT NULL,
                ended_at TEXT
            )
            """
        )
        if "ended_at" not in _columns(connection, "records"):
            connection.execute("ALTER TABLE records ADD COLUMN ended_at TEXT")

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS captures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id TEXT NOT NULL,
                cycle_id INTEGER,
                camera_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                angle_deg REAL,
                motor_position_deg REAL,
                file_path TEXT NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT,
                FOREIGN KEY(record_id) REFERENCES records(record_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS settings_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                group_name TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
