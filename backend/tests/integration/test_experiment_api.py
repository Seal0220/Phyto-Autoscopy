from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

from .test_support import authorized_headers, write_test_config


def test_experiment_api_creates_session(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        response = client.post("/api/experiments/start", json={})
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "running"
        assert payload["session_id"].startswith("session_")
