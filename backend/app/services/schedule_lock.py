from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from app.core.exceptions import PhytoAutoscopyError

if TYPE_CHECKING:
    from app.core.state import AppContext


ACTIVE_SCHEDULE_STATUSES = frozenset({"running", "paused", "stopping"})


@contextmanager
def schedule_calibration_guard(
    context: AppContext,
) -> Iterator[None]:
    """Serialize the schedule-start and calibration-lock decisions."""

    with context._operation_lock:
        yield


def schedule_is_active(context: AppContext) -> bool:
    return context.schedule_service.get_status().status in ACTIVE_SCHEDULE_STATUSES


def ensure_manual_changes_allowed(context: AppContext) -> None:
    if schedule_is_active(context):
        raise PhytoAutoscopyError("排程進行中，無法修改控制或設定。")
    ensure_calibration_unlocked(context)


def ensure_calibration_unlocked(context: AppContext) -> None:
    lock_service = getattr(context, "calibration_lock_service", None)
    if lock_service is not None:
        lock_service.ensure_unlocked()


def ensure_schedule_start_allowed(context: AppContext) -> None:
    ensure_calibration_unlocked(context)
