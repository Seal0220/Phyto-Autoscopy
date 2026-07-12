from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.state import AppContext, get_context
from app.hardware.motor.motor_safety import MotorSafety
from app.models.motor_models import MotorSettingsUpdate, MotorStatus, MoveRequest
from app.services.schedule_lock import ensure_manual_changes_allowed

router = APIRouter(prefix="/api/motor", tags=["motor"])


@router.get("/status", response_model=MotorStatus)
def motor_status(context: AppContext = Depends(get_context)) -> MotorStatus:
    return context.motor_controller.status()


@router.post("/engage", response_model=MotorStatus)
def engage_motor(context: AppContext = Depends(get_context)) -> MotorStatus:
    ensure_manual_changes_allowed(context)
    return context.motor_controller.engage()


@router.post("/disengage", response_model=MotorStatus)
def disengage_motor(context: AppContext = Depends(get_context)) -> MotorStatus:
    ensure_manual_changes_allowed(context)
    return context.motor_controller.disengage()


@router.post("/set-origin", response_model=MotorStatus)
def set_origin(context: AppContext = Depends(get_context)) -> MotorStatus:
    ensure_manual_changes_allowed(context)
    return context.motor_controller.set_origin()


@router.post("/move", response_model=MotorStatus)
def move_motor(request: MoveRequest, context: AppContext = Depends(get_context)) -> MotorStatus:
    ensure_manual_changes_allowed(context)
    return context.motor_controller.move_to_angle(request.angle_deg)


@router.post("/move-relative", response_model=MotorStatus)
def move_relative(request: MoveRequest, context: AppContext = Depends(get_context)) -> MotorStatus:
    ensure_manual_changes_allowed(context)
    return context.motor_controller.move_relative(request.angle_deg)


@router.post("/return-origin", response_model=MotorStatus)
def return_origin(context: AppContext = Depends(get_context)) -> MotorStatus:
    ensure_manual_changes_allowed(context)
    return context.motor_controller.return_origin()


@router.post("/stop", response_model=MotorStatus)
def stop_motor(context: AppContext = Depends(get_context)) -> MotorStatus:
    ensure_manual_changes_allowed(context)
    return context.motor_controller.stop()


@router.post("/emergency-stop", response_model=MotorStatus)
def emergency_stop(context: AppContext = Depends(get_context)) -> MotorStatus:
    return context.motor_controller.emergency_stop()


@router.post("/test-cycle", response_model=list[MotorStatus])
def test_cycle(context: AppContext = Depends(get_context)) -> list[MotorStatus]:
    ensure_manual_changes_allowed(context)
    current = context.motor_controller.status().command_position_deg
    target = min(current + 5.0, context.settings.motor.maximum_angle_deg)
    return [context.motor_controller.move_to_angle(target), context.motor_controller.return_origin()]


@router.post("/settings", response_model=MotorStatus)
def update_motor_settings(
    update: MotorSettingsUpdate,
    context: AppContext = Depends(get_context),
) -> MotorStatus:
    ensure_manual_changes_allowed(context)
    settings = context.settings.motor
    safety = MotorSafety(settings)
    payload = update.model_dump(exclude_none=True)
    if "current_limit_amp" in payload:
        safety.validate_current_limit(payload["current_limit_amp"])
    if "velocity_limit_deg_s" in payload:
        safety.validate_velocity(payload["velocity_limit_deg_s"])
    if "acceleration_deg_s2" in payload:
        safety.validate_acceleration(payload["acceleration_deg_s2"])
    for key, value in payload.items():
        setattr(settings, key, value)
    return context.motor_controller.status()
