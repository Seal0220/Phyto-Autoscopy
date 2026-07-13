from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from threading import RLock
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import AppSettings
from app.core.exceptions import RecordError
from app.models.record_models import RecordDetail, RecordSummary
from app.repositories.record_repository import RecordRepository
from app.services.storage_service import StorageService

TERMINAL_RECORD_STATUSES = frozenset({
    "completed",
    "failed",
    "stopped",
})
INTERRUPTED_RECORD_STATUSES = frozenset({"running", "paused", "stopping"})

logger = logging.getLogger(__name__)
# Read-only adapter for metadata created before the schedule/record rename.
LEGACY_SCHEDULE_KEY = "experiment"


class RecordService:
    def __init__(
        self,
        settings: AppSettings,
        storage: StorageService,
        repository: RecordRepository,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.repository = repository
        self.active_record_id: str | None = None
        self._lock = RLock()

    def _local_timezone(self) -> tzinfo:
        try:
            return ZoneInfo("Asia/Taipei")
        except ZoneInfoNotFoundError:
            return timezone(timedelta(hours=8), name="Asia/Taipei")

    def _next_record_id(self, date_label: str) -> str:
        candidate = self.storage.next_record_id(date_label)
        prefix, suffix = candidate.rsplit("_", 1)
        index = int(suffix)
        while self.repository.get(candidate) is not None:
            index += 1
            candidate = f"{prefix}_{index:03d}"
        return candidate

    def _record_payload(
        self,
        record_id: str,
        created_at: str,
        status: str,
        ended_at: str | None = None,
        schedule: dict | None = None,
    ) -> dict:
        return {
            "project_name": self.settings.project.name,
            "project_name_zh": self.settings.project.name_zh,
            "device_name": self.settings.project.device_name,
            "device_version": self.settings.project.device_version,
            "record_id": record_id,
            "created_at": created_at,
            "ended_at": ended_at,
            "status": status,
            "schedule": (
                schedule
                if schedule is not None
                else self.settings.schedule.model_dump()
            ),
            "hardware": {
                "camera_count": len(self.settings.cameras),
                "motor_controller": "PhidgetStepper Bipolar HC",
                "motor": "NEMA-17 Bipolar 48mm 0.9deg",
                "power_supply": "MEAN WELL RS-100-24",
                "mock_mode": self.settings.hardware.mock_mode,
            },
        }

    def _write_record_payload(
        self,
        record_path: Path,
        payload: dict,
    ) -> None:
        temporary_path = record_path.with_name(
            f".{record_path.name}.{uuid4().hex}.tmp"
        )
        try:
            record_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary_path.replace(record_path)
        finally:
            temporary_path.unlink(missing_ok=True)

    def _read_record_payload(
        self,
        summary: RecordSummary,
    ) -> dict:
        record_path = self._record_metadata_path(summary)
        try:
            payload = json.loads(record_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("record.json 根節點必須是物件。")
            legacy_id = payload.pop("session_id", None)
            payload.setdefault("record_id", legacy_id or summary.record_id)
            legacy_schedule = payload.pop(LEGACY_SCHEDULE_KEY, None)
            if "schedule" not in payload and legacy_schedule is not None:
                payload["schedule"] = legacy_schedule
            if record_path.name == "session.json":
                self._write_record_payload(
                    Path(summary.record_path) / "record.json",
                    payload,
                )
            return payload
        except (OSError, UnicodeError, ValueError) as exc:
            logger.warning(
                "Recovering unreadable record metadata: %s (%s)",
                record_path,
                exc,
            )
            payload = self._record_payload(
                record_id=summary.record_id,
                created_at=summary.created_at,
                status=summary.status,
                ended_at=summary.ended_at,
            )
            self._write_record_payload(
                Path(summary.record_path) / "record.json",
                payload,
            )
            return payload

    @staticmethod
    def _record_metadata_path(summary: RecordSummary) -> Path:
        directory = Path(summary.record_path)
        record_path = directory / "record.json"
        if record_path.exists():
            return record_path
        legacy_path = directory / "session.json"
        return legacy_path if legacy_path.exists() else record_path

    def create_record(
        self,
        status: str = "running",
        schedule: dict | None = None,
    ) -> RecordSummary:
        with self._lock:
            if self.active_record_id:
                active = self.repository.get(self.active_record_id)
                if active is not None and active.status == "manual":
                    self.update_status(active.record_id, "completed")
                elif active is not None and active.status not in TERMINAL_RECORD_STATUSES:
                    raise RecordError("已有使用中的紀錄，無法建立新紀錄。")
                else:
                    self.active_record_id = None
            now = datetime.now(self._local_timezone())
            record_id = self._next_record_id(now.strftime("%Y-%m-%d"))
            record_dir = self.storage.record_dir(record_id)
            try:
                record_dir = self.storage.create_record_layout(
                    record_id,
                    include_camera_dirs=schedule is None,
                )
                payload = self._record_payload(
                    record_id=record_id,
                    created_at=now.isoformat(),
                    status=status,
                    schedule=schedule,
                )
                self._write_record_payload(
                    self.storage.record_json_path(record_id),
                    payload,
                )
                summary = RecordSummary(
                    record_id=record_id,
                    created_at=payload["created_at"],
                    status=status,
                    record_path=str(record_dir),
                    ended_at=None,
                )
                self.repository.upsert(
                    record_id,
                    summary.created_at,
                    status,
                    summary.record_path,
                    summary.ended_at,
                )
            except Exception:
                shutil.rmtree(record_dir, ignore_errors=True)
                raise
            self.active_record_id = record_id
            return summary

    def ensure_active_record(self) -> RecordSummary:
        with self._lock:
            if self.active_record_id:
                existing = self.repository.get(self.active_record_id)
                if existing:
                    return existing
            return self.create_record(status="manual")

    def get_capture_record(self, record_id: str | None = None) -> RecordSummary:
        with self._lock:
            summary = (
                self.ensure_active_record()
                if record_id is None
                else self.repository.get(record_id)
            )
            if summary is None:
                raise RecordError(f"找不到紀錄：{record_id}")
            if summary.status in TERMINAL_RECORD_STATUSES:
                raise RecordError("已結束的紀錄不可再新增擷取影像。")
            return summary

    def update_status(self, record_id: str, status: str) -> None:
        with self._lock:
            summary = self.repository.get(record_id)
            if summary is None:
                raise RecordError(f"找不到紀錄：{record_id}")

            if summary.status in TERMINAL_RECORD_STATUSES:
                effective_status = summary.status
                ended_at = summary.ended_at
                if status != effective_status:
                    logger.info(
                        "Ignoring record status regression for %s: %s -> %s",
                        record_id,
                        effective_status,
                        status,
                    )
            else:
                effective_status = status
                ended_at = (
                    datetime.now(self._local_timezone()).isoformat()
                    if status in TERMINAL_RECORD_STATUSES
                    else None
                )
            previous_payload = self._read_record_payload(summary)
            metadata_path = self._record_metadata_path(summary)
            updated_payload = dict(previous_payload)
            updated_payload["status"] = effective_status
            updated_payload["ended_at"] = ended_at
            self._write_record_payload(metadata_path, updated_payload)
            if summary.status not in TERMINAL_RECORD_STATUSES:
                try:
                    self.repository.update_status(
                        record_id,
                        effective_status,
                        ended_at,
                    )
                except Exception:
                    try:
                        self._write_record_payload(metadata_path, previous_payload)
                    except Exception:
                        logger.exception(
                            "Failed to restore record metadata after database failure: %s",
                            record_id,
                        )
                    raise
            if (
                effective_status in TERMINAL_RECORD_STATUSES
                and self.active_record_id == record_id
            ):
                self.active_record_id = None

    def recover_interrupted_records(self) -> None:
        for summary in self.repository.list():
            if summary.status in INTERRUPTED_RECORD_STATUSES:
                try:
                    self.update_status(summary.record_id, "failed")
                except Exception:
                    logger.exception(
                        "Failed to recover interrupted record: %s",
                        summary.record_id,
                    )

    def release_active_record(self, record_id: str) -> None:
        with self._lock:
            if self.active_record_id == record_id:
                self.active_record_id = None

    def list_records(self) -> list[RecordSummary]:
        return self.repository.list()

    def get_record(self, record_id: str) -> RecordDetail:
        with self._lock:
            summary = self.repository.get(record_id)
            if summary is None:
                raise RecordError(f"找不到紀錄：{record_id}")
            payload = self._read_record_payload(summary)
            return RecordDetail(**summary.model_dump(), record_json=payload)

    def get_record_file(self, record_id: str, file_name: str) -> Path:
        with self._lock:
            summary = self.repository.get(record_id)
            if summary is None:
                raise RecordError(f"找不到紀錄：{record_id}")
            record_path = Path(summary.record_path).resolve()
            if record_path.name != record_id:
                raise RecordError("紀錄儲存位置無效。")
            if file_name not in {"metadata.csv", "record.json"}:
                raise RecordError("不支援的紀錄檔案。")
            file_path = (
                self._record_metadata_path(summary)
                if file_name == "record.json"
                else record_path / file_name
            )
            if not file_path.is_file():
                raise RecordError(f"找不到紀錄檔案：{file_name}")
            return file_path

    def delete_record(self, record_id: str) -> None:
        with self._lock:
            summary = self.repository.get(record_id)
            if summary is None:
                raise RecordError(f"找不到紀錄：{record_id}")
            record_path = Path(summary.record_path).resolve()
            if record_path.name != record_id:
                raise RecordError("紀錄儲存位置無效。")
            tombstone = record_path.with_name(
                f".{record_path.name}.{uuid4().hex}.deleting"
            )
            if record_path.exists():
                record_path.replace(tombstone)
            try:
                self.repository.delete(record_id)
            except Exception:
                if tombstone.exists():
                    tombstone.replace(record_path)
                raise
            if tombstone.exists():
                try:
                    shutil.rmtree(tombstone)
                except OSError:
                    logger.exception("Failed to remove deleted record directory: %s", tombstone)
            if self.active_record_id == record_id:
                self.active_record_id = None
