from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import AppSettings
from app.core.exceptions import SessionError
from app.models.session_models import SessionDetail, SessionSummary
from app.repositories.session_repository import SessionRepository
from app.services.storage_service import StorageService


class SessionService:
    def __init__(
        self,
        settings: AppSettings,
        storage: StorageService,
        repository: SessionRepository,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.repository = repository
        self.active_session_id: str | None = None

    def _local_timezone(self) -> tzinfo:
        try:
            return ZoneInfo("Asia/Taipei")
        except ZoneInfoNotFoundError:
            return timezone(timedelta(hours=8), name="Asia/Taipei")

    def create_session(self, status: str = "running") -> SessionSummary:
        now = datetime.now(self._local_timezone())
        session_id = self.storage.next_session_id(now.strftime("%Y-%m-%d"))
        session_dir = self.storage.create_session_layout(session_id)
        payload = {
            "project_name": self.settings.project.name,
            "project_name_zh": self.settings.project.name_zh,
            "device_name": self.settings.project.device_name,
            "device_version": self.settings.project.device_version,
            "session_id": session_id,
            "created_at": now.isoformat(),
            "status": status,
            "experiment": self.settings.experiment.model_dump(),
            "hardware": {
                "camera_count": len(self.settings.cameras),
                "motor_controller": "PhidgetStepper Bipolar HC",
                "motor": "NEMA-17 Bipolar 48mm 0.9deg",
                "power_supply": "MEAN WELL RS-100-24",
                "mock_mode": self.settings.hardware.mock_mode,
            },
        }
        self.storage.session_json_path(session_id).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        summary = SessionSummary(
            session_id=session_id,
            created_at=payload["created_at"],
            status=status,
            session_path=str(session_dir),
        )
        self.repository.upsert(session_id, summary.created_at, status, summary.session_path)
        self.active_session_id = session_id
        return summary

    def ensure_active_session(self) -> SessionSummary:
        if self.active_session_id:
            existing = self.repository.get(self.active_session_id)
            if existing:
                return existing
        return self.create_session(status="manual")

    def update_status(self, session_id: str, status: str) -> None:
        self.repository.update_status(session_id, status)
        session_path = self.storage.session_json_path(session_id)
        if session_path.exists():
            payload = json.loads(session_path.read_text(encoding="utf-8"))
            payload["status"] = status
            session_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    def list_sessions(self) -> list[SessionSummary]:
        return self.repository.list()

    def get_session(self, session_id: str) -> SessionDetail:
        summary = self.repository.get(session_id)
        if summary is None:
            raise SessionError(f"Unknown session: {session_id}")
        session_json_path = self.storage.session_json_path(session_id)
        payload = json.loads(session_json_path.read_text(encoding="utf-8"))
        return SessionDetail(**summary.model_dump(), session_json=payload)

    def delete_session(self, session_id: str) -> None:
        summary = self.repository.get(session_id)
        if summary is None:
            raise SessionError(f"Unknown session: {session_id}")
        self.repository.delete(session_id)
        session_path = Path(summary.session_path)
        if session_path.exists():
            shutil.rmtree(session_path)
        if self.active_session_id == session_id:
            self.active_session_id = None
