from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.core.state import AppContext, get_context
from app.models.analysis_models import (
    AnalysisCreateRequest,
    AnalysisProgress,
    AnalysisRound,
    AnalysisReconstructRequest,
    AnalysisRun,
    AnalysisSourcePreview,
    AnalysisSourcePreviewRequest,
    AnalysisSourceScanStatus,
    AnalysisSourceSummary,
    AnalysisView,
    RoundModelResult,
    TipCorrection,
    TipCorrectionRequest,
    TipLandmark,
    TipObservation2D,
    TipTrajectoryPoint,
    StereoPoseReviewRequest,
)
from app.security.auth import Principal, get_request_principal


router = APIRouter(prefix="/api/analysis", tags=["analysis"])


def _action_response(run: AnalysisRun) -> AnalysisRun:
    """Keep control requests small even for runs with hundreds of MB of inputs."""
    parameters = {key: value for key, value in run.parameters.items() if key not in {"input_manifest", "source_manifest"}}
    parameters["input_count"] = len(run.parameters.get("input_manifest", []))
    return run.model_copy(update={"parameters": parameters, "camera_pose_results": [], "pose_quality": {}})


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


@router.post("/sources/scans", response_model=AnalysisSourceScanStatus)
def start_analysis_source_scan(
    request: AnalysisSourcePreviewRequest,
    context: AppContext = Depends(get_context),
) -> AnalysisSourceScanStatus:
    return context.analysis_service.start_source_scan(request)


@router.get("/sources/scans/{scan_id}", response_model=AnalysisSourceScanStatus)
def get_analysis_source_scan(
    scan_id: str,
    context: AppContext = Depends(get_context),
) -> AnalysisSourceScanStatus:
    return context.analysis_service.get_source_scan(scan_id)


@router.delete("/sources/scans/{scan_id}", response_model=AnalysisSourceScanStatus)
def cancel_analysis_source_scan(
    scan_id: str,
    context: AppContext = Depends(get_context),
) -> AnalysisSourceScanStatus:
    return context.analysis_service.cancel_source_scan(scan_id)


@router.get("", response_model=list[AnalysisRun])
def list_analysis_runs(
    record_id: str | None = None,
    context: AppContext = Depends(get_context),
) -> list[AnalysisRun]:
    return context.analysis_service.list_runs(record_id=record_id)


@router.get("/backends", response_model=list[dict])
def list_analysis_reconstruction_backends(
    context: AppContext = Depends(get_context),
) -> list[dict]:
    return context.analysis_service.list_reconstruction_backends()


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


@router.get("/{analysis_id}/rounds", response_model=list[AnalysisRound])
def list_analysis_rounds(
    analysis_id: str,
    context: AppContext = Depends(get_context),
) -> list[AnalysisRound]:
    return context.analysis_service.list_rounds(analysis_id)


@router.get("/{analysis_id}/views", response_model=list[AnalysisView])
def list_analysis_views(
    analysis_id: str,
    round_key: str | None = None,
    context: AppContext = Depends(get_context),
) -> list[AnalysisView]:
    return context.analysis_service.list_views(
        analysis_id,
        round_key,
    )


@router.get(
    "/{analysis_id}/round-models",
    response_model=list[RoundModelResult],
)
def list_analysis_round_models(
    analysis_id: str,
    context: AppContext = Depends(get_context),
) -> list[RoundModelResult]:
    return context.analysis_service.list_round_models(analysis_id)


@router.get(
    "/{analysis_id}/tip-landmarks",
    response_model=list[TipLandmark],
)
def list_analysis_tip_landmarks(
    analysis_id: str,
    context: AppContext = Depends(get_context),
) -> list[TipLandmark]:
    return context.analysis_service.list_tip_landmarks(analysis_id)


@router.get(
    "/{analysis_id}/tip-observations",
    response_model=list[TipObservation2D],
)
def list_analysis_tip_observations(
    analysis_id: str,
    round_key: str | None = None,
    context: AppContext = Depends(get_context),
) -> list[TipObservation2D]:
    return context.analysis_service.list_tip_observations(
        analysis_id,
        round_key,
    )


@router.get(
    "/{analysis_id}/tip-trajectory",
    response_model=list[TipTrajectoryPoint],
)
def list_analysis_tip_trajectory(
    analysis_id: str,
    mode_id: str | None = None,
    context: AppContext = Depends(get_context),
) -> list[TipTrajectoryPoint]:
    return context.analysis_service.list_tip_trajectory(
        analysis_id,
        mode_id,
    )


