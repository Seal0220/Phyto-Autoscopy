from __future__ import annotations

from threading import Lock


class MotorWorker:
    """Serializes motor tasks so only one movement can own the controller at a time."""

    def __init__(self) -> None:
        self._lock = Lock()

    def run(self, callback):
        with self._lock:
            return callback()
