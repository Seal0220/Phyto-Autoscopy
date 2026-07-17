from __future__ import annotations

import csv
from pathlib import Path
from uuid import uuid4


def write_csv_atomic(
    path: Path,
    fieldnames: list[str] | tuple[str, ...],
    rows: list[dict],
) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field) for field in fieldnames})
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
