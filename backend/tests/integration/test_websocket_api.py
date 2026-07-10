from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

from .test_support import write_test_config


def test_status_websocket_snapshot_and_command(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app()) as client:
        with client.websocket_connect("/ws/status") as websocket:
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
