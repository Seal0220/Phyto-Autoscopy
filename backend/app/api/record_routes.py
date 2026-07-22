from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.core.state import AppContext, get_context
from app.models.record_models import RecordDetail, RecordSummary
from app.models.capture_models import StoredCapture
from app.repositories.capture_repository import CaptureRepository
from app.services.schedule_lock import ensure_manual_changes_allowed

router = APIRouter(prefix="/api/records", tags=["records"])


@router.get("", response_model=list[RecordSummary])
def list_records(context: AppContext = Depends(get_context)) -> list[RecordSummary]:
    return context.record_service.list_records()


@router.get("/{record_id}", response_model=RecordDetail)
def get_record(record_id: str, context: AppContext = Depends(get_context)) -> RecordDetail:
    return context.record_service.get_record(record_id)


@router.get("/{record_id}/captures", response_model=list[StoredCapture])
def list_record_captures(
    record_id: str,
    context: AppContext = Depends(get_context),
) -> list[StoredCapture]:
    context.record_service.get_record(record_id)
    return CaptureRepository(context.database).list_by_record(record_id)


@router.delete("/{record_id}")
def delete_record(record_id: str, context: AppContext = Depends(get_context)) -> dict:
    ensure_manual_changes_allowed(context)
    context.record_service.delete_record(record_id)
    return {"deleted": record_id}


@router.get("/{record_id}/metadata")
def metadata_csv(record_id: str, context: AppContext = Depends(get_context)) -> FileResponse:
    return FileResponse(
        context.record_service.get_record_file(record_id, "metadata.csv"),
        media_type="text/csv",
        filename="metadata.csv",
    )


@router.get("/{record_id}/config-json")
def config_json(record_id: str, context: AppContext = Depends(get_context)) -> FileResponse:
    return FileResponse(
        context.record_service.get_record_file(record_id, "config.json"),
        media_type="application/json",
        filename="config.json",
    )
