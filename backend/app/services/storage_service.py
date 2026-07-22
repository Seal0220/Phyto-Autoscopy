from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from threading import RLock
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import AppSettings
from app.core.constants import (
    CAMERA_ROLES,
    CAPTURE_MODE_ABBREVIATIONS,
    CAPTURE_MODE_NAMES,
    METADATA_FIELDS,
    MODE_CAPTURE_LOG_FIELDS,
)


CAPTURE_MODE_TYPES_BY_NAME = {
    name: mode_type
    for mode_type, name in CAPTURE_MODE_NAMES.items()
}


def _storage_timezone() -> tzinfo:
    try:
        return ZoneInfo("Asia/Taipei")
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=8), name="Asia/Taipei")


def format_storage_timestamp(value: datetime) -> str:
    return value.astimezone(_storage_timezone()).strftime(
        "%Y.%m.%d-%H.%M.%S.%f"
    )


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

    def next_record_id(self, captured_at: datetime) -> str:
        captures_dir = self.settings.paths.captures_dir
        captures_dir.mkdir(parents=True, exist_ok=True)
        candidate_time = captured_at
        while True:
            timestamp = format_storage_timestamp(candidate_time)
            record_id = f"record_{timestamp}"
            if not (captures_dir / record_id).exists():
                return record_id
            candidate_time += timedelta(microseconds=1)

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
        log_path = record_dir / "record.log.csv"
        if not log_path.exists():
            with log_path.open("w", newline="", encoding="utf-8-sig") as handle:
                csv.DictWriter(
                    handle,
                    fieldnames=MODE_CAPTURE_LOG_FIELDS,
                ).writeheader()
        return record_dir

    def config_path(self, record_id: str) -> Path:
        return self.record_dir(record_id) / "config.json"

    def mode_dir(
        self,
        record_id: str,
        mode_folder: str,
        record_path: str | Path | None = None,
    ) -> Path:
        record_dir = self._record_directory(record_id, record_path)
        return record_dir / "modes" / mode_folder

    def create_mode_layout(
        self,
        record_id: str,
        mode_folder: str,
        record_path: str | Path | None = None,
    ) -> Path:
        mode_dir = self.mode_dir(
            record_id,
            mode_folder,
            record_path,
        )
        mode_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = mode_dir / "metadata.csv"
        if not metadata_path.exists():
            with metadata_path.open("w", newline="", encoding="utf-8-sig") as handle:
                csv.DictWriter(handle, fieldnames=METADATA_FIELDS).writeheader()
        log_path = mode_dir / "mode.log.csv"
        if not log_path.exists():
            with log_path.open("w", newline="", encoding="utf-8-sig") as handle:
                csv.DictWriter(handle, fieldnames=MODE_CAPTURE_LOG_FIELDS).writeheader()
        return mode_dir

    def mode_log_path(
        self,
        record_id: str,
        mode_folder: str,
        record_path: str | Path | None = None,
    ) -> Path:
        mode_dir = self.mode_dir(
            record_id,
            mode_folder,
            record_path,
        )
        return mode_dir / "mode.log.csv"

    def mode_metadata_path(
        self,
        record_id: str,
        mode_folder: str,
        record_path: str | Path | None = None,
    ) -> Path:
        return self.mode_dir(
            record_id,
            mode_folder,
            record_path,
        ) / "metadata.csv"

    def _append_csv_rows(
        self,
        paths: tuple[Path, ...],
        fieldnames: tuple[str, ...],
        record: dict,
    ) -> None:
        previous_sizes: dict[Path, int] = {}
        try:
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                if not path.exists():
                    with path.open("w", newline="", encoding="utf-8-sig") as handle:
                        csv.DictWriter(handle, fieldnames=fieldnames).writeheader()
                previous_sizes[path] = path.stat().st_size
                with path.open("a", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fieldnames)
                    writer.writerow({field: record.get(field) for field in fieldnames})
        except Exception:
            for path, previous_size in previous_sizes.items():
                with path.open("r+b") as handle:
                    handle.truncate(previous_size)
            raise

    def append_mode_log(
        self,
        record_id: str,
        mode_folder: str,
        record: dict,
        record_path: str | Path | None = None,
    ) -> None:
        self.create_mode_layout(
            record_id,
            mode_folder,
            record_path,
        )
        with self._lock:
            self._append_csv_rows(
                (
                    self._record_directory(record_id, record_path)
                    / "record.log.csv",
                    self.mode_log_path(record_id, mode_folder, record_path),
                ),
                MODE_CAPTURE_LOG_FIELDS,
                record,
            )

    def metadata_path(
        self,
        record_id: str,
        record_path: str | Path | None = None,
    ) -> Path:
        return self._record_directory(record_id, record_path) / "metadata.csv"

    @staticmethod
    def _mode_filename_parts(mode_folder: str) -> tuple[str, str]:
        try:
            mode_name, mode_number = mode_folder.rsplit(".", 1)
            mode_type = CAPTURE_MODE_TYPES_BY_NAME[mode_name]
            number = int(mode_number)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid capture mode folder: {mode_folder}") from exc
        return CAPTURE_MODE_ABBREVIATIONS[mode_type], f"{number:02d}"

    def _round_dir(
        self,
        mode_dir: Path,
        round_number: int,
    ) -> Path:
        path = mode_dir / "rounds" / f"round.{round_number:02d}"
        path.mkdir(parents=True, exist_ok=True)
        return path

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
        captured_at: datetime,
        continuous: bool,
        record_path: str | Path | None = None,
    ) -> Path:
        mode_dir = self.create_mode_layout(
            record_id,
            mode_folder,
            record_path,
        )
        timestamp = format_storage_timestamp(captured_at)
        round_number = 0 if continuous else cycle_id
        round_dir = self._round_dir(
            mode_dir,
            round_number,
        )
        folder = round_dir / f"snapshot.{capture_index:02d}_{timestamp}"
        folder.mkdir(parents=True, exist_ok=True)
        abbreviation, mode_number = self._mode_filename_parts(mode_folder)
        filename = (
            f"{camera_id}-{abbreviation}.{mode_number}_"
            f"r.{round_number:02d}_s.{capture_index:02d}_{timestamp}.jpg"
        )
        return folder / filename

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
        candidate_time = captured_at
        while True:
            timestamp = format_storage_timestamp(candidate_time)
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
