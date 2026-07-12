from __future__ import annotations

from app.database.connection import Database
from app.models.session_models import SessionSummary


class SessionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def upsert(
        self,
        session_id: str,
        created_at: str,
        status: str,
        session_path: str,
        ended_at: str | None = None,
    ) -> None:
        self.database.execute(
            """
            INSERT INTO sessions(session_id, created_at, status, session_path, ended_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                status=excluded.status,
                session_path=excluded.session_path,
                ended_at=COALESCE(excluded.ended_at, sessions.ended_at)
            """,
            (session_id, created_at, status, session_path, ended_at),
        )

    def update_status(
        self,
        session_id: str,
        status: str,
        ended_at: str | None = None,
    ) -> None:
        self.database.execute(
            "UPDATE sessions SET status=?, ended_at=? WHERE session_id=?",
            (status, ended_at, session_id),
        )

    def list(self) -> list[SessionSummary]:
        rows = self.database.fetchall(
            """
            SELECT session_id, created_at, status, session_path, ended_at
            FROM sessions
            ORDER BY created_at DESC
            """
        )
        return [SessionSummary(**dict(row)) for row in rows]

    def get(self, session_id: str) -> SessionSummary | None:
        row = self.database.fetchone(
            """
            SELECT session_id, created_at, status, session_path, ended_at
            FROM sessions
            WHERE session_id=?
            """,
            (session_id,),
        )
        return SessionSummary(**dict(row)) if row else None

    def delete(self, session_id: str) -> None:
        self.database.execute("DELETE FROM captures WHERE session_id=?", (session_id,))
        self.database.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
