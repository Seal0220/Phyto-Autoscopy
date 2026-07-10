from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import (
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
from app.web import page_routes


def create_app() -> FastAPI:
    app = FastAPI(
        title="Phyto-Autoscopy CHLOROCULUS",
        version="0.1.0",
        lifespan=lifespan,
    )

    static_dir = Path(__file__).parent / "web" / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    app.include_router(page_routes.router)
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
