from __future__ import annotations

from threading import Event, Thread

from fastapi.testclient import TestClient

from app.analysis.analysis_runner import AnalysisJobManager
from app.main import create_app

from .test_support import authorized_headers, write_test_config


def test_motor_api_engages_and_moves_in_mock_mode(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        assert client.post("/api/motor/engage").status_code == 200
        response = client.post("/api/motor/move", json={"angle_deg": 10})
        assert response.status_code == 200
        assert response.json()["command_position_deg"] == 10


def test_motor_api_uses_fixed_zero_origin(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        assert client.post("/api/motor/engage").status_code == 200
        assert client.post("/api/motor/move", json={"angle_deg": 10}).status_code == 200

        response = client.post("/api/motor/set-origin")
        assert response.status_code == 200
        assert response.json()["command_position_deg"] == 0.0
        assert "origin_deg" not in response.json()

        assert client.post("/api/motor/move", json={"angle_deg": 10}).status_code == 200
        response = client.post("/api/motor/return-origin")
        assert response.status_code == 200
        assert response.json()["command_position_deg"] == 0.0


def test_emergency_stop_is_not_blocked_by_running_analysis_worker(
    tmp_path,
    monkeypatch,
) -> None:
    write_test_config(tmp_path, monkeypatch)
    analysis_started = Event()
    release_analysis = Event()
    request_completed = Event()
    request_outcome = []

    def blocking_analysis(_analysis_id: str, _cancel_event: Event) -> None:
        analysis_started.set()
        assert release_analysis.wait(timeout=3)

    with TestClient(create_app(), headers=authorized_headers()) as client:
        analysis_service = client.app.state.context.analysis_service
        original_runner = analysis_service._runner
        blocking_runner = AnalysisJobManager(blocking_analysis)
        analysis_service._runner = blocking_runner

        def request_emergency_stop() -> None:
            try:
                request_outcome.append(client.post("/api/motor/emergency-stop"))
            except BaseException as error:
                request_outcome.append(error)
            finally:
                request_completed.set()

        try:
            assert blocking_runner.start("analysis-blocking-proof") is True
            assert analysis_started.wait(timeout=1)
            assert blocking_runner.running_analysis_ids() == (
                "analysis-blocking-proof",
            )

            request_thread = Thread(target=request_emergency_stop)
            request_thread.start()
            completed_before_analysis_release = request_completed.wait(timeout=1)
        finally:
            release_analysis.set()
            if "request_thread" in locals():
                request_thread.join(timeout=2)
            blocking_runner.close()
            analysis_service._runner = original_runner

        assert completed_before_analysis_release is True
        assert len(request_outcome) == 1
        response = request_outcome[0]
        assert not isinstance(response, BaseException)
        assert response.status_code == 200
        assert response.json()["emergency_stopped"] is True
