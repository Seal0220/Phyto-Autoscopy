from __future__ import annotations

import csv
from pathlib import Path
from threading import RLock

from app.core.constants import METADATA_FIELDS
from app.models.capture_models import MetadataRecord
from app.repositories.capture_repository import CaptureRepository
from app.services.storage_service import StorageService


class MetadataService:
    def __init__(self, storage: StorageService, repository: CaptureRepository) -> None:
        self.storage = storage
        self.repository = repository
        self._lock = RLock()

    def append(
        self,
        record: MetadataRecord,
        record_path: str | Path | None = None,
        mode_folder: str | None = None,
    ) -> None:
        metadata_paths = [
            self.storage.metadata_path(record.record_id, record_path),
        ]
        if mode_folder is not None:
            self.storage.create_mode_layout(
                record.record_id,
                mode_folder,
                record_path,
            )
            metadata_paths.append(
                self.storage.mode_metadata_path(
                    record.record_id,
                    mode_folder,
                    record_path,
                )
            )
        with self._lock:
            previous_sizes: dict[Path, int] = {}
            try:
                for metadata_path in metadata_paths:
                    metadata_path.parent.mkdir(parents=True, exist_ok=True)
                    if not metadata_path.exists():
                        with metadata_path.open(
                            "w",
                            newline="",
                            encoding="utf-8-sig",
                        ) as handle:
                            csv.DictWriter(
                                handle,
                                fieldnames=METADATA_FIELDS,
                            ).writeheader()
                    previous_sizes[metadata_path] = metadata_path.stat().st_size
                    with metadata_path.open(
                        "a",
                        newline="",
                        encoding="utf-8",
                    ) as handle:
                        writer = csv.DictWriter(
                            handle,
                            fieldnames=METADATA_FIELDS,
                        )
                        writer.writerow(record.model_dump())
                self.repository.insert(record)
            except Exception:
                for metadata_path, previous_size in previous_sizes.items():
                    with metadata_path.open("r+b") as handle:
                        handle.truncate(previous_size)
                raise
