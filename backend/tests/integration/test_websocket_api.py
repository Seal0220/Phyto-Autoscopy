from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

from .test_support import authorized_headers, write_test_config


def receive_command_result(websocket, command_id: str) -> dict:
    for _ in range(4):
        message = websocket.receive_json()
        if message.get("type") == "command_result" and message.get("id") == command_id:
            return message
    raise AssertionError(f"Timed out waiting for command result: {command_id}")


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
            } == {"top", "fixed_side", "rotating_arm"}
