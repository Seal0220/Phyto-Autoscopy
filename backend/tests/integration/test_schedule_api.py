from __future__ import annotations

import csv
import time

from fastapi.testclient import TestClient

from app.main import create_app

from .test_support import authorized_headers, write_test_config


def test_schedule_api_creates_record(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        response = client.post("/api/schedules/start", json={})
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "running"
        assert payload["record_id"].startswith("record_")
        assert payload["total_steps"] == 3


def test_schedule_can_disable_return_path_capture(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    with TestClient(create_app(), headers=authorized_headers()) as client:
        response = client.post(
            "/api/schedules/start",
            json={"capture_on_return": False},
        )

        assert response.status_code == 200
        assert response.json()["total_steps"] == 2
        assert client.post("/api/schedules/stop").status_code == 200


def test_schedule_modes_write_isolated_images_and_logs(tmp_path, monkeypatch) -> None:
    write_test_config(tmp_path, monkeypatch)
    request = {
        "rotation_start_deg": 0,
        "rotation_end_deg": 1,
        "angle_tolerance_deg": 0.1,
        "capture_on_return": True,
        "modes": [
            {"id": "time", "type": "time_interval", "interval_seconds": 60},
            {"id": "angle", "type": "angle_interval", "interval_degrees": 1},
            {"id": "specific", "type": "specific_angles", "angles": "0,1"},
            {"id": "equal", "type": "equal_divisions", "points": 2},
        ],
    }

    with TestClient(create_app(), headers=authorized_headers()) as client:
        response = client.post("/api/schedules/start", json=request)
        assert response.status_code == 200
        record_id = response.json()["record_id"]
        modes_dir = tmp_path / "data" / "captures" / record_id / "modes"
        expected_folders = {
            "TimeInterval.01",
            "AngleInterval.01",
            "SpecificAngles.01",
            "EqualDivisions.01",
        }
        mode_log_names = {
            folder: "mode.log.csv"
            for folder in expected_folders
        }

        def mode_ready(folder: str) -> bool:
            log_path = modes_dir / folder / mode_log_names[folder]
            if not log_path.exists():
                return False
            try:
                with log_path.open(encoding="utf-8-sig", newline="") as handle:
                    rows = list(csv.DictReader(handle))
            except OSError:
                return False
            has_all_cameras = {row["camera_id"] for row in rows} == {
                "top",
                "side",
                "rotating",
            }
            if folder == "TimeInterval.01":
                return has_all_cameras
            return has_all_cameras and "return" in {
                row["motion_direction"]
                for row in rows
            }

        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            ready = all(mode_ready(folder) for folder in expected_folders)
            if ready:
                break
            time.sleep(0.05)
        else:
            raise AssertionError("Timed out waiting for all schedule mode logs")

        stop_response = client.post("/api/schedules/stop")
        assert stop_response.status_code == 200

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            status_response = client.get("/api/schedules/status")
            assert status_response.status_code == 200
            if status_response.json()["status"] == "idle":
                break
            time.sleep(0.05)
        else:
            raise AssertionError("Timed out waiting for schedule to return to idle")

        records_response = client.get("/api/records")
        assert records_response.status_code == 200
        record = next(
            item
            for item in records_response.json()
            if item["record_id"] == record_id
        )
        assert record["ended_at"]

        record_dir = modes_dir.parent
        assert (record_dir / "config.json").is_file()
        assert (record_dir / "metadata.csv").is_file()
        assert (record_dir / "record.log.csv").is_file()

        assert {path.name for path in modes_dir.iterdir() if path.is_dir()} == expected_folders
        first_capture_times: dict[str, dict[str, str]] = {}
        for folder in expected_folders:
            mode_dir = modes_dir / folder
            with (mode_dir / mode_log_names[folder]).open(
                encoding="utf-8-sig",
                newline="",
            ) as handle:
                rows = list(csv.DictReader(handle))
            assert (mode_dir / "config.json").is_file()
            assert (mode_dir / "metadata.csv").is_file()
            assert rows
            assert all(row["elapsed_seconds"] for row in rows)
            assert all(row["actual_angle_deg"] for row in rows)
            assert all(row["image_name"] for row in rows)
            assert all(row["captured_at"] for row in rows)
            assert {
                row["motion_direction"]
                for row in rows
            }.issubset({"forward", "return"})
            if folder != "TimeInterval.01":
                assert {
                    row["motion_direction"]
                    for row in rows
                } == {"forward", "return"}
            assert {row["camera_id"] for row in rows} == {
                "top",
                "side",
                "rotating",
            }
            image_names = {
                path.name
                for path in mode_dir.glob("rounds/round.*/snapshot.*/*.png")
            }
            assert image_names
            assert all(
                any(image_name.startswith(f"{camera_id}-") for image_name in image_names)
                for camera_id in ("top", "side", "rotating")
            )
            first_capture_times[folder] = {
                camera_id: next(row["captured_at"] for row in rows if row["camera_id"] == camera_id)
                for camera_id in ("top", "side", "rotating")
            }

        for camera_id in ("top", "side", "rotating"):
            assert len({times[camera_id] for times in first_capture_times.values()}) == 1
