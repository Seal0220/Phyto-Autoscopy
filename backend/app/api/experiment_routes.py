from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.state import AppContext, get_context
from app.models.experiment_models import ExperimentStartRequest, ExperimentStatus

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


@router.get("/status", response_model=ExperimentStatus)
def experiment_status(context: AppContext = Depends(get_context)) -> ExperimentStatus:
    return context.experiment_service.get_status()


@router.post("/start", response_model=ExperimentStatus)
def start_experiment(
    request: ExperimentStartRequest | None = None,
    context: AppContext = Depends(get_context),
) -> ExperimentStatus:
    return context.experiment_service.start(request)


@router.post("/pause", response_model=ExperimentStatus)
def pause_experiment(context: AppContext = Depends(get_context)) -> ExperimentStatus:
    return context.experiment_service.pause()


@router.post("/resume", response_model=ExperimentStatus)
def resume_experiment(context: AppContext = Depends(get_context)) -> ExperimentStatus:
    return context.experiment_service.resume()


@router.post("/stop", response_model=ExperimentStatus)
def stop_experiment(context: AppContext = Depends(get_context)) -> ExperimentStatus:
    return context.experiment_service.stop()
