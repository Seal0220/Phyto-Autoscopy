from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.security.audit import write_audit_event
from app.security.auth import (
    SecurityError,
    authenticate_bff_headers,
    ensure_permission,
    permission_for_http,
    rate_limit_http,
)

_MAX_REQUEST_BYTES = 1_000_000
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class ApiSecurityMiddleware(BaseHTTPMiddleware):
    """Enforce an authenticated BFF boundary before any FastAPI API handler."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        try:
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > _MAX_REQUEST_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": "請求資料過大。",
                        "code": "request_too_large",
                    },
                )

            principal = authenticate_bff_headers(request.headers)
            ensure_permission(principal, permission_for_http(request.method, request.url.path))
            rate_limit_http(principal, request.method, request.url.path)
            request.state.principal = principal
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={
                    "detail": "請求資料長度格式錯誤。",
                    "code": "invalid_content_length",
                },
            )
        except SecurityError as exc:
            write_audit_event(
                actor=request.headers.get("x-phyto-actor", "unknown")[:96],
                role=request.headers.get("x-phyto-role", "unknown")[:32],
                action=f"http:{request.method}:{request.url.path}",
                outcome="denied",
                detail=str(exc),
            )
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "detail": str(exc),
                    "code": "security_error",
                },
            )

        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-store")
        if request.method.upper() in _WRITE_METHODS:
            write_audit_event(
                actor=principal.actor,
                role=principal.role,
                action=f"http:{request.method}:{request.url.path}",
                outcome="ok" if response.status_code < 400 else "failed",
                detail=None if response.status_code < 400 else f"HTTP {response.status_code}",
            )
        return response
