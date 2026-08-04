from __future__ import annotations

import csv
import json
import logging
import shutil
from collections import Counter
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from threading import RLock
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import AppSettings, resolve_project_path
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
        self._normalize_record_paths()

    def _normalize_record_paths(self) -> None:
        for record in self.repository.list():
            absolute_path = str(resolve_project_path(record.record_path))
            if absolute_path != record.record_path:
                self.repository.update_path(
                    record.record_id,
                    absolute_path,
                )

    def _local_timezone(self) -> tzinfo:
        try:
            return ZoneInfo("Asia/Taipei")
        except ZoneInfoNotFoundError:
            return timezone(timedelta(hours=8), name="Asia/Taipei")

    def _next_record_id(self, captured_at: datetime) -> str:
        candidate_time = captured_at.astimezone(timezone.utc)
        while True:
            candidate = self.storage.next_record_id(candidate_time)
            if self.repository.get(candidate) is None:
                return candidate
            candidate_time += timedelta(microseconds=1)

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
            "record_scope": "parent",
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

    @staticmethod
    def _mode_record_payload(
        parent_payload: dict,
        mode: dict,
    ) -> dict:
        schedule = parent_payload.get("schedule")
        mode_schedule = (
            {
                **schedule,
                "modes": [mode],
            }
            if isinstance(schedule, dict)
            else {"modes": [mode]}
        )
        mode_folder = str(mode.get("folder") or "").strip()
        summaries = parent_payload.get("mode_summaries")
        mode_summary = next(
            (
                summary
                for summary in summaries
                if isinstance(summary, dict)
                and summary.get("folder") == mode_folder
            ),
            None,
        ) if isinstance(summaries, list) else None
        payload = {
            **parent_payload,
            "record_scope": "mode",
            "parent_record_id": parent_payload["record_id"],
            "mode": mode,
            "schedule": mode_schedule,
        }
        payload.pop("mode_summaries", None)
        if mode_summary is not None:
            payload["capture_summary"] = mode_summary
            payload["rounds"] = mode_summary.get("rounds", [])
        return payload

    @staticmethod
    def _capture_summary(
        metadata_path: Path,
        scope_path: Path,
    ) -> dict:
        try:
            with metadata_path.open(
                encoding="utf-8-sig",
                newline="",
            ) as handle:
                rows = list(csv.DictReader(handle))
        except (OSError, UnicodeError, csv.Error) as exc:
            return {
                "capture_count": 0,
                "snapshot_count": 0,
                "camera_counts": {},
                "status_counts": {},
                "rounds": [],
                "error": f"無法讀取擷取索引：{exc}",
            }

        snapshot_paths = {
            Path(str(row.get("file_path") or "")).parent.as_posix()
            for row in rows
            if str(row.get("file_path") or "").strip()
        }
        rounds = []
        for round_path in sorted((scope_path / "rounds").glob("round.*")):
            if not round_path.is_dir():
                continue
            snapshots = [
                path
                for path in round_path.glob("snapshot.*")
                if path.is_dir()
            ]
            rounds.append(
                {
                    "name": round_path.name,
                    "snapshot_count": len(snapshots),
                    "capture_count": sum(
                        len(list(snapshot.glob("*.jpg")))
                        for snapshot in snapshots
                    ),
                }
            )
        return {
            "capture_count": len(rows),
            "snapshot_count": len(snapshot_paths),
            "camera_counts": dict(Counter(
                str(row.get("camera_id") or "")
                for row in rows
                if str(row.get("camera_id") or "").strip()
            )),
            "status_counts": dict(Counter(
                str(row.get("status") or "")
                for row in rows
                if str(row.get("status") or "").strip()
            )),
            "rounds": rounds,
        }

    def _with_capture_summaries(
        self,
        record_path: Path,
        payload: dict,
    ) -> dict:
        updated = dict(payload)
        updated["capture_summary"] = self._capture_summary(
            record_path / "metadata.csv",
            record_path,
        )
        schedule = payload.get("schedule")
        modes = schedule.get("modes", []) if isinstance(schedule, dict) else []
        mode_summaries = []
        for mode in modes:
            if not isinstance(mode, dict):
                continue
            mode_folder = str(mode.get("folder") or "").strip()
            if not mode_folder:
                continue
            mode_path = record_path / "modes" / mode_folder
            mode_summaries.append(
                {
                    "id": mode.get("id"),
                    "type": mode.get("type"),
                    "folder": mode_folder,
                    **self._capture_summary(
                        mode_path / "metadata.csv",
                        mode_path,
                    ),
                }
            )
        updated["mode_summaries"] = mode_summaries
        return updated

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

    def _write_record_bundle(
        self,
        record_path: Path,
        parent_payload: dict,
    ) -> None:
        self._write_record_payload(
            record_path / "config.json",
            parent_payload,
        )
        schedule = parent_payload.get("schedule")
        modes = schedule.get("modes", []) if isinstance(schedule, dict) else []
        for mode in modes:
            if not isinstance(mode, dict):
                continue
            mode_folder = str(mode.get("folder") or "").strip()
            if not mode_folder:
                continue
            mode_dir = self.storage.create_mode_layout(
                parent_payload["record_id"],
                mode_folder,
                record_path,
            )
            self._write_record_payload(
                mode_dir / "config.json",
                self._mode_record_payload(parent_payload, mode),
            )

    def _read_record_payload(
        self,
        summary: RecordSummary,
    ) -> dict:
        record_path = self._record_config_path(summary)
        try:
            payload = json.loads(record_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("config.json 根節點必須是物件。")
            legacy_id = payload.pop("session_id", None)
            payload.setdefault("record_id", legacy_id or summary.record_id)
            legacy_schedule = payload.pop(LEGACY_SCHEDULE_KEY, None)
            if "schedule" not in payload and legacy_schedule is not None:
                payload["schedule"] = legacy_schedule
            if record_path.name != "config.json":
                self._write_record_bundle(
                    Path(summary.record_path),
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
            self._write_record_bundle(
                Path(summary.record_path),
                payload,
            )
            return payload

    @staticmethod
    def _record_config_path(summary: RecordSummary) -> Path:
        directory = Path(summary.record_path)
        config_path = directory / "config.json"
        if config_path.exists():
            return config_path
        for legacy_name in ("record.json", "session.json"):
            legacy_path = directory / legacy_name
            if legacy_path.exists():
                return legacy_path
        return config_path

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
            record_id = self._next_record_id(now)
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
                self._write_record_bundle(
                    record_dir,
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
            updated_payload = dict(previous_payload)
            updated_payload["status"] = effective_status
            updated_payload["ended_at"] = ended_at
            if effective_status in TERMINAL_RECORD_STATUSES:
                updated_payload = self._with_capture_summaries(
                    Path(summary.record_path),
                    updated_payload,
                )
            try:
                self._write_record_bundle(
                    Path(summary.record_path),
                    updated_payload,
                )
                if summary.status not in TERMINAL_RECORD_STATUSES:
                    self.repository.update_status(
                        record_id,
                        effective_status,
                        ended_at,
                    )
            except Exception:
                try:
                    self._write_record_bundle(
                        Path(summary.record_path),
                        previous_payload,
                    )
                except Exception:
                    logger.exception(
                        "Failed to restore record metadata after update failure: %s",
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
            return RecordDetail(**summary.model_dump(), config=payload)

    def get_record_file(self, record_id: str, file_name: str) -> Path:
        with self._lock:
            summary = self.repository.get(record_id)
            if summary is None:
                raise RecordError(f"找不到紀錄：{record_id}")
            record_path = Path(summary.record_path).resolve()
            if record_path.name != record_id:
                raise RecordError("紀錄儲存位置無效。")
            if file_name not in {"metadata.csv", "config.json"}:
                raise RecordError("不支援的紀錄檔案。")
            file_path = (
                self._record_config_path(summary)
                if file_name == "config.json"
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
