from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from app.core.config import AppSettings, PathSettings
from app.services.storage_service import StorageService


def test_rotating_path_uses_cycle_and_angle(tmp_path) -> None:
    settings = AppSettings(paths=PathSettings(captures_dir=tmp_path))
    storage = StorageService(settings)
    storage.create_record_layout("record_test_001")
    path = storage.next_capture_path("record_test_001", "rotating", cycle_id=2, angle_deg=15)
    assert path.name == "angle_015.0.png"
    assert path.parent.name == "cycle_000002"


def test_concurrent_snapshots_with_same_timestamp_do_not_overwrite(tmp_path) -> None:
    settings = AppSettings(
        paths=PathSettings(
            captures_dir=tmp_path / "captures",
            snapshots_dir=tmp_path / "snapshots",
        )
    )
    storage = StorageService(settings)
    captured_at = datetime(2026, 7, 13, tzinfo=timezone.utc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        paths = list(
            executor.map(
                lambda data: storage.save_snapshot("top", captured_at, data),
                (b"first", b"second"),
            )
        )

    assert len(set(paths)) == 2
    assert {path.read_bytes() for path in paths} == {b"first", b"second"}
    assert all(path.parent == settings.paths.snapshots_dir for path in paths)
