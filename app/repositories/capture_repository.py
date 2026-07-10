from __future__ import annotations

from app.database.connection import Database
from app.models.capture_models import MetadataRecord


class CaptureRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def insert(self, record: MetadataRecord) -> None:
        self.database.execute(
            """
            INSERT INTO captures(
                session_id, cycle_id, camera_id, timestamp, angle_deg, motor_position_deg,
                file_path, status, error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.session_id,
                record.cycle_id,
                record.camera_id,
                record.timestamp,
                record.angle_deg,
                record.motor_position_deg,
                record.file_path,
                record.status,
                record.error_message,
            ),
        )
