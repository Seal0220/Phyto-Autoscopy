from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import (
    auth_routes,
    camera_routes,
    capture_routes,
    experiment_routes,
    motor_routes,
    session_routes,
    settings_routes,
    system_routes,
    websocket_routes,
)
from app.core.exceptions import PhytoAutoscopyError
from app.lifespan import lifespan
from app.security.middleware import ApiSecurityMiddleware


def create_app() -> FastAPI:
    docs_enabled = os.environ.get("PHYTO_AUTOSCOPY_ENABLE_DOCS") == "1"
    app = FastAPI(
        title="Phyto-Autoscopy CHLOROCULUS",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.add_middleware(ApiSecurityMiddleware)

    # The FastAPI process is API-only. The browser-facing UI lives in
    # ../frontend and is the sole public entry point.
    app.include_router(auth_routes.router)
    app.include_router(system_routes.router)
    app.include_router(camera_routes.router)
    app.include_router(motor_routes.router)
    app.include_router(capture_routes.router)
    app.include_router(experiment_routes.router)
    app.include_router(session_routes.router)
    app.include_router(settings_routes.router)
    app.include_router(websocket_routes.router)

    @app.exception_handler(PhytoAutoscopyError)
    async def phyto_error_handler(request: Request, exc: PhytoAutoscopyError) -> JSONResponse:
        context = getattr(request.app.state, "context", None)
        if context is not None:
            context.add_error(str(exc))
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    return app
