from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.calibration.live_undistortion import LiveFrameUndistorter
from app.core.state import AppContext, get_context
from app.core.exceptions import CalibrationError, CameraError
from app.models.camera_models import (
    CameraSettingsUpdate,
    CameraStatus,
    CaptureRequest,
    CaptureResult,
    SnapshotResult,
)
from app.services.schedule_lock import (
    ensure_calibration_unlocked,
    ensure_manual_changes_allowed,
)

router = APIRouter(prefix="/api/cameras", tags=["cameras"])

CAMERA_STREAM_STARTUP_TIMEOUT_SECONDS = 10.0


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
async def camera_stream(
    camera_id: str,
    undistort: bool = Query(default=False),
    context: AppContext = Depends(get_context),
) -> StreamingResponse:
    status = context.camera_manager.get_status(camera_id)
    if not status.enabled:
        raise CameraError(f"相機 {camera_id} 尚未啟用。")
    frame_undistorter = None
    if undistort:
        intrinsics = context.intrinsic_calibration_service.get_intrinsics(
            camera_id
        )
        if intrinsics.status != "valid":
            raise CalibrationError(
                f"相機 {camera_id} 沒有可用的有效內參，無法即時去畸變。"
            )
        frame_undistorter = LiveFrameUndistorter(intrinsics)
    # A reconnect or settings update briefly reports `connected=False` while
    # the persistent reader obtains its first frame.  Wait for that bounded
    # first frame instead of rejecting a valid stream during this transition.
    first_frame, first_sequence = await asyncio.to_thread(
        context.camera_manager.wait_for_frame,
        camera_id,
        timeout=CAMERA_STREAM_STARTUP_TIMEOUT_SECONDS,
    )
    return StreamingResponse(
        context.image_preview_service.mjpeg_stream(
            camera_id,
            first_frame,
            first_sequence,
            frame_undistorter,
        ),
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
    ensure_calibration_unlocked(context)
    return context.camera_manager.reconnect_all()


@router.post("/{camera_id}/reconnect", response_model=CameraStatus)
def reconnect_camera(camera_id: str, context: AppContext = Depends(get_context)) -> CameraStatus:
    ensure_calibration_unlocked(context)
    return context.camera_manager.reconnect(camera_id)


@router.post("/{camera_id}/settings")
def update_camera_settings(
    camera_id: str,
    update: CameraSettingsUpdate,
    context: AppContext = Depends(get_context),
) -> dict:
    ensure_manual_changes_allowed(context)
    with context._settings_lock:
        try:
            current = context.settings.cameras[camera_id]
        except KeyError as exc:
            raise CameraError(f"找不到相機：{camera_id}") from exc

        previous_cameras = dict(context.settings.cameras)
        candidate = type(current).model_validate(
            {
                **current.model_dump(mode="python"),
                **update.model_dump(exclude_unset=True),
            }
        )
        if candidate.enabled and candidate.device_index is None:
            raise CameraError("啟用相機前必須先選擇裝置。")

        transferred_camera_ids: list[str] = []
        if candidate.device_index is not None:
            for other_id, other in previous_cameras.items():
                if (
                    other_id == camera_id
                    or other.device_index != candidate.device_index
                ):
                    continue

                context.settings.cameras[other_id] = other.model_copy(
                    update={
                        "device_index": None,
                        "enabled": False,
                    }
                )
                transferred_camera_ids.append(other_id)
        context.settings.cameras[camera_id] = candidate
        try:
            context.camera_manager.reconfigure()
        except Exception:
            context.settings.cameras.clear()
            context.settings.cameras.update(previous_cameras)
            raise
        return {
            "camera_id": camera_id,
            "settings": candidate.model_dump(),
            "transferred_from": transferred_camera_ids,
            "restart_required": False,
        }
