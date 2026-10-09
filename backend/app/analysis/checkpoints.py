from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from app.analysis.run_metadata import utc_now_iso


def step_signature(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class StepJournal:
    """Small durable step records; never rewrite the full input manifest per image."""

    def __init__(self, root: Path) -> None:
        self.path = root / "checkpoints" / "steps.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=30)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS steps (stage TEXT, item TEXT, signature TEXT, "
            "payload TEXT, updated_at TEXT, PRIMARY KEY(stage, item))"
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS steps_recent ON steps(updated_at DESC) "
            "WHERE stage != 'control'"
        )
        self.connection.commit()

    def get(self, stage: str, item: str, signature: str | None = None) -> dict | None:
        row = self.connection.execute(
            "SELECT signature,payload FROM steps WHERE stage=? AND item=?", (stage, item),
        ).fetchone()
        if row is None or (signature is not None and signature != row[0]):
            return None
        payload = json.loads(row[1])
        for output in payload.get("outputs", []):
            path = Path(output["path"])
            try:
                stat = path.stat()
            except OSError:
                return None
            if [stat.st_size, stat.st_mtime_ns] != output["stat"]:
                return None
        return payload

    def save(self, stage: str, item: str, signature: str, payload: dict, *, outputs=()) -> None:
        payload = dict(payload)
        payload["outputs"] = [
            {"path": str(path), "stat": [path.stat().st_size, path.stat().st_mtime_ns]}
            for path in map(Path, outputs)
        ]
        with self.connection:
            self.connection.execute(
                "INSERT INTO steps VALUES (?,?,?,?,?) ON CONFLICT(stage,item) DO UPDATE SET "
                "signature=excluded.signature,payload=excluded.payload,updated_at=excluded.updated_at",
                (stage, item, signature, json.dumps(payload, ensure_ascii=False), utc_now_iso()),
            )

    def close(self) -> None:
        self.connection.close()

    def invalidate(self, item: str, stages: tuple[str, ...]) -> None:
        """Invalidate only the selected round's derived steps after correction."""
        with self.connection:
            self.connection.executemany("DELETE FROM steps WHERE stage=? AND item=?", [(stage, item) for stage in stages])

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def checkpoint_summary(root: Path) -> dict:
    path = root / "checkpoints" / "steps.sqlite3"
    if not path.is_file():
        return {"completed_steps": 0, "recent_steps": []}
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)) as connection:
        count = connection.execute("SELECT COUNT(*) FROM steps WHERE stage != 'control'").fetchone()[0]
        rows = connection.execute(
            "SELECT stage,item,updated_at,payload FROM steps WHERE stage != 'control' "
            "ORDER BY updated_at DESC LIMIT 8"
        ).fetchall()
    return {
        "completed_steps": count,
        "recent_steps": [
            {"stage": stage, "item": item, "updated_at": timestamp,
             "backend": json.loads(payload).get("backend")}
            for stage, item, timestamp, payload in rows
        ],
    }
