from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.exceptions import (
    INTERNAL_ERROR_DETAIL,
    OperationCancelledError,
    PhytoAutoscopyError,
    public_error_code,
    public_error_detail,
)
from app.core.state import AppContext
from app.models.schedule_models import ScheduleStartRequest
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
logger = logging.getLogger(__name__)

SCHEDULE_ALLOWED_MANUAL_ACTIONS = frozenset({
    "motor.emergency_stop",
    "camera.reconnect",
    "camera.reconnect_all",
})


def build_snapshot(context: AppContext) -> dict[str, Any]:
    settings = context.settings
    schedule = context.schedule_service.get_status()
    disk = context.health_service.disk_status()
    analysis_service = getattr(context, "analysis_service", None)
    analysis = (
        analysis_service.get_progress().model_dump(mode="json")
        if analysis_service is not None
        else {
            "analysis_id": None,
            "status": "idle",
            "stage": None,
            "current_frame": 0,
            "total_frames": 0,
            "progress": 0.0,
            "last_error": None,
        }
    )
    return {
        "system": {
            "project_name": settings.project.name,
            "project_name_zh": settings.project.name_zh,
            "device_name": settings.project.device_name,
            "device_version": settings.project.device_version,
            "mock_mode": settings.hardware.mock_mode,
            "started_at": context.started_at.isoformat(),
            "schedule_status": schedule.status,
            "active_record_id": context.record_service.active_record_id,
            "disk": disk.model_dump(mode="json"),
            "recent_errors": context.get_recent_errors(),
        },
        "cameras": [
            item.model_dump(mode="json") for item in context.camera_manager.get_statuses()
        ],
        "motor": context.motor_controller.status().model_dump(mode="json"),
        "schedule": schedule.model_dump(mode="json"),
        "analysis": analysis,
    }


