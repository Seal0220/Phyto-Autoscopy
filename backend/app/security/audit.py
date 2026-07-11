from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

_audit_lock = Lock()


def _audit_log_path() -> Path:
    configured = os.environ.get("PHYTO_AUTOSCOPY_AUDIT_LOG", "data/logs/audit.jsonl")
    return Path(configured)


def write_audit_event(
    *,
    actor: str,
    role: str,
    action: str,
    outcome: str,
    detail: str | None = None,
) -> None:
    """Append a minimal, non-secret operation record for later review."""
    record: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "role": role,
        "action": action,
        "outcome": outcome,
    }
    if detail:
        record["detail"] = detail[:500]

    path = _audit_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _audit_lock, path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        # Audit storage must not leave hardware in a half-completed state. The
        # server logger still receives the underlying operation failure.
        return