@router.get(
    "/{analysis_id}/tip-trajectory-quality",
    response_model=dict,
)
def get_analysis_tip_trajectory_quality(
    analysis_id: str,
    context: AppContext = Depends(get_context),
) -> dict:
    return context.analysis_service.get_tip_trajectory_quality(analysis_id)


@router.get(
    "/{analysis_id}/tip-corrections",
    response_model=list[TipCorrection],
)
def list_analysis_tip_corrections(
    analysis_id: str,
    round_key: str | None = None,
    context: AppContext = Depends(get_context),
) -> list[TipCorrection]:
    return context.analysis_service.list_tip_corrections(
        analysis_id,
        round_key,
    )


@router.post(
    "/{analysis_id}/tip-corrections",
    response_model=TipCorrection,
)
def save_analysis_tip_correction(
    analysis_id: str,
    request: TipCorrectionRequest,
    context: AppContext = Depends(get_context),
    principal: Principal = Depends(get_request_principal),
) -> TipCorrection:
    return context.analysis_service.save_tip_correction(
        analysis_id,
        request,
        actor_id=principal.actor,
    )


@router.delete(
    "/{analysis_id}/tip-corrections/{correction_id}",
)
def delete_analysis_tip_correction(
    analysis_id: str,
    correction_id: str,
    context: AppContext = Depends(get_context),
) -> dict[str, str]:
    context.analysis_service.delete_tip_correction(
        analysis_id,
        correction_id,
    )
    return {"deleted": correction_id}


@router.get(
    "/{analysis_id}/views/{view_id}/image",
)
def get_analysis_view_image(
    analysis_id: str,
    view_id: str,
    coordinate_space: str = "undistorted",
    context: AppContext = Depends(get_context),
) -> FileResponse:
    path = context.analysis_service.get_view_image_path(
        analysis_id,
        view_id,
        coordinate_space,
    )
    return FileResponse(path)


@router.get(
    "/{analysis_id}/artifacts/{artifact_path:path}",
)
def get_analysis_artifact(
    analysis_id: str,
    artifact_path: str,
    context: AppContext = Depends(get_context),
) -> FileResponse:
    return FileResponse(
        context.analysis_service.get_artifact_path(
            analysis_id,
            artifact_path,
        )
    )


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
    return _action_response(context.analysis_service.validate(analysis_id))


@router.post("/{analysis_id}/start", response_model=AnalysisRun)
def start_analysis_run(
    analysis_id: str,
    context: AppContext = Depends(get_context),
) -> AnalysisRun:
    return _action_response(context.analysis_service.start(analysis_id))


@router.post("/{analysis_id}/cancel", response_model=AnalysisRun)
def cancel_analysis_run(
    analysis_id: str,
    context: AppContext = Depends(get_context),
    principal: Principal = Depends(get_request_principal),
) -> AnalysisRun:
    return context.analysis_service.cancel(
        analysis_id,
        actor_id=principal.actor,
    )


@router.post("/{analysis_id}/retry", response_model=AnalysisRun)
def retry_analysis_run(
    analysis_id: str,
    context: AppContext = Depends(get_context),
) -> AnalysisRun:
    return _action_response(context.analysis_service.retry(analysis_id))


@router.get("/{analysis_id}/stereo-review")
def get_stereo_review(analysis_id: str, context: AppContext = Depends(get_context)) -> dict:
    return context.analysis_service.get_stereo_review(analysis_id)


@router.post("/{analysis_id}/stereo-review", response_model=AnalysisRun)
def submit_stereo_review(
    analysis_id: str, request: StereoPoseReviewRequest,
    context: AppContext = Depends(get_context),
    principal: Principal = Depends(get_request_principal),
) -> AnalysisRun:
    return _action_response(context.analysis_service.submit_stereo_review(analysis_id, request, principal.actor))


@router.post("/{analysis_id}/resume", response_model=AnalysisRun)
def resume_analysis_run(
    analysis_id: str,
    context: AppContext = Depends(get_context),
) -> AnalysisRun:
    return _action_response(context.analysis_service.resume(analysis_id))


@router.post("/{analysis_id}/pause", response_model=AnalysisRun)
def pause_analysis_run(
    analysis_id: str,
    context: AppContext = Depends(get_context),
) -> AnalysisRun:
    return _action_response(context.analysis_service.pause(analysis_id))


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
