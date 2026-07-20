from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from app.calibration.board_generation import render_calibration_board
from app.core.exceptions import CalibrationError
from app.core.state import AppContext, get_context
from app.models.analysis_models import AnalysisCalibrationProfile
from app.models.calibration_models import (
    CalibrationArmHeightRequest,
    CalibrationBoardCreateRequest,
    CalibrationBoardProfile,
    CalibrationObservation,
    CalibrationDetection,
    CalibrationLockRequest,
    CalibrationLockStatus,
    CameraIntrinsics,
    ExtrinsicCaptureRequest,
    ExtrinsicProfile,
    ExtrinsicProfileCopyRequest,
    ExtrinsicProfileCreateRequest,
    ExtrinsicProfilePatchRequest,
    IntrinsicRun,
    IntrinsicRunActionRequest,
    IntrinsicRunCreateRequest,
    QuickRelocationRequest,
    UnifiedCalibrationStatus,
)
from app.models.motor_models import MotorStatus, MoveRequest
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


@router.get("/extrinsics", response_model=list[ExtrinsicProfile])
def list_extrinsic_profiles(
    context: AppContext = Depends(get_context),
) -> list[ExtrinsicProfile]:
    return context.extrinsic_calibration_service.list_profiles()


@router.get("/extrinsics/active", response_model=ExtrinsicProfile | None)
def get_active_extrinsic_profile(
    context: AppContext = Depends(get_context),
) -> ExtrinsicProfile | None:
    return context.extrinsic_calibration_service.get_active()


@router.get(
    "/active-analysis-profile",
    response_model=AnalysisCalibrationProfile | None,
)
def get_active_analysis_calibration(
    context: AppContext = Depends(get_context),
) -> AnalysisCalibrationProfile | None:
    profiles = _service(context).list_profiles()
    return profiles[0] if profiles else None


@router.post("/extrinsics", response_model=ExtrinsicProfile)
def create_extrinsic_profile(
    payload: ExtrinsicProfileCreateRequest,
    request: Request,
    context: AppContext = Depends(get_context),
) -> ExtrinsicProfile:
    return context.extrinsic_calibration_service.create(
        payload,
        _owner(request),
    )


@router.post("/extrinsics/relocate", response_model=ExtrinsicProfile)
def quick_relocate_extrinsic_profile(
    payload: QuickRelocationRequest,
    request: Request,
    context: AppContext = Depends(get_context),
) -> ExtrinsicProfile:
    return context.extrinsic_calibration_service.quick_relocation(
        payload,
        _owner(request),
    )


@router.get("/extrinsics/{profile_id}", response_model=ExtrinsicProfile)
def get_extrinsic_profile(
    profile_id: str,
    context: AppContext = Depends(get_context),
) -> ExtrinsicProfile:
    return context.extrinsic_calibration_service.get_profile(profile_id)


@router.get(
    "/extrinsics/{profile_id}/observations",
    response_model=list[CalibrationObservation],
)
def list_extrinsic_observations(
    profile_id: str,
    context: AppContext = Depends(get_context),
) -> list[CalibrationObservation]:
    return context.extrinsic_calibration_service.list_observations(profile_id)


@router.patch("/extrinsics/{profile_id}", response_model=ExtrinsicProfile)
def update_extrinsic_profile(
    profile_id: str,
    payload: ExtrinsicProfilePatchRequest,
    request: Request,
    context: AppContext = Depends(get_context),
) -> ExtrinsicProfile:
    return context.extrinsic_calibration_service.update(
        profile_id,
        payload,
        _owner(request),
    )


@router.delete("/extrinsics/{profile_id}")
def delete_extrinsic_profile(
    profile_id: str,
    request: Request,
    context: AppContext = Depends(get_context),
) -> dict[str, str]:
    context.extrinsic_calibration_service.delete(profile_id, _owner(request))
    return {"deleted": profile_id}


@router.post("/extrinsics/{profile_id}/copy", response_model=ExtrinsicProfile)
def copy_extrinsic_profile(
    profile_id: str,
    payload: ExtrinsicProfileCopyRequest,
    request: Request,
    context: AppContext = Depends(get_context),
) -> ExtrinsicProfile:
    return context.extrinsic_calibration_service.copy(
        profile_id,
        payload,
        _owner(request),
    )


@router.post("/extrinsics/{profile_id}/capture")
def capture_extrinsic_observation(
    profile_id: str,
    payload: ExtrinsicCaptureRequest,
    request: Request,
    context: AppContext = Depends(get_context),
):
    return context.extrinsic_calibration_service.capture(
        profile_id,
        payload,
        _owner(request),
    )


