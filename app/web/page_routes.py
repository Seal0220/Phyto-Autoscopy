from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
router = APIRouter(tags=["web"])


def render(request: Request, template_name: str):
    context = request.app.state.context
    return templates.TemplateResponse(
        request,
        template_name,
        {
            "request": request,
            "settings": context.settings,
            "experiment": context.experiment_service.get_status(),
        },
    )


@router.get("/")
def dashboard(request: Request):
    return render(request, "dashboard.html")


@router.get("/cameras")
def cameras():
    return RedirectResponse(url="/#cameras", status_code=303)


@router.get("/motor")
def motor():
    return RedirectResponse(url="/#motor", status_code=303)


@router.get("/experiments")
def experiments():
    return RedirectResponse(url="/#schedule", status_code=303)


@router.get("/sessions")
def sessions():
    return RedirectResponse(url="/#sessions", status_code=303)


@router.get("/settings")
def settings():
    return RedirectResponse(url="/#settings", status_code=303)
