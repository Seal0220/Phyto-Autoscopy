from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

from .test_support import authorized_headers, write_test_config


def test_settings_group_read_and_write_preserves_payload(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        current = client.get("/api/settings/cameras")
        assert current.status_code == 200
        payload = current.json()
        payload["cameras"]["top"]["preview_fps"] = 12

        updated = client.post("/api/settings/cameras", json={"payload": payload})
        assert updated.status_code == 200
        assert updated.json()["updated"] == "cameras"
        assert updated.json()["applied"] is True

        status = client.get("/api/cameras")
        assert status.status_code == 200
        assert next(item for item in status.json() if item["camera_id"] == "top")["fps"] == 12

        reloaded = client.get("/api/settings/cameras")
        assert reloaded.status_code == 200
        assert reloaded.json()["cameras"]["top"]["preview_fps"] == 12
