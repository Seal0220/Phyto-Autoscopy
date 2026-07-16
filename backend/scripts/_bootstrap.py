"""Make backend helper scripts runnable from either project directory."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def bootstrap() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    project_root = backend_root.parent
    backend_root_text = str(backend_root)
    if backend_root_text not in sys.path:
        sys.path.insert(0, backend_root_text)
    os.chdir(project_root)
