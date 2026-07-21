from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from app.calibration.board_generation import render_calibration_board
from app.calibration.live_undistortion import LiveFrameUndistorter
from app.core.exceptions import CalibrationError
from app.core.state import AppContext, get_context
from app.models.calibration_models import (
    CalibrationBoardCreateRequest,
    CalibrationBoardProfile,
    CalibrationDetection,
    CalibrationLockRequest,
    CalibrationLockStatus,
    CameraIntrinsics,
    IntrinsicRun,
    IntrinsicRunActionRequest,
    IntrinsicRunCreateRequest,
    UnifiedCalibrationStatus,
)
from app.models.camera_models import SnapshotResult
from app.security.auth import get_request_principal
from app.services.schedule_lock import schedule_calibration_guard


router = APIRouter(prefix="/api/calibration", tags=["calibration"])

CALIBRATION_STREAM_STARTUP_TIMEOUT_SECONDS = 10.0


def _owner(request: Request) -> str:
    return get_request_principal(request).actor


def _service(context: AppContext):
    service = context.unified_calibration_service
    if service is None:
        raise CalibrationError("相機校正服務尚未就緒。")
    return service


def _safe_calibration_file(
    context: AppContext,
    raw_path: str,
) -> Path:
    root = context.settings.paths.calibration_dir.resolve()
    path = Path(raw_path).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise CalibrationError("校正檔案路徑超出允許範圍。") from error
    if not path.is_file():
        raise CalibrationError("找不到校正檔案。")
    return path


@router.get("", response_model=UnifiedCalibrationStatus)
@router.get("/status", response_model=UnifiedCalibrationStatus)
def calibration_status(
    request: Request,
    context: AppContext = Depends(get_context),
) -> UnifiedCalibrationStatus:
    return _service(context).status(_owner(request))


@router.post("/lock", response_model=CalibrationLockStatus)
def acquire_calibration_lock(
    payload: CalibrationLockRequest,
    request: Request,
    context: AppContext = Depends(get_context),
) -> CalibrationLockStatus:
    with schedule_calibration_guard(context):
        return context.calibration_lock_service.acquire(_owner(request), payload)


@router.post("/lock/refresh", response_model=CalibrationLockStatus)
def refresh_calibration_lock(
    request: Request,
    context: AppContext = Depends(get_context),
) -> CalibrationLockStatus:
    return context.calibration_lock_service.refresh(_owner(request))


@router.delete("/lock", response_model=CalibrationLockStatus)
def release_calibration_lock(
    request: Request,
    context: AppContext = Depends(get_context),
) -> CalibrationLockStatus:
    return context.calibration_lock_service.release(_owner(request))


@router.post("/storage/reconcile", response_model=UnifiedCalibrationStatus)
def reconcile_calibration_storage(
    request: Request,
    context: AppContext = Depends(get_context),
) -> UnifiedCalibrationStatus:
    return _service(context).reconcile_storage(_owner(request))


@router.get("/boards", response_model=list[CalibrationBoardProfile])
def list_calibration_boards(
    context: AppContext = Depends(get_context),
) -> list[CalibrationBoardProfile]:
    return _service(context).list_boards()


@router.post("/boards", response_model=CalibrationBoardProfile)
def create_calibration_board(
    payload: CalibrationBoardCreateRequest,
    context: AppContext = Depends(get_context),
) -> CalibrationBoardProfile:
    return _service(context).create_board(payload)


@router.get("/boards/{board_profile_id}/image")
def calibration_board_image(
    board_profile_id: str,
    download: bool = Query(default=False),
    context: AppContext = Depends(get_context),
) -> Response:
    board = _service(context).get_board(board_profile_id)
    headers = {
        "Cache-Control": "no-store",
    }
    if download:
        headers["Content-Disposition"] = (
            f'attachment; filename="{board.board_profile_id}.png"'
        )
    return Response(
        content=render_calibration_board(board),
        media_type="image/png",
        headers=headers,
    )


@router.get("/intrinsics", response_model=list[CameraIntrinsics])
def list_camera_intrinsics(
    context: AppContext = Depends(get_context),
) -> list[CameraIntrinsics]:
    return context.calibration_validation_service.intrinsics_status()


@router.get("/intrinsics/{camera_id}", response_model=CameraIntrinsics)
def get_camera_intrinsics(
    camera_id: str,
    context: AppContext = Depends(get_context),
) -> CameraIntrinsics:
    return context.intrinsic_calibration_service.get_intrinsics(camera_id)


@router.post("/intrinsics/{camera_id}/runs", response_model=IntrinsicRun)
def create_intrinsic_run(
    camera_id: str,
    payload: IntrinsicRunCreateRequest,
    request: Request,
    context: AppContext = Depends(get_context),
) -> IntrinsicRun:
    return context.intrinsic_calibration_service.create_run(
        camera_id,
        payload,
        _owner(request),
    )


