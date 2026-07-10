from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

from .test_support import write_test_config


def test_motor_api_engages_and_moves_in_mock_mode(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app()) as client:
        assert client.post("/api/motor/engage").status_code == 200
        response = client.post("/api/motor/move", json={"angle_deg": 10})
        assert response.status_code == 200
        assert response.json()["command_position_deg"] == 10
