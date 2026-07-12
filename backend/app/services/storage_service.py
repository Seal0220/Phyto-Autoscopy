from __future__ import annotations

import csv
from pathlib import Path

from app.core.config import AppSettings
from app.core.constants import METADATA_FIELDS, MODE_CAPTURE_LOG_FIELDS


class StorageService:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def ensure_base_dirs(self) -> None:
        for path in (
            self.settings.paths.captures_dir,
            self.settings.paths.calibration_dir,
            self.settings.paths.database_path.parent,
            self.settings.paths.logs_dir,
            self.settings.paths.temp_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def next_session_id(self, date_label: str) -> str:
        captures_dir = self.settings.paths.captures_dir
        captures_dir.mkdir(parents=True, exist_ok=True)
        prefix = f"session_{date_label}_"
        existing = sorted(path.name for path in captures_dir.glob(f"{prefix}*") if path.is_dir())
        next_index = 1
        if existing:
            last = existing[-1].rsplit("_", 1)[-1]
            if last.isdigit():
                next_index = int(last) + 1
        return f"{prefix}{next_index:03d}"

    def session_dir(self, session_id: str) -> Path:
        return self.settings.paths.captures_dir / session_id

    def create_session_layout(self, session_id: str, include_camera_dirs: bool = True) -> Path:
        session_dir = self.session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        if include_camera_dirs:
            for relative in ("top", "fixed_side", "rotating_arm"):
                (session_dir / relative).mkdir(parents=True, exist_ok=True)

        metadata_path = session_dir / "metadata.csv"
        if not metadata_path.exists():
            with metadata_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=METADATA_FIELDS)
                writer.writeheader()
        return session_dir

    def session_json_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "session.json"

    def create_mode_layout(self, session_id: str, mode_folder: str) -> Path:
        mode_dir = self.session_dir(session_id) / "modes" / mode_folder
        for camera_id in ("top", "fixed_side", "rotating_arm"):
            (mode_dir / camera_id).mkdir(parents=True, exist_ok=True)
        log_path = mode_dir / "capture_log.csv"
        if not log_path.exists():
            with log_path.open("w", newline="", encoding="utf-8-sig") as handle:
                csv.DictWriter(handle, fieldnames=MODE_CAPTURE_LOG_FIELDS).writeheader()
        return mode_dir

    def mode_log_path(self, session_id: str, mode_folder: str) -> Path:
        return self.session_dir(session_id) / "modes" / mode_folder / "capture_log.csv"

    def append_mode_log(self, session_id: str, mode_folder: str, record: dict) -> None:
        log_path = self.mode_log_path(session_id, mode_folder)
        with log_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=MODE_CAPTURE_LOG_FIELDS)
            writer.writerow({field: record.get(field) for field in MODE_CAPTURE_LOG_FIELDS})

    def metadata_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "metadata.csv"

    def next_capture_path(
        self,
        session_id: str,
        camera_id: str,
        cycle_id: int | None = None,
        angle_deg: float | None = None,
    ) -> Path:
        session_dir = self.session_dir(session_id)
        if camera_id == "rotating_arm":
            cycle = cycle_id or 1
            folder = session_dir / "rotating_arm" / f"cycle_{cycle:06d}"
            folder.mkdir(parents=True, exist_ok=True)
            angle = 0.0 if angle_deg is None else angle_deg
            return folder / f"angle_{angle:05.1f}.jpg"

        folder = session_dir / camera_id
        folder.mkdir(parents=True, exist_ok=True)
        next_index = len(list(folder.glob("*.jpg"))) + 1
        return folder / f"{next_index:06d}.jpg"

    def next_mode_capture_path(
        self,
        session_id: str,
        mode_folder: str,
        camera_id: str,
        cycle_id: int,
        capture_index: int,
        angle_deg: float,
    ) -> Path:
        folder = self.session_dir(session_id) / "modes" / mode_folder / camera_id
        folder.mkdir(parents=True, exist_ok=True)
        return folder / (
            f"cycle_{cycle_id:06d}_capture_{capture_index:06d}_angle_{angle_deg:06.2f}.jpg"
        )

    def relative_to_session(self, session_id: str, path: Path) -> str:
        return path.relative_to(self.session_dir(session_id)).as_posix()

    def save_bytes(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
