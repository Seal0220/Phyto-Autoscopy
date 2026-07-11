from __future__ import annotations

import csv

from app.core.constants import METADATA_FIELDS
from app.models.capture_models import MetadataRecord
from app.repositories.capture_repository import CaptureRepository
from app.services.storage_service import StorageService


class MetadataService:
    def __init__(self, storage: StorageService, repository: CaptureRepository) -> None:
        self.storage = storage
        self.repository = repository

    def append(self, record: MetadataRecord) -> None:
        metadata_path = self.storage.metadata_path(record.session_id)
        with metadata_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=METADATA_FIELDS)
            writer.writerow(record.model_dump())
        self.repository.insert(record)