@router.get("/intrinsics/{camera_id}/runs", response_model=list[IntrinsicRun])
def list_intrinsic_runs(
    camera_id: str,
    context: AppContext = Depends(get_context),
) -> list[IntrinsicRun]:
    return context.intrinsic_calibration_service.list_runs(camera_id)


@router.get("/intrinsics/{camera_id}/runs/{run_id}", response_model=IntrinsicRun)
def get_intrinsic_run(
    camera_id: str,
    run_id: str,
    context: AppContext = Depends(get_context),
) -> IntrinsicRun:
    run = context.intrinsic_calibration_service.get_run(run_id)
    if run.camera_id != camera_id:
        raise CalibrationError(f"內參工作 {run_id} 不屬於相機 {camera_id}。")
    return run


@router.post("/intrinsics/{camera_id}/capture", response_model=IntrinsicRun)
def capture_intrinsic_sample(
    camera_id: str,
    payload: IntrinsicRunActionRequest,
    request: Request,
    context: AppContext = Depends(get_context),
) -> IntrinsicRun:
    return context.intrinsic_calibration_service.capture(
        camera_id,
        payload.run_id,
        _owner(request),
    )


@router.post("/intrinsics/{camera_id}/solve", response_model=IntrinsicRun)
def solve_intrinsic_run(
    camera_id: str,
    payload: IntrinsicRunActionRequest,
    request: Request,
    context: AppContext = Depends(get_context),
) -> IntrinsicRun:
    return context.intrinsic_calibration_service.solve(
        camera_id,
        payload.run_id,
        _owner(request),
    )


@router.post("/intrinsics/{camera_id}/apply", response_model=CameraIntrinsics)
def apply_intrinsic_run(
    camera_id: str,
    payload: IntrinsicRunActionRequest,
    request: Request,
    context: AppContext = Depends(get_context),
) -> CameraIntrinsics:
    return context.intrinsic_calibration_service.apply(
        camera_id,
        payload.run_id,
        _owner(request),
    )


@router.delete("/intrinsics/{camera_id}/runs/{run_id}")
def cancel_intrinsic_run(
    camera_id: str,
    run_id: str,
    request: Request,
    context: AppContext = Depends(get_context),
) -> dict[str, str]:
    context.intrinsic_calibration_service.cancel_run(
        camera_id,
        run_id,
        _owner(request),
    )
    return {"cancelled": run_id}


@router.get("/intrinsics/{camera_id}/preview")
def get_undistorted_preview(
    camera_id: str,
    context: AppContext = Depends(get_context),
) -> FileResponse:
    intrinsics = context.intrinsic_calibration_service.get_intrinsics(camera_id)
    path = intrinsics.quality.get("undistorted_preview_path")
    if not isinstance(path, str) or not path:
        raise CalibrationError(f"相機 {camera_id} 尚無去畸變預覽。")
    return FileResponse(_safe_calibration_file(context, path))


@router.post("/cameras/{camera_id}/detection", response_model=CalibrationDetection)
def detect_calibration_board(
    camera_id: str,
    request: Request,
    board_profile_id: str = Query(default="default_charuco"),
    context: AppContext = Depends(get_context),
) -> CalibrationDetection:
    return _service(context).detect(
        camera_id,
        board_profile_id,
        _owner(request),
    )


@router.get("/cameras/{camera_id}/stream")
async def calibration_camera_stream(
    camera_id: str,
    board_profile_id: str = Query(default="default_charuco"),
    undistort: bool = Query(default=False),
    context: AppContext = Depends(get_context),
) -> StreamingResponse:
    status = context.camera_manager.get_status(camera_id)
    if not status.enabled:
        raise CalibrationError(f"相機 {camera_id} 尚未啟用。")
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
    first_frame, first_sequence = await asyncio.to_thread(
        context.camera_manager.wait_for_frame,
        camera_id,
        timeout=CALIBRATION_STREAM_STARTUP_TIMEOUT_SECONDS,
    )
    return StreamingResponse(
        _service(context).calibration_mjpeg_stream(
            camera_id,
            board_profile_id,
            first_frame,
            first_sequence,
            frame_undistorter,
        ),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.post("/cameras/{camera_id}/reconnect")
def reconnect_calibration_camera(
    camera_id: str,
    request: Request,
    context: AppContext = Depends(get_context),
):
    return _service(context).reconnect_camera(camera_id, _owner(request))


@router.post("/cameras/{camera_id}/snapshot", response_model=SnapshotResult)
def snapshot_calibration_camera(
    camera_id: str,
    request: Request,
    context: AppContext = Depends(get_context),
) -> SnapshotResult:
    return _service(context).snapshot_camera(camera_id, _owner(request))

