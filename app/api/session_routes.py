from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.core.state import AppContext, get_context
from app.models.session_models import SessionDetail, SessionSummary

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionSummary])
def list_sessions(context: AppContext = Depends(get_context)) -> list[SessionSummary]:
    return context.session_service.list_sessions()


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(session_id: str, context: AppContext = Depends(get_context)) -> SessionDetail:
    return context.session_service.get_session(session_id)


@router.delete("/{session_id}")
def delete_session(session_id: str, context: AppContext = Depends(get_context)) -> dict:
    context.session_service.delete_session(session_id)
    return {"deleted": session_id}


@router.get("/{session_id}/metadata")
def metadata_csv(session_id: str, context: AppContext = Depends(get_context)) -> FileResponse:
    return FileResponse(
        context.storage_service.metadata_path(session_id),
        media_type="text/csv",
        filename="metadata.csv",
    )


@router.get("/{session_id}/session-json")
def session_json(session_id: str, context: AppContext = Depends(get_context)) -> FileResponse:
    return FileResponse(
        context.storage_service.session_json_path(session_id),
        media_type="application/json",
        filename="session.json",
    )
