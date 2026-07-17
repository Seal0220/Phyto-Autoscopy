from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4


def write_json_atomic(path: Path, payload: object) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))
