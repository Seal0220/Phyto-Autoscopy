from __future__ import annotations

import re
from pathlib import Path


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def safe_artifact_name(value: str) -> str:
    normalized = _SAFE_NAME.sub("_", value).strip("._")
    return normalized or "unknown"


def round_key_parts(
    round_key: str,
) -> tuple[str, str, str | None]:
    parts = round_key.split(":")
    if len(parts) < 3:
        raise ValueError(f"Round 識別碼格式無效：{round_key}")
    snapshot_id = (
        parts[-1]
        if parts[-1].startswith("snapshot.")
        else None
    )
    if snapshot_id is None:
        mode_id = parts[-2]
        round_id = parts[-1]
    else:
        if len(parts) < 4:
            raise ValueError(f"Round 識別碼格式無效：{round_key}")
        mode_id = parts[-3]
        round_id = parts[-2]
    if not mode_id or not round_id.startswith("round."):
        raise ValueError(f"Round 識別碼格式無效：{round_key}")
    return mode_id, round_id, snapshot_id


def round_artifact_directory(
    output_root: Path,
    round_key: str,
) -> Path:
    mode_id, round_id, snapshot_id = round_key_parts(round_key)
    directory = (
        output_root
        / "rounds"
        / safe_artifact_name(mode_id)
        / safe_artifact_name(round_id)
    )
    if snapshot_id is not None:
        directory /= safe_artifact_name(snapshot_id)
    return directory
