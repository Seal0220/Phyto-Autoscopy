from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

from .test_support import write_test_config


def test_camera_api_lists_mock_cameras(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app()) as client:
        response = client.get("/api/cameras")
        assert response.status_code == 200
        camera_ids = {item["camera_id"] for item in response.json()}
        assert camera_ids == {"top", "fixed_side", "rotating_arm"}
