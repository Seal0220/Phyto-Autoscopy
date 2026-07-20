from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.state import AppContext, get_context
from app.models.schedule_models import ScheduleStartRequest, ScheduleStatus
from app.services.schedule_lock import (
    ensure_schedule_start_allowed,
    schedule_calibration_guard,
)

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


@router.get("/status", response_model=ScheduleStatus)
def schedule_status(context: AppContext = Depends(get_context)) -> ScheduleStatus:
    return context.schedule_service.get_status()


@router.post("/start", response_model=ScheduleStatus)
def start_schedule(
    request: ScheduleStartRequest | None = None,
    context: AppContext = Depends(get_context),
) -> ScheduleStatus:
    with schedule_calibration_guard(context):
        ensure_schedule_start_allowed(context)
        return context.schedule_service.start(request)


@router.post("/pause", response_model=ScheduleStatus)
def pause_schedule(context: AppContext = Depends(get_context)) -> ScheduleStatus:
    return context.schedule_service.pause()


@router.post("/resume", response_model=ScheduleStatus)
def resume_schedule(context: AppContext = Depends(get_context)) -> ScheduleStatus:
    return context.schedule_service.resume()


@router.post("/stop", response_model=ScheduleStatus)
def stop_schedule(context: AppContext = Depends(get_context)) -> ScheduleStatus:
    return context.schedule_service.stop()


@router.post("/reset", response_model=ScheduleStatus)
def reset_schedule(context: AppContext = Depends(get_context)) -> ScheduleStatus:
    return context.schedule_service.reset()
