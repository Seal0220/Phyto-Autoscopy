from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.state import AppContext, get_context
from app.models.system_models import SystemStatus

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/status", response_model=SystemStatus)
def system_status(context: AppContext = Depends(get_context)) -> SystemStatus:
    settings = context.settings
    schedule = context.schedule_service.get_status()
    return SystemStatus(
        project_name=settings.project.name,
        project_name_zh=settings.project.name_zh,
        device_name=settings.project.device_name,
        device_version=settings.project.device_version,
        mock_mode=settings.hardware.mock_mode,
        started_at=context.started_at.isoformat(),
        schedule_status=schedule.status,
        active_record_id=context.record_service.active_record_id,
        disk=context.health_service.disk_status(),
        recent_errors=context.get_recent_errors(),
    )


@router.get("/health")
def health(context: AppContext = Depends(get_context)) -> dict:
    disk = context.health_service.disk_status()
    return {
        "status": "error" if disk.error else "ok",
        "disk": disk.model_dump(),
        "mock_mode": context.settings.hardware.mock_mode,
    }


@router.post("/errors/reset")
def reset_errors(context: AppContext = Depends(get_context)) -> dict:
    context.clear_errors()
    return {"detail": "錯誤紀錄已清除。", "cleared": True}
