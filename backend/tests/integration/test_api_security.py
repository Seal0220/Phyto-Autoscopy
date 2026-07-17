from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app

from .test_support import authorized_headers, write_test_config


def test_backend_rejects_unauthenticated_api_calls(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app()) as client:
        response = client.get("/api/system/status")
    assert response.status_code == 401


def test_backend_does_not_publish_docs_or_schema_by_default(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app()) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_backend_accepts_authenticated_bff_call(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        response = client.get("/api/system/status")
    assert response.status_code == 200


def test_viewer_cannot_operate_hardware(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    headers = authorized_headers()
    headers["X-Phyto-Role"] = "viewer"
    with TestClient(create_app(), headers=headers) as client:
        response = client.post("/api/motor/engage")
    assert response.status_code == 403


def test_viewer_cannot_start_schedule(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    headers = authorized_headers()
    headers["X-Phyto-Role"] = "viewer"
    with TestClient(create_app(), headers=headers) as client:
        response = client.post("/api/schedules/start", json={})
    assert response.status_code == 403


def test_viewer_can_read_analysis_and_calibration_lists(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    headers = authorized_headers()
    headers["X-Phyto-Role"] = "viewer"
    with TestClient(create_app(), headers=headers) as client:
        analysis_response = client.get("/api/analysis")
        calibration_response = client.get("/api/calibrations")

    assert analysis_response.status_code == 200
    assert calibration_response.status_code == 200


def test_viewer_cannot_mutate_analysis_or_calibration(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    headers = authorized_headers()
    headers["X-Phyto-Role"] = "viewer"
    with TestClient(create_app(), headers=headers) as client:
        analysis_response = client.post("/api/analysis", json={})
        calibration_response = client.post("/api/calibrations", json={})

    assert analysis_response.status_code == 403
    assert calibration_response.status_code == 403


def test_websocket_requires_a_one_use_ticket(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/status"):
                pass

        ticket_response = client.post("/api/auth/ws-ticket")
        ticket = ticket_response.json()["ticket"]
        with client.websocket_connect(f"/ws/status?ticket={ticket}") as websocket:
            assert websocket.receive_json()["type"] == "snapshot"

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/ws/status?ticket={ticket}"):
                pass
