from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from app.core.config import AppSettings, HardwareSettings, PathSettings
from app.database.connection import Database
from app.database.schema import initialize_schema
from app.repositories.record_repository import RecordRepository
from app.services.record_service import RecordService
from app.services.storage_service import StorageService


def create_record_service(tmp_path) -> tuple[
    RecordService,
    RecordRepository,
    StorageService,
    Database,
]:
    settings = AppSettings(
        hardware=HardwareSettings(mock_mode=True),
        paths=PathSettings(
            captures_dir=tmp_path / "records",
            calibration_dir=tmp_path / "calibration",
            database_path=tmp_path / "database.sqlite3",
            logs_dir=tmp_path / "logs",
            temp_dir=tmp_path / "temp",
        ),
    )
    database = Database(settings.paths.database_path)
    initialize_schema(database)
    storage = StorageService(settings)
    storage.ensure_base_dirs()
    repository = RecordRepository(database)
    service = RecordService(settings, storage, repository)
    return service, repository, storage, database


def test_update_status_recovers_empty_record_json(tmp_path) -> None:
    service, repository, storage, database = create_record_service(tmp_path)
    try:
        summary = service.create_record()
        record_path = storage.record_json_path(summary.record_id)
        record_path.write_text("", encoding="utf-8")

        service.update_status(summary.record_id, "completed")

        payload = json.loads(record_path.read_text(encoding="utf-8"))
        stored = repository.get(summary.record_id)
        assert stored is not None
        assert stored.status == "completed"
        assert stored.ended_at is not None
        assert payload["record_id"] == summary.record_id
        assert payload["status"] == "completed"
        assert payload["ended_at"] == stored.ended_at
    finally:
        database.close()


def test_terminal_record_status_cannot_regress(tmp_path) -> None:
    service, repository, storage, database = create_record_service(tmp_path)
    try:
        summary = service.create_record()
        service.update_status(summary.record_id, "stopped")
        terminal_summary = repository.get(summary.record_id)
        assert terminal_summary is not None

        service.update_status(summary.record_id, "stopping")

        stored = repository.get(summary.record_id)
        payload = json.loads(
            storage.record_json_path(summary.record_id).read_text(encoding="utf-8")
        )
        assert stored is not None
        assert stored.status == "stopped"
        assert stored.ended_at == terminal_summary.ended_at
        assert payload["status"] == "stopped"
        assert payload["ended_at"] == terminal_summary.ended_at
    finally:
        database.close()


def test_concurrent_status_updates_keep_record_json_valid(tmp_path) -> None:
    service, _, storage, database = create_record_service(tmp_path)
    try:
        summary = service.create_record()
        statuses = ["paused", "running"] * 25

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [
                executor.submit(service.update_status, summary.record_id, status)
                for status in statuses
            ]
            for future in futures:
                future.result()

        payload = json.loads(
            storage.record_json_path(summary.record_id).read_text(encoding="utf-8")
        )
        assert payload["status"] in {"paused", "running"}
        assert not list(storage.record_dir(summary.record_id).glob(".*.tmp"))
    finally:
        database.close()


def test_old_record_remains_available_after_capture_root_changes(tmp_path) -> None:
    service, repository, _, database = create_record_service(tmp_path)
    try:
        old_summary = service.create_record(status="manual")
        old_record_path = service.get_record_file(
            old_summary.record_id,
            "record.json",
        )
        service.update_status(old_summary.record_id, "completed")

        service.settings.paths.captures_dir = tmp_path / "new-captures"
        service.storage.ensure_base_dirs()
        new_summary = service.create_record(status="manual")

        assert new_summary.record_id != old_summary.record_id
        assert old_record_path.is_file()
        assert service.get_record(old_summary.record_id).status == "completed"
        assert service.get_record_file(
            old_summary.record_id,
            "record.json",
        ) == old_record_path
        assert repository.get(old_summary.record_id) is not None
    finally:
        database.close()


