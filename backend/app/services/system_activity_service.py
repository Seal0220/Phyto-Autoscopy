from __future__ import annotations


ACTIVE_SCHEDULE_STATUSES = frozenset({
    "running",
    "paused",
    "stopping",
})

ACTIVE_ANALYSIS_STATUSES = frozenset({
    "validating",
    "processing",
    "reviewing",
    "reconstructing",
})


def system_is_active(
    *,
    schedule_status: str | None,
    motor_moving: bool,
    analysis_status: str | None,
    calibration_locked: bool = False,
) -> bool:
    return bool(
        schedule_status in ACTIVE_SCHEDULE_STATUSES
        or motor_moving
        or analysis_status in ACTIVE_ANALYSIS_STATUSES
        or calibration_locked
    )
