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


def _migrate_manual_correction_history(connection: sqlite3.Connection) -> None:
    """Remove the legacy one-correction-per-frame UNIQUE constraint safely."""

    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='manual_corrections'"
    ).fetchone()
    if row is None:
        return
    normalized_sql = "".join(str(row["sql"] or "").lower().split())
    if "unique(analysis_id,frame_id,camera_id)" not in normalized_sql:
        return
    connection.execute("DROP TABLE IF EXISTS manual_corrections_history_new")
    connection.execute(
        """
        CREATE TABLE manual_corrections_history_new (
            correction_id TEXT PRIMARY KEY,
            analysis_id TEXT NOT NULL,
            frame_id INTEGER NOT NULL,
            camera_id TEXT NOT NULL,
            automatic_x_px REAL,
            automatic_y_px REAL,
            corrected_x_px REAL,
            corrected_y_px REAL,
            operator_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            reason TEXT,
            invalid INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(analysis_id) REFERENCES analysis_runs(analysis_id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        INSERT INTO manual_corrections_history_new(
            correction_id, analysis_id, frame_id, camera_id,
            automatic_x_px, automatic_y_px, corrected_x_px,
            corrected_y_px, operator_id, created_at, reason, invalid
        )
        SELECT
            correction_id, analysis_id, frame_id, camera_id,
            automatic_x_px, automatic_y_px, corrected_x_px,
            corrected_y_px, operator_id, created_at, reason, invalid
        FROM manual_corrections
        """
    )
    connection.execute("DROP TABLE manual_corrections")
    connection.execute(
        "ALTER TABLE manual_corrections_history_new RENAME TO manual_corrections"
    )


def _analysis_runs_require_rebuild(connection: sqlite3.Connection) -> bool:
    if not _table_exists(connection, "analysis_runs"):
        return False
    record_is_required = any(
        row["name"] == "record_id" and bool(row["notnull"])
        for row in connection.execute("PRAGMA table_info(analysis_runs)").fetchall()
    )
    calibration_is_foreign_key = any(
        row["from"] == "calibration_id"
        for row in connection.execute(
            "PRAGMA foreign_key_list(analysis_runs)"
        ).fetchall()
    )
    return record_is_required or calibration_is_foreign_key


def _migrate_analysis_runs_nullable_record(connection: sqlite3.Connection) -> None:
    """Decouple immutable analysis snapshots from mutable calibration rows."""

    if not _analysis_runs_require_rebuild(connection):
        return
    connection.execute("DROP TABLE IF EXISTS analysis_runs_source_new")
    connection.execute(
        """
        CREATE TABLE analysis_runs_source_new (
            analysis_id TEXT PRIMARY KEY,
            record_id TEXT,
            calibration_id TEXT,
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
            FOREIGN KEY(record_id) REFERENCES records(record_id)
        )
        """
    )
    connection.execute(
        """
        INSERT INTO analysis_runs_source_new
        SELECT * FROM analysis_runs
        """
    )
    connection.execute("DROP TABLE analysis_runs")
    connection.execute(
        "ALTER TABLE analysis_runs_source_new RENAME TO analysis_runs"
    )


