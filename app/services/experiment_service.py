from __future__ import annotations

from app.core.config import AppSettings
from app.core.exceptions import PhytoAutoscopyError
from app.models.experiment_models import ExperimentStartRequest, ExperimentStatus
from app.services.session_service import SessionService


class ExperimentService:
    def __init__(self, settings: AppSettings, sessions: SessionService) -> None:
        self.settings = settings
        self.sessions = sessions
        self.status = "idle"
        self.session_id: str | None = None
        self.cycle_count = 0
        self.last_error: str | None = None

    def get_status(self) -> ExperimentStatus:
        return ExperimentStatus(
            status=self.status,
            session_id=self.session_id,
            cycle_count=self.cycle_count,
            last_error=self.last_error,
        )

    def start(self, request: ExperimentStartRequest | None = None) -> ExperimentStatus:
        if self.status == "running":
            raise PhytoAutoscopyError("Experiment is already running")
        session = self.sessions.create_session(status="running")
        self.status = "running"
        self.session_id = session.session_id
        self.cycle_count = 0
        self.last_error = None
        return self.get_status()

    def pause(self) -> ExperimentStatus:
        if self.status != "running":
            raise PhytoAutoscopyError("Only a running experiment can be paused")
        self.status = "paused"
        if self.session_id:
            self.sessions.update_status(self.session_id, "paused")
        return self.get_status()

    def resume(self) -> ExperimentStatus:
        if self.status != "paused":
            raise PhytoAutoscopyError("Only a paused experiment can be resumed")
        self.status = "running"
        if self.session_id:
            self.sessions.update_status(self.session_id, "running")
        return self.get_status()

    def stop(self) -> ExperimentStatus:
        if self.session_id:
            self.sessions.update_status(self.session_id, "stopped")
        self.status = "idle"
        self.session_id = None
        return self.get_status()
