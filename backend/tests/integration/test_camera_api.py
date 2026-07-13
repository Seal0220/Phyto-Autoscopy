from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

from .test_support import authorized_headers, write_test_config


def test_camera_api_lists_mock_cameras(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        response = client.get("/api/cameras")
        assert response.status_code == 200
        camera_ids = {item["camera_id"] for item in response.json()}
        assert camera_ids == {"top", "side", "rotating"}


def test_camera_api_reconnects_all_mock_cameras(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        response = client.post("/api/cameras/reconnect-all")

        assert response.status_code == 200
        assert {
            item["camera_id"]
            for item in response.json()
        } == {"top", "side", "rotating"}


def test_record_capture_relation_is_read_from_sqlite(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        capture = client.post("/api/cameras/top/capture")
        assert capture.status_code == 200
        record_id = capture.json()["record_id"]

        response = client.get(f"/api/records/{record_id}/captures")

        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["file_path"] == capture.json()["file_path"]


def test_preview_snapshot_is_flat_and_does_not_create_record(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        response = client.post("/api/cameras/side/snapshot")

        assert response.status_code == 200
        assert response.json()["file_path"].startswith("side_")
        assert response.json()["file_path"].endswith(".jpg")
        snapshot_path = (
            tmp_path / "data" / "snapshots" / response.json()["file_path"]
        )
        assert snapshot_path.is_file()
        assert list((tmp_path / "data" / "snapshots").iterdir()) == [snapshot_path]
        assert client.get("/api/records").json() == []


def test_snapshot_all_uses_camera_short_names(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        response = client.post("/api/cameras/snapshot-all")

        assert response.status_code == 200
        names = {item["file_path"].split("_", 1)[0] for item in response.json()}
        assert names == {"top", "side", "rotating"}
        assert client.get("/api/records").json() == []
