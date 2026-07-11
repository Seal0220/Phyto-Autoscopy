from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.core.config import AppSettings


def configure_logging(settings: AppSettings) -> None:
    settings.paths.logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = settings.paths.logs_dir / settings.logging.file_name

    level = getattr(logging, settings.logging.level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.setLevel(level)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    root.addHandler(console)
    root.addHandler(file_handler)
