from __future__ import annotations

import re
from pathlib import Path


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def safe_artifact_name(value: str) -> str:
    normalized = _SAFE_NAME.sub("_", value).strip("._")
    return normalized or "unknown"


def round_key_parts(round_key: str) -> tuple[str, str]:
    try:
        _, mode_id, round_id = round_key.rsplit(":", 2)
    except ValueError as error:
        raise ValueError(f"Round 識別碼格式無效：{round_key}") from error
    return mode_id, round_id


def round_artifact_directory(
    output_root: Path,
    round_key: str,
) -> Path:
    mode_id, round_id = round_key_parts(round_key)
    return (
        output_root
        / "rounds"
        / safe_artifact_name(mode_id)
        / safe_artifact_name(round_id)
    )
