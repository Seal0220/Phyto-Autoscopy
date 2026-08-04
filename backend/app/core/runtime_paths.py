from __future__ import annotations

import filecmp
import os
from pathlib import Path

from app.core.config import (
    ensure_path_mappings_file,
    resolve_mapped_project_path,
)


BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent


def _next_conflict_path(target: Path) -> Path:
    counter = 1
    while True:
        suffix = ".from-backend" if counter == 1 else f".from-backend-{counter}"
        candidate = target.with_name(f"{target.stem}{suffix}{target.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _merge_line_file(source: Path, target: Path) -> None:
    target_text = target.read_text(encoding="utf-8")
    existing_lines = {
        line
        for line in target_text.splitlines()
        if line
    }
    incoming_lines = source.read_text(encoding="utf-8").splitlines()
    new_lines = [line for line in incoming_lines if line and line not in existing_lines]

    if new_lines:
        with target.open("a", encoding="utf-8") as handle:
            if target_text and not target_text.endswith(("\n", "\r")):
                handle.write("\n")
            handle.write("\n".join(new_lines))
            handle.write("\n")

    source.unlink()


def _move_legacy_item(source: Path, target: Path) -> None:
    if source.is_dir():
        children = list(source.iterdir())
        if not children:
            source.rmdir()
            return
        target.mkdir(parents=True, exist_ok=True)
        for child in children:
            _move_legacy_item(child, target / child.name)
        source.rmdir()
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        source.replace(target)
        return

    if source.name == ".gitkeep" or filecmp.cmp(source, target, shallow=False):
        source.unlink()
        return

    if source.suffix.lower() in {".jsonl", ".log"}:
        try:
            _merge_line_file(source, target)
            return
        except (OSError, UnicodeError):
            pass

    source.replace(_next_conflict_path(target))


def migrate_legacy_backend_data(
    *,
    project_root: Path = PROJECT_ROOT,
    backend_root: Path = BACKEND_ROOT,
    target_data_root: Path | None = None,
) -> bool:
    legacy_data = backend_root / "data"
    project_data = target_data_root or project_root / "data"

    if not legacy_data.exists() or legacy_data.resolve() == project_data.resolve():
        return False

    project_data.mkdir(parents=True, exist_ok=True)
    for item in legacy_data.iterdir():
        _move_legacy_item(item, project_data / item.name)
    legacy_data.rmdir()
    return True


def prepare_runtime_paths(
    *,
    project_root: Path = PROJECT_ROOT,
    backend_root: Path = BACKEND_ROOT,
) -> bool:
    configured = Path(os.environ.get("PHYTO_AUTOSCOPY_CONFIG_DIR", "config"))
    if not configured.is_absolute():
        configured = backend_root / configured
    os.environ["PHYTO_AUTOSCOPY_CONFIG_DIR"] = str(configured.resolve())

    os.chdir(project_root)
    ensure_path_mappings_file(
        configured,
        project_root=project_root,
    )

    audit_log = Path(
        os.environ.get(
            "PHYTO_AUTOSCOPY_AUDIT_LOG",
            "data/logs/audit.jsonl",
        )
    )
    if not audit_log.is_absolute():
        audit_log = resolve_mapped_project_path(
            audit_log,
            configured,
            project_root=project_root,
        )
    os.environ["PHYTO_AUTOSCOPY_AUDIT_LOG"] = str(audit_log.resolve())

    data_root = resolve_mapped_project_path(
        "data",
        configured,
        project_root=project_root,
    )
    return migrate_legacy_backend_data(
        project_root=project_root,
        backend_root=backend_root,
        target_data_root=data_root,
    )
