from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends

from app.core.state import AppContext, get_context
from app.models.camera_models import CaptureResult
from app.services.schedule_lock import ensure_manual_changes_allowed

router = APIRouter(prefix="/api/capture", tags=["capture"])


class RotationCycleRequest(BaseModel):
    session_id: str | None = None
    cycle_id: int = Field(default=1, gt=0)
    start_deg: float | None = None
    end_deg: float | None = None
    step_deg: float | None = Field(default=None, gt=0)


@router.post("/rotation-cycle", response_model=list[CaptureResult])
def rotation_cycle(
    request: RotationCycleRequest,
    context: AppContext = Depends(get_context),
) -> list[CaptureResult]:
    ensure_manual_changes_allowed(context)
    return context.rotation_service.capture_cycle(
        session_id=request.session_id,
        cycle_id=request.cycle_id,
        start_deg=request.start_deg,
        end_deg=request.end_deg,
        step_deg=request.step_deg,
    )
