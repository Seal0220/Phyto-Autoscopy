from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

from .test_support import authorized_headers, write_test_config


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
            result = websocket.receive_json()
            assert result["type"] == "command_result"
            assert result["ok"] is True
            assert result["payload"]["engaged"] is True
