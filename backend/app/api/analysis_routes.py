from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.core.state import AppContext, get_context
from app.models.analysis_models import (
    AnalysisCreateRequest,
    AnalysisFrameDetail,
    AnalysisFramePair,
    AnalysisProgress,
    AnalysisReconstructRequest,
    AnalysisRun,
    AnalysisSourcePreview,
    AnalysisSourcePreviewRequest,
    AnalysisSourceSummary,
    DetectionSummary,
    ManualCorrection,
    ManualCorrectionRequest,
    ReprojectionErrorRecord,
    TrajectoryPoint,
)
from app.security.auth import Principal, get_request_principal


router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/sources", response_model=list[AnalysisSourceSummary])
def list_analysis_sources(
    context: AppContext = Depends(get_context),
) -> list[AnalysisSourceSummary]:
    return context.analysis_service.list_sources()


@router.post("/sources/preview", response_model=AnalysisSourcePreview)
def preview_analysis_sources(
    request: AnalysisSourcePreviewRequest,
    context: AppContext = Depends(get_context),
) -> AnalysisSourcePreview:
    return context.analysis_service.preview_sources(request)


@router.get("", response_model=list[AnalysisRun])
def list_analysis_runs(
    record_id: str | None = None,
    context: AppContext = Depends(get_context),
) -> list[AnalysisRun]:
    return context.analysis_service.list_runs(record_id=record_id)


@router.post("", response_model=AnalysisRun)
def create_analysis_run(
    request: AnalysisCreateRequest,
    context: AppContext = Depends(get_context),
    principal: Principal = Depends(get_request_principal),
) -> AnalysisRun:
    return context.analysis_service.create(request, actor_id=principal.actor)


@router.get("/progress", response_model=AnalysisProgress)
def get_active_analysis_progress(
    context: AppContext = Depends(get_context),
) -> AnalysisProgress:
    return context.analysis_service.get_progress()


@router.get("/{analysis_id}", response_model=AnalysisRun)
def get_analysis_run(
    analysis_id: str,
    context: AppContext = Depends(get_context),
) -> AnalysisRun:
    return context.analysis_service.get_run(analysis_id)


@router.delete("/{analysis_id}")
def delete_analysis_run(
    analysis_id: str,
    context: AppContext = Depends(get_context),
) -> dict[str, str]:
    context.analysis_service.delete(analysis_id)
    return {"deleted": analysis_id}


@router.post("/{analysis_id}/validate", response_model=AnalysisRun)
def validate_analysis_run(
    analysis_id: str,
    context: AppContext = Depends(get_context),
) -> AnalysisRun:
    return context.analysis_service.validate(analysis_id)


@router.post("/{analysis_id}/start", response_model=AnalysisRun)
def start_analysis_run(
    analysis_id: str,
    context: AppContext = Depends(get_context),
) -> AnalysisRun:
    return context.analysis_service.start(analysis_id)


@router.post("/{analysis_id}/cancel", response_model=AnalysisRun)
def cancel_analysis_run(
    analysis_id: str,
    context: AppContext = Depends(get_context),
) -> AnalysisRun:
    return context.analysis_service.cancel(analysis_id)


@router.post("/{analysis_id}/retry", response_model=AnalysisRun)
def retry_analysis_run(
    analysis_id: str,
    context: AppContext = Depends(get_context),
) -> AnalysisRun:
    return context.analysis_service.retry(analysis_id)


@router.post("/{analysis_id}/resume", response_model=AnalysisRun)
def resume_analysis_run(
    analysis_id: str,
    context: AppContext = Depends(get_context),
) -> AnalysisRun:
    return context.analysis_service.resume(analysis_id)


@router.post("/{analysis_id}/reset", response_model=AnalysisRun)
def reset_analysis_run(
    analysis_id: str,
    context: AppContext = Depends(get_context),
) -> AnalysisRun:
    return context.analysis_service.reset(analysis_id)


@router.post("/{analysis_id}/reconstruct", response_model=AnalysisRun)
def reconstruct_analysis_run(
    analysis_id: str,
    request: AnalysisReconstructRequest | None = None,
    context: AppContext = Depends(get_context),
) -> AnalysisRun:
    return context.analysis_service.reconstruct(
        analysis_id,
        manual_review_completed=(
            request.manual_review_completed
            if request is not None
            else True
        ),
    )


