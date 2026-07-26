from __future__ import annotations

import sqlite3

from app.database.connection import Database


ANALYSIS_BACKUP_FILE_NAME = "phyto_autoscopy-backup.sqlite3"
SUPPORTED_ANALYSIS_METHODS = (
    "fixed",
    "rotating",
)
LEGACY_ANALYSIS_TABLES = (
    "analysis_frame_pairs",
    "analysis_detections",
    "manual_corrections",
)


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


def _analysis_cleanup_required(connection: sqlite3.Connection) -> bool:
    if any(
        _table_exists(connection, table_name)
        for table_name in LEGACY_ANALYSIS_TABLES
    ):
        return True
    if not _table_exists(connection, "analysis_runs"):
        return False
    row = connection.execute(
        """
        SELECT
            COUNT(*) AS total_count,
            SUM(
                CASE WHEN method_name NOT IN (?, ?) THEN 1 ELSE 0 END
            ) AS unsupported_count
        FROM analysis_runs
        """,
        SUPPORTED_ANALYSIS_METHODS,
    ).fetchone()
    return bool(
        row
        and (
            int(row["total_count"] or 0) > 1
            or int(row["unsupported_count"] or 0) > 0
        )
    )


def _backup_database_before_analysis_cleanup(database: Database) -> None:
    connection = database.connection
    if not _analysis_cleanup_required(connection):
        return
    backup_path = database.path.with_name(ANALYSIS_BACKUP_FILE_NAME)
    if backup_path.exists():
        return
    with sqlite3.connect(backup_path) as backup_connection:
        connection.backup(backup_connection)


def _cleanup_analysis_history(connection: sqlite3.Connection) -> None:
    for table_name in LEGACY_ANALYSIS_TABLES:
        connection.execute(f'DROP TABLE IF EXISTS "{table_name}"')
    if not _table_exists(connection, "analysis_runs"):
        return
    connection.execute(
        """
        DELETE FROM analysis_runs
        WHERE method_name NOT IN (?, ?)
        """,
        SUPPORTED_ANALYSIS_METHODS,
    )
    connection.execute(
        """
        DELETE FROM analysis_runs
        WHERE analysis_id NOT IN (
            SELECT analysis_id
            FROM analysis_runs
            ORDER BY created_at DESC, analysis_id DESC
            LIMIT 1
        )
        """
    )


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


