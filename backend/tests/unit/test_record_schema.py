from __future__ import annotations

import pytest

import app.database.schema as schema_module
from app.database.connection import Database
from app.database.schema import initialize_schema


def test_initialize_schema_migrates_existing_records(tmp_path) -> None:
    database = Database(tmp_path / "legacy.sqlite3")
    database.execute(
        """
        CREATE TABLE records (
            record_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL,
            record_path TEXT NOT NULL
        )
        """
    )

    initialize_schema(database)

    columns = {
        row["name"]
        for row in database.fetchall("PRAGMA table_info(records)")
    }
    assert "ended_at" in columns
    database.close()


def test_initialize_schema_creates_new_record_schema(tmp_path) -> None:
    database = Database(tmp_path / "new.sqlite3")

    initialize_schema(database)

    record_columns = {
        row["name"] for row in database.fetchall("PRAGMA table_info(records)")
    }
    capture_columns = {
        row["name"] for row in database.fetchall("PRAGMA table_info(captures)")
    }
    assert {"record_id", "record_path", "ended_at"} <= record_columns
    assert "record_id" in capture_columns
    database.close()


def test_initialize_schema_migrates_legacy_rows_and_foreign_key(tmp_path) -> None:
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
    database.execute(
        """
        CREATE TABLE captures (
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
        "INSERT INTO sessions VALUES (?, ?, ?, ?)",
        ("session_legacy", "2026-01-01T00:00:00+08:00", "completed", "old/path"),
    )
    database.execute(
        """
        INSERT INTO captures(
            session_id, camera_id, timestamp, file_path, status
        ) VALUES (?, ?, ?, ?, ?)
        """,
        ("session_legacy", "top", "2026-01-01T00:00:01+08:00", "top/1.jpg", "success"),
    )

    initialize_schema(database)

    record = database.fetchone("SELECT * FROM records WHERE record_id=?", ("session_legacy",))
    capture = database.fetchone("SELECT * FROM captures WHERE record_id=?", ("session_legacy",))
    foreign_keys = database.fetchall("PRAGMA foreign_key_list(captures)")
    assert record is not None
    assert record["record_path"] == "old/path"
    assert capture is not None
    assert any(
        row["table"] == "records"
        and row["from"] == "record_id"
        and row["to"] == "record_id"
        for row in foreign_keys
    )
    database.close()


def test_schema_migration_rolls_back_and_can_retry(tmp_path, monkeypatch) -> None:
    database = Database(tmp_path / "rollback.sqlite3")
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
    original_migrate = schema_module._migrate_legacy_record_schema

    def fail_after_first_step(connection) -> None:
        connection.execute("ALTER TABLE sessions RENAME TO records")
        raise RuntimeError("migration failure")

    monkeypatch.setattr(
        schema_module,
        "_migrate_legacy_record_schema",
        fail_after_first_step,
    )
    with pytest.raises(RuntimeError, match="migration failure"):
        initialize_schema(database)

    assert database.fetchone(
        "SELECT 1 FROM sqlite_master WHERE name='sessions'"
    ) is not None
    assert database.fetchone(
        "SELECT 1 FROM sqlite_master WHERE name='records'"
    ) is None

    monkeypatch.setattr(
        schema_module,
        "_migrate_legacy_record_schema",
        original_migrate,
    )
    initialize_schema(database)
    initialize_schema(database)
    assert database.fetchone(
        "SELECT 1 FROM sqlite_master WHERE name='records'"
    ) is not None
    database.close()
