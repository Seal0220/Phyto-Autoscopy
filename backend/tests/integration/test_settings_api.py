from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.core.config import load_settings
from app.core.exceptions import ConfigError
from app.main import create_app

from .test_support import authorized_headers, write_test_config


def test_explicit_production_mode_disables_mock_config(
    tmp_path,
    monkeypatch,
) -> None:
    config_dir = write_test_config(tmp_path, monkeypatch)
    monkeypatch.setenv("PHYTO_AUTOSCOPY_MOCK", "0")

    settings = load_settings(config_dir)

    assert settings.hardware.mock_mode is False


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
        assert next(item for item in status.json() if item["camera_id"] == "top")["preview_fps"] == 12

        reloaded = client.get("/api/settings/cameras")
        assert reloaded.status_code == 200
        assert reloaded.json()["cameras"]["top"]["preview_fps"] == 12


def test_camera_settings_persist_unassigned_disabled_device(
    tmp_path,
    monkeypatch,
) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        payload = client.get("/api/settings/cameras").json()
        payload["cameras"]["rotating"]["enabled"] = False
        payload["cameras"]["rotating"]["device_index"] = None

        updated = client.post(
            "/api/settings/cameras",
            json={"payload": payload},
        )

        assert updated.status_code == 200
        reloaded = client.get("/api/settings/cameras").json()
        assert reloaded["cameras"]["rotating"]["enabled"] is False
        assert reloaded["cameras"]["rotating"]["device_index"] is None


def test_schedule_settings_persist_capture_on_return(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        current = client.get("/api/settings/schedule")
        assert current.status_code == 200
        payload = current.json()
        assert payload["schedule"]["capture_on_return"] is True

        payload["schedule"]["capture_on_return"] = False
        updated = client.post(
            "/api/settings/schedule",
            json={"payload": payload},
        )

        assert updated.status_code == 200
        reloaded = client.get("/api/settings/schedule")
        assert reloaded.status_code == 200
        assert reloaded.json()["schedule"]["capture_on_return"] is False


def test_settings_apply_failure_restores_runtime_and_file(tmp_path, monkeypatch) -> None:
    config_dir = write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        current = client.get("/api/settings/cameras").json()
        original_fps = current["cameras"]["top"].get("preview_fps", 5)
        current["cameras"]["top"]["preview_fps"] = 12
        context = client.app.state.context

        def fail_scan():
            raise RuntimeError("private driver failure")

        monkeypatch.setattr(context.camera_manager, "reconfigure", fail_scan)
        response = client.post(
            "/api/settings/cameras",
            json={"payload": current},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "套用設定失敗，已還原原設定。"
        assert context.settings.cameras["top"].preview_fps == original_fps
        stored = json.loads((config_dir / "cameras.json").read_text(encoding="utf-8"))
        assert stored["cameras"]["top"].get("preview_fps", 5) == original_fps


def test_duplicate_enabled_camera_index_is_rejected_without_changing_file(
    tmp_path,
    monkeypatch,
) -> None:
    config_dir = write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        current = client.get("/api/settings/cameras").json()
        current["cameras"]["side"]["device_index"] = 0

        response = client.post(
            "/api/settings/cameras",
            json={"payload": current},
        )

        assert response.status_code == 400
        assert response.json()["code"] == "config_error"
        stored = json.loads(
            (config_dir / "cameras.json").read_text(encoding="utf-8")
        )
        assert stored["cameras"]["side"]["device_index"] == 1
        assert client.app.state.context.settings.cameras["side"].device_index == 1


def test_settings_persist_failure_does_not_change_runtime(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        current = client.get("/api/settings/cameras").json()
        original_fps = client.app.state.context.settings.cameras["top"].preview_fps
        current["cameras"]["top"]["preview_fps"] = 12

        def fail_save(*_args, **_kwargs):
            raise ConfigError("無法儲存測試設定。")

        monkeypatch.setattr(
            "app.api.settings_routes.save_settings_group",
            fail_save,
        )
        response = client.post(
            "/api/settings/cameras",
            json={"payload": current},
        )

        assert response.status_code == 400
        assert client.app.state.context.settings.cameras["top"].preview_fps == original_fps


def test_capture_root_change_preserves_old_records_and_avoids_id_collision(
    tmp_path,
    monkeypatch,
) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        first_capture = client.post("/api/cameras/top/capture")
        assert first_capture.status_code == 200
        first_record_id = first_capture.json()["record_id"]

        default_payload = client.get("/api/settings/default").json()
        default_payload["paths"]["captures_dir"] = str(tmp_path / "new-captures")
        updated = client.post(
            "/api/settings/default",
            json={"payload": default_payload},
        )
        assert updated.status_code == 200

        old_detail = client.get(f"/api/records/{first_record_id}")
        old_file = client.get(f"/api/records/{first_record_id}/record-json")
        assert old_detail.status_code == 200
        assert old_file.status_code == 200

        second_capture = client.post("/api/cameras/top/capture")
        assert second_capture.status_code == 200
        assert second_capture.json()["record_id"] != first_record_id

        deleted = client.delete(f"/api/records/{first_record_id}")
        assert deleted.status_code == 200
