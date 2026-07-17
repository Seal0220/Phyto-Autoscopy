from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4

from app.core.config import AppSettings
from app.core.constants import CAMERA_ROLES, METADATA_FIELDS, MODE_CAPTURE_LOG_FIELDS


class StorageService:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self._lock = RLock()

    def ensure_base_dirs(self) -> None:
        for path in (
            self.settings.paths.captures_dir,
            self.settings.paths.snapshots_dir,
            self.settings.paths.calibration_dir,
            self.settings.paths.analysis_dir,
            self.settings.paths.database_path.parent,
            self.settings.paths.logs_dir,
            self.settings.paths.temp_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def next_record_id(self, date_label: str) -> str:
        captures_dir = self.settings.paths.captures_dir
        captures_dir.mkdir(parents=True, exist_ok=True)
        prefix = f"record_{date_label}_"
        existing = sorted(path.name for path in captures_dir.glob(f"{prefix}*") if path.is_dir())
        next_index = 1
        if existing:
            last = existing[-1].rsplit("_", 1)[-1]
            if last.isdigit():
                next_index = int(last) + 1
        return f"{prefix}{next_index:03d}"

    def record_dir(self, record_id: str) -> Path:
        return self.settings.paths.captures_dir / record_id

    def _record_directory(
        self,
        record_id: str,
        record_path: str | Path | None = None,
    ) -> Path:
        return Path(record_path) if record_path is not None else self.record_dir(record_id)

    def create_record_layout(self, record_id: str, include_camera_dirs: bool = True) -> Path:
        record_dir = self.record_dir(record_id)
        record_dir.mkdir(parents=True, exist_ok=True)
        if include_camera_dirs:
            for relative in CAMERA_ROLES:
                (record_dir / relative).mkdir(parents=True, exist_ok=True)

        metadata_path = record_dir / "metadata.csv"
        if not metadata_path.exists():
            with metadata_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=METADATA_FIELDS)
                writer.writeheader()
        return record_dir

    def record_json_path(self, record_id: str) -> Path:
        return self.record_dir(record_id) / "record.json"

    def create_mode_layout(self, record_id: str, mode_folder: str) -> Path:
        mode_dir = self.record_dir(record_id) / "modes" / mode_folder
        for camera_id in CAMERA_ROLES:
            (mode_dir / camera_id).mkdir(parents=True, exist_ok=True)
        log_path = mode_dir / "capture_log.csv"
        if not log_path.exists():
            with log_path.open("w", newline="", encoding="utf-8-sig") as handle:
                csv.DictWriter(handle, fieldnames=MODE_CAPTURE_LOG_FIELDS).writeheader()
        return mode_dir

    def mode_log_path(self, record_id: str, mode_folder: str) -> Path:
        return self.record_dir(record_id) / "modes" / mode_folder / "capture_log.csv"

    def append_mode_log(self, record_id: str, mode_folder: str, record: dict) -> None:
        log_path = self.mode_log_path(record_id, mode_folder)
        with self._lock:
            with log_path.open("a", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=MODE_CAPTURE_LOG_FIELDS)
                writer.writerow({field: record.get(field) for field in MODE_CAPTURE_LOG_FIELDS})

    def metadata_path(
        self,
        record_id: str,
        record_path: str | Path | None = None,
    ) -> Path:
        return self._record_directory(record_id, record_path) / "metadata.csv"

    def next_capture_path(
        self,
        record_id: str,
        camera_id: str,
        cycle_id: int | None = None,
        angle_deg: float | None = None,
        record_path: str | Path | None = None,
    ) -> Path:
        record_dir = self._record_directory(record_id, record_path)
        if camera_id == "rotating":
            cycle = cycle_id or 1
            folder = record_dir / "rotating" / f"cycle_{cycle:06d}"
            folder.mkdir(parents=True, exist_ok=True)
            angle = 0.0 if angle_deg is None else angle_deg
            return folder / f"angle_{angle:05.1f}.jpg"

        folder = record_dir / camera_id
        folder.mkdir(parents=True, exist_ok=True)
        next_index = len(list(folder.glob("*.jpg"))) + 1
        return folder / f"{next_index:06d}.jpg"

    def next_mode_capture_path(
        self,
        record_id: str,
        mode_folder: str,
        camera_id: str,
        cycle_id: int,
        capture_index: int,
        angle_deg: float,
        record_path: str | Path | None = None,
    ) -> Path:
        folder = (
            self._record_directory(record_id, record_path)
            / "modes"
            / mode_folder
            / camera_id
        )
        folder.mkdir(parents=True, exist_ok=True)
        return folder / (
            f"cycle_{cycle_id:06d}_capture_{capture_index:06d}_angle_{angle_deg:06.2f}.jpg"
        )

    def relative_to_record(
        self,
        record_id: str,
        path: Path,
        record_path: str | Path | None = None,
    ) -> str:
        return path.relative_to(self._record_directory(record_id, record_path)).as_posix()

    def save_bytes(self, path: Path, data: bytes) -> None:
        temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            temporary_path.write_bytes(data)
            temporary_path.replace(path)
        finally:
            temporary_path.unlink(missing_ok=True)

    def next_snapshot_path(self, camera_id: str, captured_at: datetime) -> Path:
        if camera_id not in CAMERA_ROLES:
            raise ValueError(f"Unsupported snapshot camera: {camera_id}")
        directory = self.settings.paths.snapshots_dir
        directory.mkdir(parents=True, exist_ok=True)
        candidate_time = captured_at.astimezone(timezone.utc)
        while True:
            timestamp = candidate_time.strftime("%Y%m%dT%H%M%S%fZ")
            path = directory / f"{camera_id}_{timestamp}.jpg"
            if not path.exists():
                return path
            candidate_time += timedelta(microseconds=1)

    def save_snapshot(
        self,
        camera_id: str,
        captured_at: datetime,
        data: bytes,
    ) -> Path:
        with self._lock:
            path = self.next_snapshot_path(camera_id, captured_at)
            self.save_bytes(path, data)
            return path
