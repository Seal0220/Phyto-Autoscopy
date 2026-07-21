from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from threading import RLock

from app.core.exceptions import CalibrationError
from app.models.calibration_models import (
    CalibrationLockRequest,
    CalibrationLockStatus,
)


CALIBRATION_LOCK_LEASE_MINUTES = 30
ACTIVE_SCHEDULE_STATUSES = frozenset({"running", "paused", "stopping"})
logger = logging.getLogger(__name__)


class CalibrationLockService:
    def __init__(self, schedule_service: object) -> None:
        self.schedule_service = schedule_service
        self._lock = RLock()
        self._status = CalibrationLockStatus()
        self._release_callback: Callable[
            [CalibrationLockStatus, str],
            None,
        ] | None = None

    def set_release_callback(
        self,
        callback: Callable[[CalibrationLockStatus, str], None],
    ) -> None:
        with self._lock:
            self._release_callback = callback

    def _clear(self, reason: str) -> CalibrationLockStatus:
        previous = self._status.model_copy(deep=True)
        self._status = CalibrationLockStatus()
        if previous.locked and self._release_callback is not None:
            try:
                self._release_callback(previous, reason)
            except Exception:
                logger.exception(
                    "Calibration lock release cleanup failed: %s",
                    reason,
                )
        return self._status

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _normalized_status(self) -> CalibrationLockStatus:
        if not self._status.locked or self._status.expires_at is None:
            return self._status
        try:
            expires_at = datetime.fromisoformat(self._status.expires_at)
        except ValueError:
            expires_at = self._now()
        if expires_at <= self._now():
            self._clear("expired")
        return self._status

    def status(self) -> CalibrationLockStatus:
        with self._lock:
            return self._normalized_status().model_copy(deep=True)

    def acquire(
        self,
        owner: str,
        request: CalibrationLockRequest,
    ) -> CalibrationLockStatus:
        with self._lock:
            if self.schedule_service.get_status().status in ACTIVE_SCHEDULE_STATUSES:
                raise CalibrationError("排程進行中，無法開始相機校正。請先停止排程。")
            current = self._normalized_status()
            if current.locked and current.owner != owner:
                raise CalibrationError("另一位操作人員正在執行相機校正，請稍後再試。")
            now = self._now()
            self._status = CalibrationLockStatus(
                locked=True,
                owner=owner,
                mode=request.mode,
                run_id=request.run_id,
                acquired_at=current.acquired_at or now.isoformat(),
                expires_at=(
                    now + timedelta(minutes=CALIBRATION_LOCK_LEASE_MINUTES)
                ).isoformat(),
            )
            return self._status.model_copy(deep=True)

    def refresh(self, owner: str) -> CalibrationLockStatus:
        with self._lock:
            self.ensure_owner(owner)
            now = self._now()
            self._status = self._status.model_copy(
                update={
                    "expires_at": (
                        now + timedelta(minutes=CALIBRATION_LOCK_LEASE_MINUTES)
                    ).isoformat(),
                },
                deep=True,
            )
            return self._status.model_copy(deep=True)

    def ensure_owner(self, owner: str) -> CalibrationLockStatus:
        with self._lock:
            current = self._normalized_status()
            if not current.locked:
                raise CalibrationError("尚未取得校正操作鎖，請重新開始校正。")
            if current.owner != owner:
                raise CalibrationError("目前校正操作鎖屬於其他操作人員。")
            return current.model_copy(deep=True)

    def ensure_unlocked(self) -> None:
        with self._lock:
            if self._normalized_status().locked:
                raise CalibrationError("相機校正進行中，暫時無法執行此操作。")

    def release(
        self,
        owner: str,
        *,
        force: bool = False,
    ) -> CalibrationLockStatus:
        with self._lock:
            current = self._normalized_status()
            if current.locked and not force and current.owner != owner:
                raise CalibrationError("目前校正操作鎖屬於其他操作人員。")
            return self._clear("forced" if force else "released").model_copy(
                deep=True
            )

    def close(self) -> None:
        with self._lock:
            self._clear("shutdown")
