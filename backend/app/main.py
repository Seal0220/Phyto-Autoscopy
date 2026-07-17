from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import (
    analysis_routes,
    auth_routes,
    calibration_routes,
    camera_routes,
    capture_routes,
    schedule_routes,
    motor_routes,
    record_routes,
    settings_routes,
    system_routes,
    websocket_routes,
)
from app.core.exceptions import (
    INTERNAL_ERROR_DETAIL,
    OperationCancelledError,
    PhytoAutoscopyError,
    public_error_code,
    public_error_detail,
)
from app.lifespan import lifespan
from app.security.middleware import ApiSecurityMiddleware

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    docs_enabled = os.environ.get("PHYTO_AUTOSCOPY_ENABLE_DOCS") == "1"
    app = FastAPI(
        title="Phyto-Autoscopy CHLOROCULUS",
        version="0.2.0",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.add_middleware(ApiSecurityMiddleware)

    # The FastAPI process is API-only. The browser-facing UI lives in
    # ../frontend and is the sole public entry point.
    app.include_router(auth_routes.router)
    app.include_router(analysis_routes.router)
    app.include_router(calibration_routes.router)
    app.include_router(system_routes.router)
    app.include_router(camera_routes.router)
    app.include_router(motor_routes.router)
    app.include_router(capture_routes.router)
    app.include_router(schedule_routes.router)
    app.include_router(record_routes.router)
    app.include_router(settings_routes.router)
    app.include_router(websocket_routes.router)

    @app.exception_handler(PhytoAutoscopyError)
    async def phyto_error_handler(request: Request, exc: PhytoAutoscopyError) -> JSONResponse:
        context = getattr(request.app.state, "context", None)
        if context is not None and not isinstance(exc, OperationCancelledError):
            context.add_error(public_error_detail(exc))
        return JSONResponse(
            status_code=400,
            content={
                "detail": public_error_detail(exc),
                "code": public_error_code(exc),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        logger.info("Request validation failed for %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=422,
            content={
                "detail": "請求資料格式錯誤，請檢查輸入內容。",
                "code": "validation_error",
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        detail_by_status = {
            404: "找不到要求的資源。",
            405: "不支援此請求方法。",
        }
        detail = detail_by_status.get(exc.status_code, "請求無法完成。")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": detail, "code": "http_error"},
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled API error for %s", request.url.path, exc_info=exc)
        context = getattr(request.app.state, "context", None)
        if context is not None:
            context.add_error(INTERNAL_ERROR_DETAIL)
        return JSONResponse(
            status_code=500,
            content={
                "detail": INTERNAL_ERROR_DETAIL,
                "code": "internal_error",
            },
        )

    return app
