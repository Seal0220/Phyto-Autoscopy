from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.main import create_app
from app.core.exceptions import OperationCancelledError
from app.services.schedule_lock import schedule_is_active

from .test_support import authorized_headers, write_test_config


def test_http_errors_use_safe_traditional_chinese_contract(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(
        create_app(),
        headers=authorized_headers(),
        raise_server_exceptions=False,
    ) as client:
        missing = client.get("/api/cameras/not-a-camera/status")
        invalid = client.post("/api/motor/move", json={"angle_deg": "abc"})

        assert missing.status_code == 400
        assert missing.json()["code"] == "camera_error"
        assert missing.json()["detail"] == "找不到相機：not-a-camera"
        assert invalid.status_code == 422
        assert invalid.json() == {
            "detail": "請求資料格式錯誤，請檢查輸入內容。",
            "code": "validation_error",
        }

        context = client.app.state.context
        original_disk_status = context.health_service.disk_status

        def fail_disk_status():
            raise RuntimeError("private filesystem detail")

        monkeypatch.setattr(context.health_service, "disk_status", fail_disk_status)
        unexpected = client.get("/api/system/status")
        monkeypatch.setattr(
            context.health_service,
            "disk_status",
            original_disk_status,
        )

        assert unexpected.status_code == 500
        assert unexpected.json() == {
            "detail": "伺服器處理請求時發生錯誤，請稍後再試。",
            "code": "internal_error",
        }
        assert all(
            "private filesystem detail" not in error
            for error in context.get_recent_errors()
        )

        reset = client.post("/api/system/errors/reset")
        assert reset.status_code == 200
        assert context.get_recent_errors() == []


def test_final_status_write_failure_releases_schedule_lock(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        context = client.app.state.context
        original_update_status = context.record_service.update_status

        def fail_final_status(record_id: str, status: str) -> None:
            if status in {"completed", "stopped", "failed"}:
                raise OSError("private record write failure")
            original_update_status(record_id, status)

        monkeypatch.setattr(
            context.record_service,
            "update_status",
            fail_final_status,
        )
        started = client.post(
            "/api/schedules/start",
            json={
                "duration_seconds": 30,
                "rotation_start_deg": 0,
                "rotation_end_deg": 1,
                "rotation_step_deg": 1,
                "capture_on_return": False,
            },
        )
        assert started.status_code == 200
        assert client.post("/api/schedules/stop").status_code == 200

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            status = context.schedule_service.get_status()
            if status.status == "failed":
                break
            time.sleep(0.02)
        else:
            raise AssertionError("排程終態寫入失敗後未釋放背景狀態")

        assert context.schedule_service._worker is None
        assert context.record_service.active_record_id is None
        assert schedule_is_active(context) is False
        assert "private record write failure" not in (status.last_error or "")
        assert "伺服器處理請求時發生錯誤，請稍後再試。" in context.get_recent_errors()

        reset = client.post("/api/schedules/reset")
        assert reset.status_code == 200
        assert reset.json()["status"] == "idle"


def test_http_operation_cancelled_does_not_create_notification(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        context = client.app.state.context
        monkeypatch.setattr(
            context.motor_controller,
            "move_to_angle",
            lambda _angle: (_ for _ in ()).throw(
                OperationCancelledError("馬達移動已停止。")
            ),
        )

        response = client.post("/api/motor/move", json={"angle_deg": 10})

        assert response.status_code == 400
        assert response.json()["code"] == "operation_cancelled"
        assert context.get_recent_errors() == []
