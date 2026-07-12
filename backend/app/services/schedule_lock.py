from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.exceptions import PhytoAutoscopyError

if TYPE_CHECKING:
    from app.core.state import AppContext


ACTIVE_SCHEDULE_STATUSES = frozenset({"running", "paused", "stopping"})


def schedule_is_active(context: AppContext) -> bool:
    return context.experiment_service.get_status().status in ACTIVE_SCHEDULE_STATUSES


def ensure_manual_changes_allowed(context: AppContext) -> None:
    if schedule_is_active(context):
        raise PhytoAutoscopyError("排程進行中，無法修改控制或設定。")
