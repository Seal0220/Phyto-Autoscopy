from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.state import AppContext, get_context
from app.core.exceptions import CameraError
from app.models.camera_models import (
    CameraSettingsUpdate,
    CameraStatus,
    CaptureRequest,
    CaptureResult,
    SnapshotResult,
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
    status = context.camera_manager.get_status(camera_id)
    if not status.enabled:
        raise CameraError(f"相機 {camera_id} 尚未啟用。")
    if not status.connected:
        raise CameraError(f"相機 {camera_id} 未連線。")
    first_frame = context.camera_manager.capture(camera_id)
    return StreamingResponse(
        context.image_preview_service.mjpeg_stream(camera_id, first_frame),
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
        record_id=request.record_id,
        cycle_id=request.cycle_id,
        angle_deg=request.angle_deg,
    )


@router.post("/{camera_id}/snapshot", response_model=SnapshotResult)
def snapshot_camera(
    camera_id: str,
    context: AppContext = Depends(get_context),
) -> SnapshotResult:
    ensure_manual_changes_allowed(context)
    return context.snapshot_service.snapshot_camera(camera_id)


@router.post("/snapshot-all", response_model=list[SnapshotResult])
def snapshot_all(
    context: AppContext = Depends(get_context),
) -> list[SnapshotResult]:
    ensure_manual_changes_allowed(context)
    return context.snapshot_service.snapshot_all()


@router.post("/capture-all", response_model=list[CaptureResult])
def capture_all(
    request: CaptureRequest | None = None,
    context: AppContext = Depends(get_context),
) -> list[CaptureResult]:
    ensure_manual_changes_allowed(context)
    request = request or CaptureRequest()
    return context.capture_service.capture_all(record_id=request.record_id)


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
    try:
        current = context.settings.cameras[camera_id]
    except KeyError as exc:
        raise CameraError(f"找不到相機：{camera_id}") from exc
    for key, value in update.model_dump(exclude_none=True).items():
        setattr(current, key, value)
    return {"camera_id": camera_id, "settings": current.model_dump(), "restart_required": False}
