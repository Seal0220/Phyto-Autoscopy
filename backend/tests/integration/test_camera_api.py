from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.camera_routes import (
    CAMERA_STREAM_STARTUP_TIMEOUT_SECONDS,
    camera_stream,
)
from app.core.exceptions import CameraError
from app.hardware.cameras.camera_types import CameraFrame
from app.main import create_app

from .test_support import authorized_headers, write_test_config


def test_camera_api_lists_mock_cameras(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        response = client.get("/api/cameras")
        assert response.status_code == 200
        statuses = response.json()
        camera_ids = {item["camera_id"] for item in statuses}
        assert camera_ids == {"top", "side", "rotating"}
        assert all(item["actual_fps"] >= 0 for item in statuses)


def test_camera_stream_allows_slow_physical_camera_startup() -> None:
    calls: list[tuple[str, float]] = []
    frame = CameraFrame(camera_id="top", data=b"jpeg")

    class CameraManager:
        @staticmethod
        def get_status(_camera_id: str):
            return SimpleNamespace(enabled=True)

        @staticmethod
        def wait_for_frame(camera_id: str, timeout: float):
            calls.append((camera_id, timeout))
            return frame, 7

    class ImagePreviewService:
        @staticmethod
        async def mjpeg_stream(camera_id: str, first_frame, first_sequence: int):
            assert camera_id == "top"
            assert first_frame is frame
            assert first_sequence == 7
            if False:
                yield b""

    response = asyncio.run(
        camera_stream(
            "top",
            SimpleNamespace(
                camera_manager=CameraManager(),
                image_preview_service=ImagePreviewService(),
            ),
        ),
    )

    assert response.media_type == "multipart/x-mixed-replace; boundary=frame"
    assert calls == [("top", CAMERA_STREAM_STARTUP_TIMEOUT_SECONDS)]


def test_camera_scan_returns_selectable_device_metadata(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        response = client.get("/api/cameras/scan")

        assert response.status_code == 200
        assert response.json() == [
            {
                "camera_id": "top",
                "camera_name": "CHLOROCULUS EYE-TOP",
                "device_index": 0,
                "connected": True,
                "error": None,
                "in_use": True,
                "backend": "MOCK",
                "mock": True,
            },
            {
                "camera_id": "side",
                "camera_name": "CHLOROCULUS EYE-SIDE",
                "device_index": 1,
                "connected": True,
                "error": None,
                "in_use": True,
                "backend": "MOCK",
                "mock": True,
            },
            {
                "camera_id": "rotating",
                "camera_name": "CHLOROCULUS EYE-ARM",
                "device_index": 2,
                "connected": True,
                "error": None,
                "in_use": True,
                "backend": "MOCK",
                "mock": True,
            },
        ]


def test_camera_api_reconnects_all_mock_cameras(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        response = client.post("/api/cameras/reconnect-all")

        assert response.status_code == 200
        assert {
            item["camera_id"]
            for item in response.json()
        } == {"top", "side", "rotating"}


def test_camera_settings_reject_device_index_used_by_another_camera(
    tmp_path,
    monkeypatch,
) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        response = client.post(
            "/api/cameras/side/settings",
            json={"device_index": 0},
        )

        assert response.status_code == 400
        assert response.json() == {
            "detail": "裝置索引 0 已由相機 top 使用。",
            "code": "camera_error",
        }
        assert client.app.state.context.settings.cameras["side"].device_index == 1


def test_disabled_camera_settings_accept_no_device_index(
    tmp_path,
    monkeypatch,
) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        response = client.post(
            "/api/cameras/side/settings",
            json={
                "enabled": False,
                "device_index": None,
            },
        )

        assert response.status_code == 200
        assert response.json()["settings"]["device_index"] is None
        assert client.app.state.context.settings.cameras["side"].enabled is False
        assert client.app.state.context.settings.cameras["side"].device_index is None


def test_camera_settings_close_timeout_is_reported_and_rolled_back(
    tmp_path,
    monkeypatch,
) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        context = client.app.state.context
        original_fps = context.settings.cameras["top"].preview_fps

        def fail_reconfigure() -> None:
            raise CameraError("舊相機連線尚未安全關閉，請稍後再重新連線。")

        monkeypatch.setattr(
            context.camera_manager,
            "reconfigure",
            fail_reconfigure,
        )
        response = client.post(
            "/api/cameras/top/settings",
            json={"preview_fps": original_fps + 1},
        )

        assert response.status_code == 400
        assert response.json() == {
            "detail": "舊相機連線尚未安全關閉，請稍後再重新連線。",
            "code": "camera_error",
        }
        assert context.settings.cameras["top"].preview_fps == original_fps


def test_camera_reconnect_close_timeout_is_reported(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        context = client.app.state.context

        def fail_reconnect(_camera_id: str):
            raise CameraError("舊相機連線尚未安全關閉，請稍後再重新連線。")

        monkeypatch.setattr(
            context.camera_manager,
            "reconnect",
            fail_reconnect,
        )
        response = client.post("/api/cameras/top/reconnect")

        assert response.status_code == 400
        assert response.json()["detail"] == (
            "舊相機連線尚未安全關閉，請稍後再重新連線。"
        )


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