def test_recover_interrupted_records_marks_them_failed(tmp_path) -> None:
    service, repository, _, database = create_record_service(tmp_path)
    try:
        summary = service.create_record(status="running")
        service.release_active_record(summary.record_id)

        recovered = RecordService(
            service.settings,
            service.storage,
            repository,
        )
        recovered.recover_interrupted_records()

        stored = repository.get(summary.record_id)
        assert stored is not None
        assert stored.status == "failed"
        assert stored.ended_at is not None
    finally:
        database.close()


def test_status_file_failure_does_not_change_database(tmp_path, monkeypatch) -> None:
    service, repository, storage, database = create_record_service(tmp_path)
    try:
        summary = service.create_record()
        original_payload = json.loads(
            storage.record_json_path(summary.record_id).read_text(encoding="utf-8")
        )
        monkeypatch.setattr(
            service,
            "_write_record_payload",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("write failed")),
        )

        with pytest.raises(OSError, match="write failed"):
            service.update_status(summary.record_id, "completed")

        stored = repository.get(summary.record_id)
        payload = json.loads(
            storage.record_json_path(summary.record_id).read_text(encoding="utf-8")
        )
        assert stored is not None
        assert stored.status == "running"
        assert payload == original_payload
    finally:
        database.close()


def test_status_database_failure_restores_record_json(tmp_path, monkeypatch) -> None:
    service, repository, storage, database = create_record_service(tmp_path)
    try:
        summary = service.create_record()
        original_payload = json.loads(
            storage.record_json_path(summary.record_id).read_text(encoding="utf-8")
        )
        monkeypatch.setattr(
            repository,
            "update_status",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("database failed")),
        )

        with pytest.raises(OSError, match="database failed"):
            service.update_status(summary.record_id, "completed")

        stored = repository.get(summary.record_id)
        payload = json.loads(
            storage.record_json_path(summary.record_id).read_text(encoding="utf-8")
        )
        assert stored is not None
        assert stored.status == "running"
        assert payload == original_payload
    finally:
        database.close()


def test_legacy_metadata_is_normalized_without_overwriting_source(tmp_path) -> None:
    service, repository, _, database = create_record_service(tmp_path)
    try:
        record_id = "session_legacy"
        record_dir = tmp_path / record_id
        record_dir.mkdir()
        legacy_path = record_dir / "session.json"
        legacy_payload = {
            "session_id": record_id,
            "status": "completed",
            "experiment": {"duration_seconds": 60},
        }
        legacy_text = json.dumps(legacy_payload, ensure_ascii=False)
        legacy_path.write_text(legacy_text, encoding="utf-8")
        repository.upsert(
            record_id,
            "2026-01-01T00:00:00+08:00",
            "completed",
            str(record_dir),
            "2026-01-01T00:01:00+08:00",
        )

        detail = service.get_record(record_id)

        assert detail.record_json["record_id"] == record_id
        assert detail.record_json["schedule"] == {"duration_seconds": 60}
        assert "session_id" not in detail.record_json
        assert "experiment" not in detail.record_json
        assert legacy_path.read_text(encoding="utf-8") == legacy_text
        assert (record_dir / "record.json").is_file()
    finally:
        database.close()


def test_corrupt_legacy_metadata_is_preserved_during_recovery(tmp_path) -> None:
    service, repository, _, database = create_record_service(tmp_path)
    try:
        record_id = "session_corrupt"
        record_dir = tmp_path / record_id
        record_dir.mkdir()
        legacy_path = record_dir / "session.json"
        legacy_path.write_text("{", encoding="utf-8")
        repository.upsert(
            record_id,
            "2026-01-01T00:00:00+08:00",
            "completed",
            str(record_dir),
        )

        detail = service.get_record(record_id)

        assert detail.record_json["record_id"] == record_id
        assert legacy_path.read_text(encoding="utf-8") == "{"
        assert (record_dir / "record.json").is_file()
    finally:
        database.close()
import pytest
