from __future__ import annotations

from threading import Event

from fastapi.testclient import TestClient

from app.main import create_app
from app.core.exceptions import OperationCancelledError

from .test_support import authorized_headers, write_test_config


def receive_command_result(websocket, command_id: str) -> dict:
    for _ in range(12):
        message = websocket.receive_json()
        if message.get("type") == "command_result" and message.get("id") == command_id:
            return message
    raise AssertionError(f"Timed out waiting for command result: {command_id}")


def send_command(
    websocket,
    command_id: str,
    action: str,
    payload: dict | None = None,
) -> dict:
    websocket.send_json(
        {
            "type": "command",
            "id": command_id,
            "action": action,
            "payload": payload or {},
        }
    )
    result = receive_command_result(websocket, command_id)
    assert result["action"] == action
    assert result["ok"] is True, result
    return result["payload"]


def test_status_websocket_snapshot_and_command(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        ticket_response = client.post("/api/auth/ws-ticket")
        assert ticket_response.status_code == 200
        ticket = ticket_response.json()["ticket"]
        with client.websocket_connect(f"/ws/status?ticket={ticket}") as websocket:
            snapshot = websocket.receive_json()
            assert snapshot["type"] == "snapshot"
            assert snapshot["payload"]["system"]["mock_mode"] is True
            calibration = snapshot["payload"]["calibration"]
            assert calibration["lock"] == {
                "locked": False,
                "owner": None,
                "mode": None,
                "run_id": None,
                "profile_id": None,
                "acquired_at": None,
                "expires_at": None,
            }
            assert {
                camera["camera_id"]
                for camera in calibration["cameras"]
            } == {"top", "side", "rotating"}
            assert calibration["storage_synchronized"] is True

            websocket.send_json(
                {
                    "type": "command",
                    "id": "motor-engage",
                    "action": "motor.engage",
                    "payload": {},
                }
            )
            result = receive_command_result(websocket, "motor-engage")
            assert result["type"] == "command_result"
            assert result["ok"] is True
            assert result["payload"]["engaged"] is True

            websocket.send_json(
                {
                    "type": "command",
                    "id": "camera-reconnect-all",
                    "action": "camera.reconnect_all",
                    "payload": {},
                }
            )
            result = receive_command_result(websocket, "camera-reconnect-all")
            assert result["type"] == "command_result"
            assert result["ok"] is True
            assert {
                item["camera_id"]
                for item in result["payload"]
            } == {"top", "side", "rotating"}


def test_frontend_websocket_action_contract(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        client.app.state.context.add_error("待清除的測試錯誤")
        ticket = client.post("/api/auth/ws-ticket").json()["ticket"]
        with client.websocket_connect(f"/ws/status?ticket={ticket}") as websocket:
            assert websocket.receive_json()["type"] == "snapshot"

            motor_commands = [
                ("motor-engage", "motor.engage", {}),
                ("motor-move", "motor.move", {"angle_deg": 5}),
                ("motor-stop", "motor.stop", {}),
                ("motor-origin", "motor.set_origin", {}),
                ("motor-return", "motor.return_origin", {}),
                ("motor-disengage", "motor.disengage", {}),
                ("motor-emergency", "motor.emergency_stop", {}),
            ]
            for command_id, action, payload in motor_commands:
                send_command(websocket, command_id, action, payload)

            camera_commands = [
                ("camera-reconnect", "camera.reconnect", {"camera_id": "top"}),
                ("camera-reconnect-all", "camera.reconnect_all", {}),
                ("camera-capture", "camera.capture", {"camera_id": "top"}),
                ("camera-capture-all", "camera.capture_all", {}),
            ]
            for command_id, action, payload in camera_commands:
                send_command(websocket, command_id, action, payload)

            send_command(websocket, "errors-reset", "system.errors.reset")
            assert client.app.state.context.get_recent_errors() == []

            send_command(
                websocket,
                "schedule-start",
                "schedule.start",
                {
                    "duration_seconds": 30,
                    "rotation_start_deg": 0,
                    "rotation_end_deg": 1,
                    "rotation_step_deg": 1,
                    "capture_on_return": False,
                },
            )
            send_command(websocket, "schedule-pause", "schedule.pause")
            send_command(websocket, "schedule-resume", "schedule.resume")
            send_command(websocket, "schedule-stop", "schedule.stop")

            for _ in range(12):
                message = websocket.receive_json()
                if (
                    message.get("type") == "snapshot"
                    and message["payload"]["schedule"]["status"] == "idle"
                ):
                    break
            else:
                raise AssertionError("排程停止後未回到待命狀態")

            reset = send_command(
                websocket,
                "schedule-reset",
                "schedule.reset",
            )
            assert reset["status"] == "idle"


def test_websocket_operation_cancelled_does_not_create_notification(
    tmp_path,
    monkeypatch,
) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        context = client.app.state.context
        monkeypatch.setattr(
            context.motor_controller,
            "move_to_angle",
            lambda _angle: (_ for _ in ()).throw(
                OperationCancelledError("馬達移動已停止。")
            ),
        )
        ticket = client.post("/api/auth/ws-ticket").json()["ticket"]
        with client.websocket_connect(f"/ws/status?ticket={ticket}") as websocket:
            assert websocket.receive_json()["type"] == "snapshot"
            websocket.send_json(
                {
                    "type": "command",
                    "id": "cancelled-move",
                    "action": "motor.move",
                    "payload": {"angle_deg": 10},
                }
            )
            result = receive_command_result(websocket, "cancelled-move")

        assert result["ok"] is False
        assert result["code"] == "operation_cancelled"
        assert context.get_recent_errors() == []


def test_websocket_snapshots_continue_during_blocking_command(
    tmp_path,
    monkeypatch,
) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        context = client.app.state.context
        context.motor_controller.engage()
        started = Event()
        release = Event()

        def blocking_move(_angle):
            started.set()
            release.wait(timeout=5)
            return context.motor_controller.status()

        monkeypatch.setattr(
            context.motor_controller,
            "move_to_angle",
            blocking_move,
        )
        ticket = client.post("/api/auth/ws-ticket").json()["ticket"]
        with client.websocket_connect(f"/ws/status?ticket={ticket}") as websocket:
            assert websocket.receive_json()["type"] == "snapshot"
            websocket.send_json(
                {
                    "type": "command",
                    "id": "blocking-move",
                    "action": "motor.move",
                    "payload": {"angle_deg": 10},
                }
            )
            assert started.wait(timeout=1)

            heartbeat = websocket.receive_json()
            assert heartbeat["type"] == "snapshot"

            release.set()
            result = receive_command_result(websocket, "blocking-move")
            assert result["ok"] is True
