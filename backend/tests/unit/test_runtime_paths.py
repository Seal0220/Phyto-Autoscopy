from __future__ import annotations

import os
from pathlib import Path

from app.core.runtime_paths import (
    migrate_legacy_backend_data,
    prepare_runtime_paths,
)


def test_legacy_backend_data_moves_to_project_data_without_losing_logs(
    tmp_path: Path,
) -> None:
    backend_root = tmp_path / "backend"
    legacy_data = backend_root / "data"
    project_data = tmp_path / "data"
    (legacy_data / "captures" / "record-1").mkdir(parents=True)
    (legacy_data / "captures" / "record-1" / "image.jpg").write_bytes(b"jpeg")
    (legacy_data / "database").mkdir(parents=True)
    (legacy_data / "database" / "phyto_autoscopy.sqlite3").write_bytes(b"sqlite")
    (legacy_data / "records").mkdir(parents=True)
    (legacy_data / "logs").mkdir(parents=True)
    (legacy_data / "logs" / "audit.jsonl").write_text(
        '{"timestamp":"legacy"}\n',
        encoding="utf-8",
    )
    (project_data / "logs").mkdir(parents=True)
    (project_data / "logs" / "audit.jsonl").write_text(
        '{"timestamp":"root"}\n',
        encoding="utf-8",
    )

    migrated = migrate_legacy_backend_data(
        project_root=tmp_path,
        backend_root=backend_root,
    )

    assert migrated is True
    assert not legacy_data.exists()
    assert (project_data / "captures" / "record-1" / "image.jpg").read_bytes() == b"jpeg"
    assert (project_data / "database" / "phyto_autoscopy.sqlite3").read_bytes() == b"sqlite"
    assert not (project_data / "records").exists()
    audit_lines = (project_data / "logs" / "audit.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    assert audit_lines == [
        '{"timestamp":"root"}',
        '{"timestamp":"legacy"}',
    ]


def test_runtime_paths_anchor_data_to_project_and_config_to_backend(
    tmp_path: Path,
    monkeypatch,
) -> None:
    backend_root = tmp_path / "backend"
    backend_root.mkdir()
    original_directory = Path.cwd()
    monkeypatch.setenv("PHYTO_AUTOSCOPY_CONFIG_DIR", "config")
    monkeypatch.setenv(
        "PHYTO_AUTOSCOPY_AUDIT_LOG",
        "data/logs/audit.jsonl",
    )

    try:
        migrated = prepare_runtime_paths(
            project_root=tmp_path,
            backend_root=backend_root,
        )

        assert migrated is False
        assert Path.cwd() == tmp_path
        assert Path(os.environ["PHYTO_AUTOSCOPY_CONFIG_DIR"]) == (
            backend_root / "config"
        )
        assert Path(os.environ["PHYTO_AUTOSCOPY_AUDIT_LOG"]) == (
            tmp_path / "data" / "logs" / "audit.jsonl"
        )
    finally:
        os.chdir(original_directory)
