from __future__ import annotations

from fastapi import APIRouter, Request

from app.security.audit import write_audit_event
from app.security.auth import get_request_principal, websocket_tickets

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/ws-ticket")
def issue_ws_ticket(request: Request) -> dict[str, int | str]:
    principal = get_request_principal(request)
    ticket, expires_in_seconds = websocket_tickets.issue(principal)
    write_audit_event(
        actor=principal.actor,
        role=principal.role,
        action="websocket.ticket",
        outcome="ok",
    )
    return {"ticket": ticket, "expires_in_seconds": expires_in_seconds}
