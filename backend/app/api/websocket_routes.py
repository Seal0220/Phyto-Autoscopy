from __future__ import annotations

import asyncio
import math
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.exceptions import PhytoAutoscopyError
from app.core.state import AppContext
from app.models.experiment_models import ExperimentStartRequest
from app.security.audit import write_audit_event
from app.security.auth import (
    SecurityError,
    ensure_permission,
    permission_for_websocket_action,
    rate_limit_websocket,
    websocket_tickets,
)
from app.services.schedule_lock import ensure_manual_changes_allowed

router = APIRouter(tags=["websocket"])

SCHEDULE_ALLOWED_MANUAL_ACTIONS = frozenset({
    "motor.emergency_stop",
    "camera.reconnect",
    "camera.reconnect_all",
})


def build_snapshot(context: AppContext) -> dict[str, Any]:
    settings = context.settings
    experiment = context.experiment_service.get_status()
    disk = context.health_service.disk_status()
    return {
        "system": {
            "project_name": settings.project.name,
            "project_name_zh": settings.project.name_zh,
            "device_name": settings.project.device_name,
            "device_version": settings.project.device_version,
            "mock_mode": settings.hardware.mock_mode,
            "started_at": context.started_at.isoformat(),
            "experiment_status": experiment.status,
            "active_session_id": context.session_service.active_session_id,
            "disk": disk.model_dump(mode="json"),
            "recent_errors": context.recent_errors,
        },
        "cameras": [
            item.model_dump(mode="json") for item in context.camera_manager.get_statuses()
        ],
        "motor": context.motor_controller.status().model_dump(mode="json"),
        "experiment": experiment.model_dump(mode="json"),
    }


def run_command(context: AppContext, action: str, payload: dict[str, Any]) -> Any:
    if action == "system.snapshot":
        return build_snapshot(context)

    if (
        action.startswith(("motor.", "camera.", "capture."))
        and action not in SCHEDULE_ALLOWED_MANUAL_ACTIONS
    ):
        ensure_manual_changes_allowed(context)

    if action == "motor.engage":
        return context.motor_controller.engage().model_dump(mode="json")
    if action == "motor.disengage":
        return context.motor_controller.disengage().model_dump(mode="json")
    if action == "motor.set_origin":
        return context.motor_controller.set_origin().model_dump(mode="json")
    if action == "motor.return_origin":
        return context.motor_controller.return_origin().model_dump(mode="json")
    if action == "motor.stop":
        return context.motor_controller.stop().model_dump(mode="json")
    if action == "motor.emergency_stop":
        return context.motor_controller.emergency_stop().model_dump(mode="json")
    if action == "motor.move":
        angle_deg = float(payload["angle_deg"])
        if not math.isfinite(angle_deg):
            raise PhytoAutoscopyError("目標角度必須是有效數字。")
        return context.motor_controller.move_to_angle(angle_deg).model_dump(mode="json")

    if action == "camera.capture":
        return context.capture_service.capture_camera(payload["camera_id"]).model_dump(mode="json")
    if action == "camera.capture_all":
        return [
            item.model_dump(mode="json") for item in context.capture_service.capture_all()
        ]
    if action == "camera.reconnect":
        return context.camera_manager.reconnect(payload["camera_id"]).model_dump(mode="json")
    if action == "camera.reconnect_all":
        return [
            item.model_dump(mode="json")
            for item in context.camera_manager.reconnect_all()
        ]

    if action == "experiment.start":
        request = ExperimentStartRequest.model_validate(payload)
        return context.experiment_service.start(request).model_dump(mode="json")
    if action == "experiment.pause":
        return context.experiment_service.pause().model_dump(mode="json")
    if action == "experiment.resume":
        return context.experiment_service.resume().model_dump(mode="json")
    if action == "experiment.stop":
        return context.experiment_service.stop().model_dump(mode="json")

    if action == "capture.rotation_cycle":
        captures = context.rotation_service.capture_cycle(
            session_id=payload.get("session_id"),
            cycle_id=int(payload.get("cycle_id", 1)),
            start_deg=payload.get("start_deg"),
            end_deg=payload.get("end_deg"),
            step_deg=payload.get("step_deg"),
        )
        return [item.model_dump(mode="json") for item in captures]

    if action == "sessions.list":
        return [
            item.model_dump(mode="json") for item in context.session_service.list_sessions()
        ]

    if action == "settings.get":
        group = payload.get("group")
        settings = context.settings.model_dump(mode="json")
        if group is None:
            return settings
        if group == "default":
            return {
                "project": settings["project"],
                "hardware": settings["hardware"],
                "paths": settings["paths"],
            }
        if group not in settings:
            raise PhytoAutoscopyError(f"找不到設定群組：{group}")
        return settings[group]

    raise PhytoAutoscopyError("不支援的即時操作。")


@router.websocket("/ws/status")
async def status_websocket(websocket: WebSocket) -> None:
    # The browser never receives the BFF credential. It can only connect with
    # a one-use ticket minted through the authenticated Next.js route handler.
    try:
        principal = websocket_tickets.consume(websocket.query_params.get("ticket"))
        rate_limit_websocket(principal, "connect")
    except SecurityError:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    context: AppContext = websocket.app.state.context
    await websocket.send_json({"type": "snapshot", "payload": build_snapshot(context)})

    try:
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_json(), timeout=1.5)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "snapshot", "payload": build_snapshot(context)})
                continue

            if message.get("type") != "command":
                await websocket.send_json(
                    {"type": "error", "detail": "不支援的即時訊息類型。"}
                )
                continue

            command_id = message.get("id")
            action = str(message.get("action", ""))
            payload = message.get("payload") or {}
            try:
                if not isinstance(payload, dict):
                    raise PhytoAutoscopyError("即時操作資料格式錯誤。")
                ensure_permission(principal, permission_for_websocket_action(action))
                rate_limit_websocket(principal, "command")
                result = await asyncio.to_thread(run_command, context, action, payload)
                write_audit_event(
                    actor=principal.actor,
                    role=principal.role,
                    action=f"websocket:{action}",
                    outcome="ok",
                )
                await websocket.send_json(
                    {
                        "type": "command_result",
                        "id": command_id,
                        "ok": True,
                        "action": action,
                        "payload": result,
                    }
                )
                await websocket.send_json({"type": "snapshot", "payload": build_snapshot(context)})
            except Exception as exc:
                context.add_error(str(exc))
                write_audit_event(
                    actor=principal.actor,
                    role=principal.role,
                    action=f"websocket:{action or 'unknown'}",
                    outcome="failed",
                    detail=str(exc),
                )
                await websocket.send_json(
                    {
                        "type": "command_result",
                        "id": command_id,
                        "ok": False,
                        "action": action,
                        "detail": str(exc),
                    }
                )
                await websocket.send_json({"type": "snapshot", "payload": build_snapshot(context)})
    except WebSocketDisconnect:
        return