@router.post("/extrinsics/{profile_id}/solve", response_model=ExtrinsicProfile)
def solve_extrinsic_profile(
    profile_id: str,
    request: Request,
    context: AppContext = Depends(get_context),
) -> ExtrinsicProfile:
    return context.extrinsic_calibration_service.solve(
        profile_id,
        _owner(request),
    )


@router.post("/extrinsics/{profile_id}/validate", response_model=ExtrinsicProfile)
def validate_extrinsic_profile(
    profile_id: str,
    request: Request,
    context: AppContext = Depends(get_context),
) -> ExtrinsicProfile:
    return context.extrinsic_calibration_service.validate(
        profile_id,
        _owner(request),
    )


@router.post("/extrinsics/{profile_id}/activate", response_model=ExtrinsicProfile)
def activate_extrinsic_profile(
    profile_id: str,
    request: Request,
    context: AppContext = Depends(get_context),
) -> ExtrinsicProfile:
    candidate = context.extrinsic_calibration_service.get_profile(profile_id)
    _service(context).analysis_profile(candidate)
    profile = context.extrinsic_calibration_service.activate(
        profile_id,
        _owner(request),
    )
    return profile


@router.post("/extrinsics/{profile_id}/archive", response_model=ExtrinsicProfile)
def archive_extrinsic_profile(
    profile_id: str,
    request: Request,
    context: AppContext = Depends(get_context),
) -> ExtrinsicProfile:
    return context.extrinsic_calibration_service.archive(
        profile_id,
        _owner(request),
    )


@router.get("/extrinsics/{profile_id}/export")
def export_extrinsic_profile(
    profile_id: str,
    context: AppContext = Depends(get_context),
) -> FileResponse:
    path = context.extrinsic_calibration_service.export(profile_id)
    return FileResponse(
        _safe_calibration_file(context, path.as_posix()),
        filename=path.name,
        media_type="application/zip",
    )


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
    context: AppContext = Depends(get_context),
) -> StreamingResponse:
    status = context.camera_manager.get_status(camera_id)
    if not status.enabled:
        raise CalibrationError(f"相機 {camera_id} 尚未啟用。")
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


@router.post("/motor/move", response_model=MotorStatus)
def move_calibration_motor(
    payload: MoveRequest,
    request: Request,
    context: AppContext = Depends(get_context),
) -> MotorStatus:
    return _service(context).move_motor(payload.angle_deg, _owner(request))


@router.post("/motor/engage", response_model=MotorStatus)
def engage_calibration_motor(
    request: Request,
    context: AppContext = Depends(get_context),
) -> MotorStatus:
    return _service(context).engage_motor(_owner(request))


@router.post("/motor/disengage", response_model=MotorStatus)
def disengage_calibration_motor(
    request: Request,
    context: AppContext = Depends(get_context),
) -> MotorStatus:
    return _service(context).disengage_motor(_owner(request))


@router.post("/motor/return-origin", response_model=MotorStatus)
def return_calibration_motor_origin(
    request: Request,
    context: AppContext = Depends(get_context),
) -> MotorStatus:
    return _service(context).return_motor_origin(_owner(request))


@router.post("/motor/set-origin", response_model=MotorStatus)
def set_calibration_motor_origin(
    request: Request,
    context: AppContext = Depends(get_context),
) -> MotorStatus:
    return _service(context).set_motor_origin(_owner(request))


@router.post("/motor/stop", response_model=MotorStatus)
def stop_calibration_motor(
    request: Request,
    context: AppContext = Depends(get_context),
) -> MotorStatus:
    return _service(context).stop_motor(_owner(request))


@router.post("/motor/emergency-stop", response_model=MotorStatus)
def emergency_stop_calibration_motor(
    context: AppContext = Depends(get_context),
) -> MotorStatus:
    return _service(context).emergency_stop()


@router.patch("/extrinsics/{profile_id}/arm-height", response_model=ExtrinsicProfile)
def update_calibration_arm_height(
    profile_id: str,
    payload: CalibrationArmHeightRequest,
    request: Request,
    context: AppContext = Depends(get_context),
) -> ExtrinsicProfile:
    profile = context.extrinsic_calibration_service.get_profile(profile_id)
    motion = profile.motion_model.model_copy(
        update={"arm_height_mm": payload.arm_height_mm},
        deep=True,
    )
    return context.extrinsic_calibration_service.update(
        profile_id,
        ExtrinsicProfilePatchRequest(motion_model=motion),
        _owner(request),
    )
