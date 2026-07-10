from __future__ import annotations

import argparse
import os

import uvicorn

DEFAULT_PORT = 22222


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start the Phyto-Autoscopy CHLOROCULUS control interface."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--mock", action="store_true", help="Use mock cameras and mock motor.")
    parser.add_argument("--reload", action="store_true", help="Enable Uvicorn reload for development.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.mock:
        os.environ["PHYTO_AUTOSCOPY_MOCK"] = "1"

    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        ws="websockets",
    )


if __name__ == "__main__":
    main()
