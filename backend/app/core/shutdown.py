from __future__ import annotations

import logging
from contextlib import suppress

logger = logging.getLogger(__name__)


def shutdown_context(context: object) -> None:
    """Best-effort cleanup for hardware, services, and database handles."""
    for attr, method in (
        ("schedule_service", "close"),
        ("motor_controller", "stop"),
        ("motor_controller", "disengage"),
        ("motor_controller", "close"),
        ("camera_manager", "close_all"),
        ("database", "close"),
    ):
        target = getattr(context, attr, None)
        if target is None or not hasattr(target, method):
            continue
        with suppress(Exception):
            getattr(target, method)()
            logger.info("Shutdown step completed: %s.%s", attr, method)
