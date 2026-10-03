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

    def successful_camera_counts(self, record_id: str) -> dict[str, int]:
        """Count one Record's images when no persisted summary is available."""
        rows = self.database.fetchall(
            """
            SELECT camera_id, COUNT(*) AS image_count
            FROM captures
            WHERE record_id=? AND status='success'
                AND camera_id IN ('top', 'side', 'rotating')
            GROUP BY camera_id
            """,
            (record_id,),
        )
        return {row["camera_id"]: row["image_count"] for row in rows}
