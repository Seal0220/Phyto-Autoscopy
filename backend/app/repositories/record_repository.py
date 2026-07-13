from __future__ import annotations

from app.database.connection import Database
from app.models.record_models import RecordSummary


class RecordRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def upsert(
        self,
        record_id: str,
        created_at: str,
        status: str,
        record_path: str,
        ended_at: str | None = None,
    ) -> None:
        self.database.execute(
            """
            INSERT INTO records(record_id, created_at, status, record_path, ended_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(record_id) DO UPDATE SET
                status=excluded.status,
                record_path=excluded.record_path,
                ended_at=COALESCE(excluded.ended_at, records.ended_at)
            """,
            (record_id, created_at, status, record_path, ended_at),
        )

    def update_status(
        self,
        record_id: str,
        status: str,
        ended_at: str | None = None,
    ) -> None:
        self.database.execute(
            "UPDATE records SET status=?, ended_at=? WHERE record_id=?",
            (status, ended_at, record_id),
        )

    def list(self) -> list[RecordSummary]:
        rows = self.database.fetchall(
            """
            SELECT record_id, created_at, status, record_path, ended_at
            FROM records
            ORDER BY created_at DESC
            """
        )
        return [RecordSummary(**dict(row)) for row in rows]

    def get(self, record_id: str) -> RecordSummary | None:
        row = self.database.fetchone(
            """
            SELECT record_id, created_at, status, record_path, ended_at
            FROM records
            WHERE record_id=?
            """,
            (record_id,),
        )
        return RecordSummary(**dict(row)) if row else None

    def delete(self, record_id: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "DELETE FROM captures WHERE record_id=?",
                (record_id,),
            )
            connection.execute(
                "DELETE FROM records WHERE record_id=?",
                (record_id,),
            )
