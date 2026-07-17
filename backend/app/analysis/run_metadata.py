from __future__ import annotations

from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from threading import RLock


_identifier_lock = RLock()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def next_dated_identifier(
    root: Path,
    prefix: str,
    *,
    date_label: str | None = None,
) -> str:
    label = date_label or datetime.now().strftime("%Y-%m-%d")
    root.mkdir(parents=True, exist_ok=True)
    with _identifier_lock:
        existing = {
            path.name
            for path in root.rglob(f"{prefix}_{label}_*")
            if path.is_dir()
        }
        index = 1
        while f"{prefix}_{label}_{index:03d}" in existing:
            index += 1
        return f"{prefix}_{label}_{index:03d}"


def repository_commit(project_root: Path) -> str:
    git_directory = project_root / ".git"
    try:
        head = (git_directory / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            reference = head.split(":", 1)[1].strip()
            reference_path = git_directory / reference
            if reference_path.is_file():
                return reference_path.read_text(encoding="utf-8").strip()
            packed_refs = git_directory / "packed-refs"
            if packed_refs.is_file():
                for line in packed_refs.read_text(encoding="utf-8").splitlines():
                    if line and not line.startswith(("#", "^")):
                        commit, name = line.split(" ", 1)
                        if name == reference:
                            return commit
            return "unknown"
        return head if len(head) >= 7 else "unknown"
    except (OSError, UnicodeError, ValueError):
        return "unknown"


def runtime_versions() -> dict[str, str]:
    packages = {
        "opencv": "opencv-python",
        "numpy": "numpy",
        "scipy": "scipy",
        "pandas": "pandas",
    }
    result = {}
    for key, package in packages.items():
        try:
            result[key] = version(package)
        except PackageNotFoundError:
            result[key] = "not-installed"
    return result
