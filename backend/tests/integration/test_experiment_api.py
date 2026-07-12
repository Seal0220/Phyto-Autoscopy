from __future__ import annotations

import csv
import time

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


def test_experiment_modes_write_isolated_images_and_logs(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    request = {
        "duration_seconds": 60,
        "rotation_start_deg": 0,
        "rotation_end_deg": 1,
        "rotation_step_deg": 1,
        "angle_tolerance_deg": 0.1,
        "modes": [
            {"id": "seconds", "type": "seconds_interval", "interval_seconds": 60},
            {"id": "angle", "type": "angle_interval", "interval_degrees": 1},
            {"id": "specific", "type": "specific_angles", "angles": "0,1"},
            {"id": "equal", "type": "equal_divisions", "points": 2},
        ],
    }

    with TestClient(create_app(), headers=authorized_headers()) as client:
        response = client.post("/api/experiments/start", json=request)
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        modes_dir = tmp_path / "data" / "captures" / session_id / "modes"
        expected_folders = {
            "01_seconds_interval_seconds",
            "02_angle_interval_angle",
            "03_specific_angles_specific",
            "04_equal_divisions_equal",
        }

        def mode_ready(folder: str) -> bool:
            log_path = modes_dir / folder / "capture_log.csv"
            if not log_path.exists():
                return False
            try:
                with log_path.open(encoding="utf-8-sig", newline="") as handle:
                    rows = list(csv.DictReader(handle))
            except OSError:
                return False
            return {row["camera_id"] for row in rows} == {
                "top",
                "fixed_side",
                "rotating_arm",
            }

        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            ready = all(mode_ready(folder) for folder in expected_folders)
            if ready:
                break
            time.sleep(0.05)
        else:
            raise AssertionError("Timed out waiting for all schedule mode logs")

        client.post("/api/experiments/stop")

        assert {path.name for path in modes_dir.iterdir() if path.is_dir()} == expected_folders
        first_capture_times: dict[str, dict[str, str]] = {}
        for folder in expected_folders:
            mode_dir = modes_dir / folder
            with (mode_dir / "capture_log.csv").open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            assert rows
            assert all(row["elapsed_seconds"] for row in rows)
            assert all(row["actual_angle_deg"] for row in rows)
            assert all(row["image_name"] for row in rows)
            assert all(row["captured_at"] for row in rows)
            assert {row["camera_id"] for row in rows} == {
                "top",
                "fixed_side",
                "rotating_arm",
            }
            assert all(
                any((mode_dir / camera_id).glob("*.jpg"))
                for camera_id in ("top", "fixed_side", "rotating_arm")
            )
            first_capture_times[folder] = {
                camera_id: next(row["captured_at"] for row in rows if row["camera_id"] == camera_id)
                for camera_id in ("top", "fixed_side", "rotating_arm")
            }

        for camera_id in ("top", "fixed_side", "rotating_arm"):
            assert len({times[camera_id] for times in first_capture_times.values()}) == 1
