from __future__ import annotations

import json
from pathlib import Path
from time import sleep
from uuid import uuid4


def write_json_atomic(path: Path, payload: object) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        # Windows readers and virus scanners can briefly deny delete sharing.
        # Keep the old JSON intact while retrying the atomic replacement.
        delays = (0.01, 0.02, 0.04, 0.08, 0.16)
        for attempt in range(len(delays) + 1):
            try:
                temporary.replace(path)
                break
            except OSError as error:
                if (
                    getattr(error, "winerror", None) not in {5, 32, 33}
                    or attempt == len(delays)
                ):
                    raise
                sleep(delays[attempt])
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))
