from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.state import AppContext, get_context
from app.models.camera_models import (
    CameraSettingsUpdate,
    CameraStatus,
    CaptureRequest,
    CaptureResult,
)
from app.services.schedule_lock import ensure_manual_changes_allowed

router = APIRouter(prefix="/api/cameras", tags=["cameras"])


@router.get("", response_model=list[CameraStatus])
def list_cameras(context: AppContext = Depends(get_context)) -> list[CameraStatus]:
    return context.camera_manager.get_statuses()


@router.get("/scan")
def scan_cameras(context: AppContext = Depends(get_context)) -> list[dict]:
    return context.camera_manager.scan()


@router.get("/{camera_id}/status", response_model=CameraStatus)
def camera_status(camera_id: str, context: AppContext = Depends(get_context)) -> CameraStatus:
    return context.camera_manager.get_status(camera_id)


@router.get("/{camera_id}/stream")
def camera_stream(camera_id: str, context: AppContext = Depends(get_context)) -> StreamingResponse:
    return StreamingResponse(
        context.preview_service.mjpeg_stream(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.post("/{camera_id}/capture", response_model=CaptureResult)
def capture_camera(
    camera_id: str,
    request: CaptureRequest | None = None,
    context: AppContext = Depends(get_context),
) -> CaptureResult:
    ensure_manual_changes_allowed(context)
    request = request or CaptureRequest()
    return context.capture_service.capture_camera(
        camera_id,
        session_id=request.session_id,
        cycle_id=request.cycle_id,
        angle_deg=request.angle_deg,
    )


@router.post("/capture-all", response_model=list[CaptureResult])
def capture_all(
    request: CaptureRequest | None = None,
    context: AppContext = Depends(get_context),
) -> list[CaptureResult]:
    ensure_manual_changes_allowed(context)
    request = request or CaptureRequest()
    return context.capture_service.capture_all(session_id=request.session_id)


@router.post("/reconnect-all", response_model=list[CameraStatus])
def reconnect_all_cameras(
    context: AppContext = Depends(get_context),
) -> list[CameraStatus]:
    return context.camera_manager.reconnect_all()


@router.post("/{camera_id}/reconnect", response_model=CameraStatus)
def reconnect_camera(camera_id: str, context: AppContext = Depends(get_context)) -> CameraStatus:
    return context.camera_manager.reconnect(camera_id)


@router.post("/{camera_id}/settings")
def update_camera_settings(
    camera_id: str,
    update: CameraSettingsUpdate,
    context: AppContext = Depends(get_context),
) -> dict:
    ensure_manual_changes_allowed(context)
    current = context.settings.cameras[camera_id]
    for key, value in update.model_dump(exclude_none=True).items():
        setattr(current, key, value)
    return {"camera_id": camera_id, "settings": current.model_dump(), "restart_required": False}