def _analysis_runs_require_rebuild(connection: sqlite3.Connection) -> bool:
    if not _table_exists(connection, "analysis_runs"):
        return False
    record_is_required = any(
        row["name"] == "record_id" and bool(row["notnull"])
        for row in connection.execute("PRAGMA table_info(analysis_runs)").fetchall()
    )
    has_legacy_calibration_id = "calibration_id" in _columns(
        connection,
        "analysis_runs",
    )
    return record_is_required or has_legacy_calibration_id


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
            intrinsics_snapshot_json TEXT NOT NULL DEFAULT '{}',
            aruco_layout_snapshot_json TEXT NOT NULL DEFAULT '{}',
            camera_pose_results_json TEXT NOT NULL DEFAULT '[]',
            pose_estimation_version TEXT,
            pose_quality_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY(record_id) REFERENCES records(record_id)
        )
        """
    )
    connection.execute(
        """
        INSERT INTO analysis_runs_source_new(
            analysis_id, record_id, method_name, method_version,
            git_commit, parameters_json, created_at, updated_at,
            created_by, output_path, status, stage, current_frame,
            total_frames, progress, manual_review_completed,
            average_reprojection_error_px, last_error,
            intrinsics_snapshot_json, aruco_layout_snapshot_json,
            camera_pose_results_json, pose_estimation_version,
            pose_quality_json
        )
        SELECT
            analysis_id, record_id, method_name, method_version,
            git_commit, parameters_json, created_at, updated_at,
            created_by, output_path, status, stage, current_frame,
            total_frames, progress, manual_review_completed,
            average_reprojection_error_px, last_error,
            intrinsics_snapshot_json, aruco_layout_snapshot_json,
            camera_pose_results_json, pose_estimation_version,
            pose_quality_json
        FROM analysis_runs
        """
    )
    connection.execute("DROP TABLE analysis_runs")
    connection.execute(
        "ALTER TABLE analysis_runs_source_new RENAME TO analysis_runs"
    )


def _migrate_calibration_runs_intrinsic_only(
    connection: sqlite3.Connection,
) -> None:
    if not _table_exists(connection, "calibration_runs"):
        return
    if "profile_id" not in _columns(connection, "calibration_runs"):
        return

    connection.execute("DROP TABLE IF EXISTS calibration_runs_intrinsic_new")
    connection.execute(
        """
        CREATE TABLE calibration_runs_intrinsic_new (
            run_id TEXT PRIMARY KEY,
            run_type TEXT NOT NULL,
            camera_id TEXT,
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
        INSERT INTO calibration_runs_intrinsic_new(
            run_id, run_type, camera_id, board_profile_id, status,
            created_at, updated_at, payload_json, last_error
        )
        SELECT
            run_id, 'intrinsic', camera_id, board_profile_id, status,
            created_at, updated_at, payload_json, last_error
        FROM calibration_runs
        WHERE run_type='intrinsic'
        """
    )
    connection.execute("DROP TABLE calibration_runs")
    connection.execute(
        "ALTER TABLE calibration_runs_intrinsic_new RENAME TO calibration_runs"
    )


def initialize_schema(database: Database) -> None:
    _backup_database_before_analysis_cleanup(database)
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
            _migrate_calibration_runs_intrinsic_only(connection)
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_calibration_runs_status
                ON calibration_runs(status, created_at)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_runs (
                    analysis_id TEXT PRIMARY KEY,
                    record_id TEXT,
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
                    intrinsics_snapshot_json TEXT NOT NULL DEFAULT '{}',
                    aruco_layout_snapshot_json TEXT NOT NULL DEFAULT '{}',
                    camera_pose_results_json TEXT NOT NULL DEFAULT '[]',
                    pose_estimation_version TEXT,
                    pose_quality_json TEXT NOT NULL DEFAULT '{}',
                    cancel_requested_at TEXT,
                    cancel_requested_by TEXT,
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
            analysis_run_columns = _columns(connection, "analysis_runs")
            for name, definition in (
                ("intrinsics_snapshot_json", "TEXT NOT NULL DEFAULT '{}'"),
                ("aruco_layout_snapshot_json", "TEXT NOT NULL DEFAULT '{}'"),
                ("camera_pose_results_json", "TEXT NOT NULL DEFAULT '[]'"),
                ("pose_estimation_version", "TEXT"),
                ("pose_quality_json", "TEXT NOT NULL DEFAULT '{}'"),
            ):
                if name not in analysis_run_columns:
                    connection.execute(
                        f"ALTER TABLE analysis_runs ADD COLUMN {name} {definition}"
                    )
            _migrate_analysis_runs_nullable_record(connection)
            analysis_run_columns = _columns(connection, "analysis_runs")
            for name, definition in (
                ("reconstruction_backend", "TEXT"),
                ("reconstruction_backend_version", "TEXT"),
                ("reconstruction_environment_json", "TEXT NOT NULL DEFAULT '{}'"),
                ("round_count", "INTEGER NOT NULL DEFAULT 0"),
                ("completed_round_count", "INTEGER NOT NULL DEFAULT 0"),
                ("failed_round_count", "INTEGER NOT NULL DEFAULT 0"),
                ("tip_marker_count", "INTEGER NOT NULL DEFAULT 0"),
                ("trajectory_status", "TEXT"),
                ("cancel_requested_at", "TEXT"),
                ("cancel_requested_by", "TEXT"),
            ):
                if name not in analysis_run_columns:
                    connection.execute(
                        f"ALTER TABLE analysis_runs ADD COLUMN {name} {definition}"
                    )
            connection.execute("DROP TABLE IF EXISTS calibration_profiles")
            connection.execute("DROP TABLE IF EXISTS calibration_observations")
            connection.execute("DROP TABLE IF EXISTS extrinsic_profile_cameras")
            connection.execute("DROP TABLE IF EXISTS extrinsic_profiles")

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_rounds (
                    analysis_id TEXT NOT NULL,
                    round_key TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    mode_id TEXT NOT NULL,
                    round_id TEXT NOT NULL,
                    started_at TEXT,
                    ended_at TEXT,
                    duration_seconds REAL,
                    status TEXT NOT NULL,
                    view_count INTEGER NOT NULL DEFAULT 0,
                    top_view_count INTEGER NOT NULL DEFAULT 0,
                    side_view_count INTEGER NOT NULL DEFAULT 0,
                    rotating_view_count INTEGER NOT NULL DEFAULT 0,
                    angular_coverage_deg REAL,
                    static_scene_score REAL,
                    model_result_id TEXT,
                    tip_landmark_id TEXT,
                    failure_reason TEXT,
                    PRIMARY KEY(analysis_id, round_key),
                    UNIQUE(analysis_id, mode_id, round_id),
                    FOREIGN KEY(analysis_id)
                        REFERENCES analysis_runs(analysis_id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_views (
                    analysis_id TEXT NOT NULL,
                    round_key TEXT NOT NULL,
                    view_id TEXT NOT NULL,
                    capture_id INTEGER NOT NULL,
                    camera_id TEXT NOT NULL,
                    snapshot_id TEXT,
                    timestamp TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    absolute_path TEXT NOT NULL,
                    angle_deg REAL,
                    motor_position_deg REAL,
                    image_width INTEGER NOT NULL,
                    image_height INTEGER NOT NULL,
                    image_sha256 TEXT NOT NULL,
                    selected_for_reconstruction INTEGER NOT NULL DEFAULT 0,
                    exclusion_reason TEXT,
                    pose_status TEXT,
                    pose_reprojection_error_px REAL,
                    PRIMARY KEY(analysis_id, view_id),
                    UNIQUE(analysis_id, round_key, camera_id, capture_id),
                    FOREIGN KEY(analysis_id, round_key)
                        REFERENCES analysis_rounds(analysis_id, round_key)
                        ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_camera_poses (
                    analysis_id TEXT NOT NULL,
                    round_key TEXT NOT NULL,
                    view_id TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    valid INTEGER NOT NULL DEFAULT 0,
                    pose_source TEXT NOT NULL,
                    failure_reason TEXT,
                    PRIMARY KEY(analysis_id, view_id),
                    FOREIGN KEY(analysis_id, view_id)
                        REFERENCES analysis_views(analysis_id, view_id)
                        ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_round_models (
                    analysis_id TEXT NOT NULL,
                    round_key TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    failure_reason TEXT,
                    PRIMARY KEY(analysis_id, model_id),
                    UNIQUE(analysis_id, round_key),
                    FOREIGN KEY(analysis_id, round_key)
                        REFERENCES analysis_rounds(analysis_id, round_key)
                        ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_tip_landmarks (
                    analysis_id TEXT NOT NULL,
                    round_key TEXT NOT NULL,
                    tip_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    valid INTEGER NOT NULL DEFAULT 0,
                    confidence REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY(analysis_id, tip_id),
                    UNIQUE(analysis_id, round_key),
                    FOREIGN KEY(analysis_id, round_key)
                        REFERENCES analysis_rounds(analysis_id, round_key)
                        ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_tip_observations (
                    analysis_id TEXT NOT NULL,
                    round_key TEXT NOT NULL,
                    view_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    selected INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(analysis_id, candidate_id),
                    FOREIGN KEY(analysis_id, view_id)
                        REFERENCES analysis_views(analysis_id, view_id)
                        ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_tip_corrections (
                    correction_id TEXT PRIMARY KEY,
                    analysis_id TEXT NOT NULL,
                    round_key TEXT NOT NULL,
                    operator_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(analysis_id, round_key)
                        REFERENCES analysis_rounds(analysis_id, round_key)
                        ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_trajectory_points (
                    analysis_id TEXT NOT NULL,
                    mode_id TEXT NOT NULL,
                    round_key TEXT NOT NULL,
                    point_index INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY(analysis_id, mode_id, point_index),
                    FOREIGN KEY(analysis_id, round_key)
                        REFERENCES analysis_rounds(analysis_id, round_key)
                        ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_analysis_runs_record ON analysis_runs(record_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_analysis_runs_status ON analysis_runs(status)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_analysis_rounds_status ON analysis_rounds(analysis_id, status)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_analysis_rounds_order ON analysis_rounds(analysis_id, mode_id, round_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_analysis_views_round ON analysis_views(analysis_id, round_key, camera_id)"
            )
            _cleanup_analysis_history(connection)
    finally:
        connection.execute("PRAGMA foreign_keys = ON")
