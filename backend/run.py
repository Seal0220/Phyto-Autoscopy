from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn

from app.core.runtime_paths import prepare_runtime_paths

DEFAULT_PORT = 22222


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE pairs without adding a runtime dependency."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def load_runtime_environment() -> None:
    backend_dir = Path(__file__).resolve().parent
    load_env_file(backend_dir.parent / ".env")
    load_env_file(backend_dir / ".env")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start the Phyto-Autoscopy CHLOROCULUS control interface."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--reload", action="store_true", help="Enable Uvicorn reload for development.")
    return parser.parse_args()


def main() -> None:
    load_runtime_environment()
    migrated_data = prepare_runtime_paths()
    args = parse_args()
    # Development/reload changes the server process only. It must never
    # silently replace physical cameras or the motor with mock hardware.
    os.environ["PHYTO_AUTOSCOPY_MOCK"] = "0"

    if migrated_data:
        print("已將 backend/data 的既有資料移至專案根目錄 data。")

    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        ws="auto",
    )


if __name__ == "__main__":
    main()