@router.get("/{analysis_id}/progress", response_model=AnalysisProgress)
def get_analysis_progress(
    analysis_id: str,
    context: AppContext = Depends(get_context),
) -> AnalysisProgress:
    return context.analysis_service.get_progress(analysis_id)


@router.get(
    "/{analysis_id}/frames",
    response_model=list[AnalysisFrameDetail],
)
def list_analysis_frames(
    analysis_id: str,
    context: AppContext = Depends(get_context),
) -> list[AnalysisFrameDetail]:
    return context.analysis_service.list_frames(analysis_id)


@router.get(
    "/{analysis_id}/frames/{frame_id}",
    response_model=AnalysisFrameDetail,
)
def get_analysis_frame(
    analysis_id: str,
    frame_id: int,
    context: AppContext = Depends(get_context),
) -> AnalysisFrameDetail:
    return context.analysis_service.get_frame_detail(analysis_id, frame_id)


@router.get("/{analysis_id}/frames/{frame_id}/images/{camera_id}")
def get_analysis_frame_image(
    analysis_id: str,
    frame_id: int,
    camera_id: str,
    context: AppContext = Depends(get_context),
) -> FileResponse:
    path = context.analysis_service.get_frame_image_path(
        analysis_id,
        frame_id,
        camera_id,
    )
    return FileResponse(path)


@router.get(
    "/{analysis_id}/frame-pairs",
    response_model=list[AnalysisFramePair],
)
def list_analysis_frame_pairs(
    analysis_id: str,
    context: AppContext = Depends(get_context),
) -> list[AnalysisFramePair]:
    return context.analysis_service.list_frame_pairs(analysis_id)


@router.get(
    "/{analysis_id}/corrections",
    response_model=list[ManualCorrection],
)
def list_analysis_corrections(
    analysis_id: str,
    context: AppContext = Depends(get_context),
) -> list[ManualCorrection]:
    return context.analysis_service.list_corrections(analysis_id)


@router.post(
    "/{analysis_id}/corrections",
    response_model=ManualCorrection,
)
def save_analysis_correction(
    analysis_id: str,
    request: ManualCorrectionRequest,
    context: AppContext = Depends(get_context),
    principal: Principal = Depends(get_request_principal),
) -> ManualCorrection:
    return context.analysis_service.save_correction(
        analysis_id,
        request,
        actor_id=principal.actor,
    )


@router.delete("/{analysis_id}/corrections/{correction_id}")
def delete_analysis_correction(
    analysis_id: str,
    correction_id: str,
    context: AppContext = Depends(get_context),
) -> dict[str, str]:
    context.analysis_service.delete_correction(
        analysis_id,
        correction_id,
    )
    return {"deleted": correction_id}


@router.get(
    "/{analysis_id}/trajectory",
    response_model=list[TrajectoryPoint],
)
def get_analysis_trajectory(
    analysis_id: str,
    context: AppContext = Depends(get_context),
) -> list[TrajectoryPoint]:
    return context.analysis_service.get_trajectory(analysis_id)


@router.get(
    "/{analysis_id}/reprojection-errors",
    response_model=list[ReprojectionErrorRecord],
)
def get_analysis_reprojection_errors(
    analysis_id: str,
    context: AppContext = Depends(get_context),
) -> list[ReprojectionErrorRecord]:
    return context.analysis_service.get_reprojection_errors(analysis_id)


@router.get(
    "/{analysis_id}/detection-summary",
    response_model=DetectionSummary,
)
def get_analysis_detection_summary(
    analysis_id: str,
    context: AppContext = Depends(get_context),
) -> DetectionSummary:
    return context.analysis_service.get_detection_summary(analysis_id)


@router.get("/{analysis_id}/export")
def export_analysis_run(
    analysis_id: str,
    context: AppContext = Depends(get_context),
) -> FileResponse:
    path = context.analysis_service.export(analysis_id)
    return FileResponse(
        path,
        media_type="application/zip",
        filename=path.name,
    )
