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
    analysis_columns = {
        row["name"]
        for row in database.fetchall("PRAGMA table_info(analysis_runs)")
    }
    assert {"record_id", "record_path", "ended_at"} <= record_columns
    assert "record_id" in capture_columns
    assert "average_reprojection_error_px" in analysis_columns
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


def test_initialize_schema_removes_legacy_calibration_projection_without_losing_analysis(
    tmp_path,
) -> None:
    database = Database(tmp_path / "legacy-calibration.sqlite3")
    database.execute(
        """
        CREATE TABLE records (
            record_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL,
            record_path TEXT NOT NULL,
            ended_at TEXT
        )
        """
    )
    database.execute(
        """
        CREATE TABLE calibration_profiles (
            calibration_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        )
        """
    )
    database.execute(
        """
        CREATE TABLE analysis_runs (
            analysis_id TEXT PRIMARY KEY,
            record_id TEXT NOT NULL,
            calibration_id TEXT NOT NULL,
            method_name TEXT NOT NULL,
            method_version TEXT NOT NULL,
            git_commit TEXT NOT NULL,
            parameters_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by TEXT NOT NULL,
            output_path TEXT NOT NULL,
            status TEXT NOT NULL,
            stage TEXT,
            current_frame INTEGER NOT NULL DEFAULT 0,
            total_frames INTEGER NOT NULL DEFAULT 0,
            progress REAL NOT NULL DEFAULT 0,
            manual_review_completed INTEGER NOT NULL DEFAULT 0,
            average_reprojection_error_px REAL,
            last_error TEXT,
            FOREIGN KEY(record_id) REFERENCES records(record_id),
            FOREIGN KEY(calibration_id)
                REFERENCES calibration_profiles(calibration_id)
        )
        """
    )
    database.execute(
        "INSERT INTO records VALUES (?, ?, ?, ?, ?)",
        (
            "record-legacy",
            "2026-07-20T00:00:00+08:00",
            "completed",
            "data/captures/record-legacy",
            "2026-07-20T00:10:00+08:00",
        ),
    )
    database.execute(
        "INSERT INTO calibration_profiles VALUES (?, ?)",
        (
            "calibration-legacy",
            "2026-07-20T00:00:00+08:00",
        ),
    )
    database.execute(
        """
        INSERT INTO analysis_runs(
            analysis_id, record_id, calibration_id, method_name,
            method_version, git_commit, parameters_json, created_at,
            updated_at, created_by, output_path, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "analysis-legacy",
            "record-legacy",
            "calibration-legacy",
            "top_side",
            "1",
            "unknown",
            "{}",
            "2026-07-20T00:00:00+08:00",
            "2026-07-20T00:00:00+08:00",
            "operator",
            "data/analysis/analysis-legacy",
            "completed",
        ),
    )

    initialize_schema(database)

    run = database.fetchone(
        "SELECT * FROM analysis_runs WHERE analysis_id=?",
        ("analysis-legacy",),
    )
    foreign_keys = database.fetchall("PRAGMA foreign_key_list(analysis_runs)")
    assert run is not None
    assert run["calibration_id"] == "calibration-legacy"
    assert run["record_id"] == "record-legacy"
    assert not any(row["from"] == "calibration_id" for row in foreign_keys)
    assert database.fetchone(
        "SELECT 1 FROM sqlite_master WHERE name='calibration_profiles'"
    ) is None
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
