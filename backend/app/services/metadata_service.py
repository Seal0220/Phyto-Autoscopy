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
    ) -> None:
        metadata_path = self.storage.metadata_path(record.record_id, record_path)
        with self._lock:
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            if not metadata_path.exists():
                with metadata_path.open("w", newline="", encoding="utf-8") as handle:
                    csv.DictWriter(handle, fieldnames=METADATA_FIELDS).writeheader()
            previous_size = metadata_path.stat().st_size
            with metadata_path.open("a", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=METADATA_FIELDS)
                writer.writerow(record.model_dump())
            try:
                self.repository.insert(record)
            except Exception:
                with metadata_path.open("r+b") as handle:
                    handle.truncate(previous_size)
                raise
