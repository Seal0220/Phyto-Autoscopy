from __future__ import annotations

from app.database.connection import Database
from app.models.capture_models import MetadataRecord, StoredCapture


class CaptureRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def insert(self, record: MetadataRecord) -> None:
        self.database.execute(
            """
            INSERT INTO captures(
                record_id, cycle_id, camera_id, timestamp, angle_deg, motor_position_deg,
                file_path, status, error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.record_id,
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

    def list_by_record(self, record_id: str) -> list[StoredCapture]:
        rows = self.database.fetchall(
            """
            SELECT
                id, record_id, cycle_id, camera_id, timestamp, angle_deg,
                motor_position_deg, file_path, status, error_message
            FROM captures
            WHERE record_id=?
            ORDER BY timestamp ASC, id ASC
            """,
            (record_id,),
        )
        return [StoredCapture(**dict(row)) for row in rows]

    def successful_camera_counts(self) -> dict[str, dict[str, int]]:
        """Read list-page counts in one query without loading capture rows or images."""
        rows = self.database.fetchall(
            """
            SELECT record_id, camera_id, COUNT(*) AS image_count
            FROM captures
            WHERE status='success' AND camera_id IN ('top', 'side', 'rotating')
            GROUP BY record_id, camera_id
            """
        )
        counts: dict[str, dict[str, int]] = {}
        for row in rows:
            counts.setdefault(row["record_id"], {})[row["camera_id"]] = row["image_count"]
        return counts