def initialize_schema(database: Database) -> None:
    connection = database.connection
    connection.commit()
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS calibration_boards (
                    board_profile_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    board_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS camera_intrinsics (
                    camera_id TEXT PRIMARY KEY,
                    camera_model TEXT NOT NULL,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    board_profile_id TEXT NOT NULL,
                    source_run_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(board_profile_id)
                        REFERENCES calibration_boards(board_profile_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS camera_intrinsics_history (
                    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id TEXT NOT NULL,
                    replaced_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS calibration_runs (
                    run_id TEXT PRIMARY KEY,
                    run_type TEXT NOT NULL,
                    camera_id TEXT,
                    profile_id TEXT,
                    board_profile_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    last_error TEXT,
                    FOREIGN KEY(board_profile_id)
                        REFERENCES calibration_boards(board_profile_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS extrinsic_profiles (
                    profile_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 0,
                    board_profile_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    last_error TEXT,
                    FOREIGN KEY(board_profile_id)
                        REFERENCES calibration_boards(board_profile_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS extrinsic_profile_cameras (
                    profile_id TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    height_mm REAL NOT NULL,
                    position_json TEXT NOT NULL,
                    transform_json TEXT,
                    mount_description TEXT NOT NULL,
                    PRIMARY KEY(profile_id, camera_id),
                    FOREIGN KEY(profile_id)
                        REFERENCES extrinsic_profiles(profile_id)
                        ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS calibration_observations (
                    observation_id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    motor_angle_deg REAL,
                    arm_height_mm REAL,
                    accepted INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(profile_id)
                        REFERENCES extrinsic_profiles(profile_id)
                        ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_extrinsic_active_singleton
                ON extrinsic_profiles(is_active)
                WHERE is_active = 1
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_calibration_runs_status
                ON calibration_runs(status, created_at)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_calibration_observations_profile
                ON calibration_observations(profile_id, captured_at)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_runs (
                    analysis_id TEXT PRIMARY KEY,
                    record_id TEXT,
                    calibration_id TEXT,
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
                    FOREIGN KEY(record_id) REFERENCES records(record_id)
                )
                """
            )
            if "average_reprojection_error_px" not in _columns(
                connection,
                "analysis_runs",
            ):
                connection.execute(
                    "ALTER TABLE analysis_runs ADD COLUMN average_reprojection_error_px REAL"
                )
            _migrate_analysis_runs_nullable_record(connection)
            connection.execute("DROP TABLE IF EXISTS calibration_profiles")

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_frame_pairs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    analysis_id TEXT NOT NULL,
                    pair_id TEXT NOT NULL,
                    frame_id INTEGER NOT NULL,
                    cycle_id INTEGER,
                    top_capture_id INTEGER,
                    side_capture_id INTEGER,
                    top_input_id INTEGER,
                    side_input_id INTEGER,
                    rotating_input_id INTEGER,
                    top_timestamp TEXT,
                    side_timestamp TEXT,
                    rotating_timestamp TEXT,
                    rotating_angle_deg REAL,
                    timestamp_delta_ms REAL,
                    rotating_timestamp_delta_ms REAL,
                    frame_offset INTEGER NOT NULL DEFAULT 0,
                    pair_status TEXT NOT NULL,
                    UNIQUE(analysis_id, pair_id),
                    UNIQUE(analysis_id, frame_id),
                    FOREIGN KEY(analysis_id) REFERENCES analysis_runs(analysis_id) ON DELETE CASCADE,
                    FOREIGN KEY(top_capture_id) REFERENCES captures(id),
                    FOREIGN KEY(side_capture_id) REFERENCES captures(id)
                )
                """
            )
            pair_columns = _columns(connection, "analysis_frame_pairs")
            for name, sql_type in (
                ("top_input_id", "INTEGER"),
                ("side_input_id", "INTEGER"),
                ("rotating_input_id", "INTEGER"),
                ("rotating_timestamp", "TEXT"),
                ("rotating_angle_deg", "REAL"),
                ("rotating_timestamp_delta_ms", "REAL"),
            ):
                if name not in pair_columns:
                    connection.execute(
                        f"ALTER TABLE analysis_frame_pairs ADD COLUMN {name} {sql_type}"
                    )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_detections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    analysis_id TEXT NOT NULL,
                    frame_id INTEGER NOT NULL,
                    camera_id TEXT NOT NULL,
                    automatic_json TEXT,
                    interpolated_json TEXT,
                    resolved_json TEXT,
                    updated_at TEXT NOT NULL,
                    UNIQUE(analysis_id, frame_id, camera_id),
                    FOREIGN KEY(analysis_id) REFERENCES analysis_runs(analysis_id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS manual_corrections (
                    correction_id TEXT PRIMARY KEY,
                    analysis_id TEXT NOT NULL,
                    frame_id INTEGER NOT NULL,
                    camera_id TEXT NOT NULL,
                    automatic_x_px REAL,
                    automatic_y_px REAL,
                    corrected_x_px REAL,
                    corrected_y_px REAL,
                    operator_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    reason TEXT,
                    invalid INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(analysis_id) REFERENCES analysis_runs(analysis_id) ON DELETE CASCADE
                )
                """
            )
            _migrate_manual_correction_history(connection)
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_analysis_runs_record ON analysis_runs(record_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_analysis_runs_status ON analysis_runs(status)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_analysis_pairs_run ON analysis_frame_pairs(analysis_id, frame_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_analysis_detections_run ON analysis_detections(analysis_id, frame_id)"
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_manual_corrections_frame
                ON manual_corrections(analysis_id, frame_id, camera_id, created_at)
                """
            )
    finally:
        connection.execute("PRAGMA foreign_keys = ON")
