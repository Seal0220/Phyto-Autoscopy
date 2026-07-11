from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

from .test_support import authorized_headers, write_test_config


def test_rotation_cycle_captures_mock_arm_frames(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        assert client.post("/api/motor/engage").status_code == 200
        response = client.post(
            "/api/capture/rotation-cycle",
            json={"cycle_id": 1, "start_deg": 0, "end_deg": 15, "step_deg": 15},
        )
        assert response.status_code == 200
        assert len(response.json()) == 2
