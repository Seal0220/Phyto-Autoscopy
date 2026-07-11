from __future__ import annotations

from app.database.connection import Database
from app.models.session_models import SessionSummary


class SessionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def upsert(self, session_id: str, created_at: str, status: str, session_path: str) -> None:
        self.database.execute(
            """
            INSERT INTO sessions(session_id, created_at, status, session_path)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                status=excluded.status,
                session_path=excluded.session_path
            """,
            (session_id, created_at, status, session_path),
        )

    def update_status(self, session_id: str, status: str) -> None:
        self.database.execute(
            "UPDATE sessions SET status=? WHERE session_id=?",
            (status, session_id),
        )

    def list(self) -> list[SessionSummary]:
        rows = self.database.connection.execute(
            "SELECT session_id, created_at, status, session_path FROM sessions ORDER BY created_at DESC"
        ).fetchall()
        return [SessionSummary(**dict(row)) for row in rows]

    def get(self, session_id: str) -> SessionSummary | None:
        row = self.database.connection.execute(
            "SELECT session_id, created_at, status, session_path FROM sessions WHERE session_id=?",
            (session_id,),
        ).fetchone()
        return SessionSummary(**dict(row)) if row else None

    def delete(self, session_id: str) -> None:
        self.database.execute("DELETE FROM captures WHERE session_id=?", (session_id,))
        self.database.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
