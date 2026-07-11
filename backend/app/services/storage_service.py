from __future__ import annotations

import csv
from pathlib import Path

from app.core.config import AppSettings
from app.core.constants import METADATA_FIELDS


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

    def create_session_layout(self, session_id: str) -> Path:
        session_dir = self.session_dir(session_id)
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

    def relative_to_session(self, session_id: str, path: Path) -> str:
        return path.relative_to(self.session_dir(session_id)).as_posix()

    def save_bytes(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