def run_command(context: AppContext, action: str, payload: dict[str, Any]) -> Any:
    if action == "system.snapshot":
        return build_snapshot(context)
    if action == "system.errors.reset":
        context.clear_errors()
        return {"cleared": True}

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
        try:
            angle_deg = float(payload["angle_deg"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PhytoAutoscopyError("目標角度格式錯誤。") from exc
        if not math.isfinite(angle_deg):
            raise PhytoAutoscopyError("目標角度必須是有效數字。")
        return context.motor_controller.move_to_angle(angle_deg).model_dump(mode="json")

    if action == "camera.capture":
        camera_id = payload.get("camera_id")
        if not isinstance(camera_id, str) or not camera_id:
            raise PhytoAutoscopyError("缺少相機識別碼。")
        return context.capture_service.capture_camera(camera_id).model_dump(mode="json")
    if action == "camera.capture_all":
        return [
            item.model_dump(mode="json") for item in context.capture_service.capture_all()
        ]
    if action == "camera.snapshot":
        camera_id = payload.get("camera_id")
        if not isinstance(camera_id, str) or not camera_id:
            raise PhytoAutoscopyError("缺少相機識別碼。")
        return context.snapshot_service.snapshot_camera(camera_id).model_dump(mode="json")
    if action == "camera.snapshot_all":
        return [
            item.model_dump(mode="json")
            for item in context.snapshot_service.snapshot_all()
        ]
    if action == "camera.reconnect":
        camera_id = payload.get("camera_id")
        if not isinstance(camera_id, str) or not camera_id:
            raise PhytoAutoscopyError("缺少相機識別碼。")
        return context.camera_manager.reconnect(camera_id).model_dump(mode="json")
    if action == "camera.reconnect_all":
        return [
            item.model_dump(mode="json")
            for item in context.camera_manager.reconnect_all()
        ]

    if action == "schedule.start":
        request = ScheduleStartRequest.model_validate(payload)
        return context.schedule_service.start(request).model_dump(mode="json")
    if action == "schedule.pause":
        return context.schedule_service.pause().model_dump(mode="json")
    if action == "schedule.resume":
        return context.schedule_service.resume().model_dump(mode="json")
    if action == "schedule.stop":
        return context.schedule_service.stop().model_dump(mode="json")
    if action == "schedule.reset":
        return context.schedule_service.reset().model_dump(mode="json")

    if action == "capture.rotation_cycle":
        captures = context.rotation_service.capture_cycle(
            record_id=payload.get("record_id"),
            cycle_id=int(payload.get("cycle_id", 1)),
            start_deg=payload.get("start_deg"),
            end_deg=payload.get("end_deg"),
            step_deg=payload.get("step_deg"),
        )
        return [item.model_dump(mode="json") for item in captures]

    if action == "records.list":
        return [
            item.model_dump(mode="json") for item in context.record_service.list_records()
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


def websocket_error_detail(exc: BaseException) -> str:
    if isinstance(exc, SecurityError):
        return str(exc)
    return public_error_detail(exc)


def websocket_error_code(exc: BaseException) -> str:
    if isinstance(exc, SecurityError):
        return "security_error"
    return public_error_code(exc)


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
    send_lock = asyncio.Lock()
    command_lock = asyncio.Lock()
    pending_commands: set[asyncio.Task] = set()
    interrupt_actions = frozenset({
        "motor.stop",
        "motor.emergency_stop",
        "schedule.stop",
    })

    async def send(message: dict) -> None:
        async with send_lock:
            await websocket.send_json(message)

    async def send_snapshot() -> None:
        await send({"type": "snapshot", "payload": build_snapshot(context)})

    async def execute_command(
        command_id: Any,
        action: str,
        payload: Any,
    ) -> None:
        try:
            if not isinstance(payload, dict):
                raise PhytoAutoscopyError("即時操作資料格式錯誤。")
            ensure_permission(principal, permission_for_websocket_action(action))
            rate_limit_websocket(principal, "command")
            if action in interrupt_actions:
                result = await asyncio.to_thread(run_command, context, action, payload)
            else:
                async with command_lock:
                    result = await asyncio.to_thread(
                        run_command,
                        context,
                        action,
                        payload,
                    )
            write_audit_event(
                actor=principal.actor,
                role=principal.role,
                action=f"websocket:{action}",
                outcome="ok",
            )
            await send(
                {
                    "type": "command_result",
                    "id": command_id,
                    "ok": True,
                    "action": action,
                    "payload": result,
                }
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            detail = websocket_error_detail(exc)
            code = websocket_error_code(exc)
            if not isinstance(exc, OperationCancelledError):
                context.add_error(detail)
            if not isinstance(exc, (PhytoAutoscopyError, SecurityError)):
                logger.exception("Unhandled WebSocket command error: %s", action)
            write_audit_event(
                actor=principal.actor,
                role=principal.role,
                action=f"websocket:{action or 'unknown'}",
                outcome=(
                    "cancelled"
                    if isinstance(exc, OperationCancelledError)
                    else "failed"
                ),
                detail=detail,
            )
            try:
                await send(
                    {
                        "type": "command_result",
                        "id": command_id,
                        "ok": False,
                        "action": action,
                        "detail": detail,
                        "code": code,
                    }
                )
            except Exception:
                return
        try:
            await send_snapshot()
        except Exception:
            return

    try:
        await send_snapshot()
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_json(), timeout=1.5)
            except asyncio.TimeoutError:
                await send_snapshot()
                continue
            except ValueError:
                await send(
                    {
                        "type": "error",
                        "detail": "即時訊息必須是有效的 JSON。",
                        "code": "invalid_message",
                    }
                )
                continue

            if not isinstance(message, dict):
                await send(
                    {
                        "type": "error",
                        "detail": "即時訊息格式錯誤。",
                        "code": "invalid_message",
                    }
                )
                continue

            if message.get("type") != "command":
                await send(
                    {
                        "type": "error",
                        "detail": "不支援的即時訊息類型。",
                        "code": "unsupported_message",
                    }
                )
                continue

            command_id = message.get("id")
            action = str(message.get("action", ""))
            payload = message.get("payload", {})
            task = asyncio.create_task(
                execute_command(command_id, action, payload)
            )
            pending_commands.add(task)
            task.add_done_callback(pending_commands.discard)
    except WebSocketDisconnect:
        return
    except Exception:
        logger.exception("Status WebSocket failed")
        context.add_error(INTERNAL_ERROR_DETAIL)
        try:
            await websocket.close(code=1011, reason="即時連線發生錯誤。")
        except Exception:
            return
    finally:
        tasks = list(pending_commands)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
