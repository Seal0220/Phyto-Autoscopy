from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from app.core.state import AppContext, get_context
from app.models.calibration_models import (
    CalibrationCreateRequest,
    CalibrationProfile,
    CalibrationReport,
)


router = APIRouter(prefix="/api/calibrations", tags=["calibrations"])


@router.get("", response_model=list[CalibrationProfile])
def list_calibrations(
    context: AppContext = Depends(get_context),
) -> list[CalibrationProfile]:
    return context.calibration_service.list_profiles()


@router.post("", response_model=CalibrationProfile)
def create_calibration(
    request: CalibrationCreateRequest,
    context: AppContext = Depends(get_context),
) -> CalibrationProfile:
    return context.calibration_service.create(request)


@router.get("/source-images")
def list_calibration_source_images(
    limit: int = Query(default=500, ge=1, le=1000),
    context: AppContext = Depends(get_context),
) -> list[dict]:
    return context.calibration_service.list_source_images(limit=limit)


@router.get("/{calibration_id}", response_model=CalibrationProfile)
def get_calibration(
    calibration_id: str,
    context: AppContext = Depends(get_context),
) -> CalibrationProfile:
    return context.calibration_service.get_profile(calibration_id)


@router.delete("/{calibration_id}")
def delete_calibration(
    calibration_id: str,
    context: AppContext = Depends(get_context),
) -> dict[str, str]:
    context.calibration_service.delete(calibration_id)
    return {"deleted": calibration_id}


@router.post(
    "/{calibration_id}/detect-corners",
    response_model=CalibrationProfile,
)
def detect_calibration_corners(
    calibration_id: str,
    context: AppContext = Depends(get_context),
) -> CalibrationProfile:
    return context.calibration_service.detect_corners(calibration_id)


@router.post(
    "/{calibration_id}/solve-intrinsics",
    response_model=CalibrationProfile,
)
def solve_calibration_intrinsics(
    calibration_id: str,
    context: AppContext = Depends(get_context),
) -> CalibrationProfile:
    return context.calibration_service.solve_intrinsics(calibration_id)


@router.post(
    "/{calibration_id}/solve-stereo",
    response_model=CalibrationProfile,
)
def solve_stereo_calibration(
    calibration_id: str,
    context: AppContext = Depends(get_context),
) -> CalibrationProfile:
    return context.calibration_service.solve_stereo(calibration_id)


@router.post(
    "/{calibration_id}/solve-rotating",
    response_model=CalibrationProfile,
)
def solve_rotating_calibration(
    calibration_id: str,
    context: AppContext = Depends(get_context),
) -> CalibrationProfile:
    return context.calibration_service.solve_rotating(calibration_id)


@router.post(
    "/{calibration_id}/validate",
    response_model=CalibrationProfile,
)
def validate_calibration(
    calibration_id: str,
    context: AppContext = Depends(get_context),
) -> CalibrationProfile:
    return context.calibration_service.validate(calibration_id)


@router.get(
    "/{calibration_id}/report",
    response_model=CalibrationReport,
)
def get_calibration_report(
    calibration_id: str,
    context: AppContext = Depends(get_context),
) -> CalibrationReport:
    return context.calibration_service.report(calibration_id)


@router.get("/{calibration_id}/previews/{preview_name}")
def get_calibration_preview(
    calibration_id: str,
    preview_name: str,
    context: AppContext = Depends(get_context),
) -> FileResponse:
    path = context.calibration_service.get_preview_path(
        calibration_id,
        preview_name,
    )
    return FileResponse(path)
