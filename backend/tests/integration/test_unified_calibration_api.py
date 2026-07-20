from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from threading import Event
import time

import numpy as np
from fastapi.testclient import TestClient

from app.main import create_app

from .test_support import authorized_headers, write_test_config


def intrinsic_solution(camera_id: str):
    result = {
        "camera_model": "opencv",
        "camera_matrix": [
            [900.0, 0.0, 640.0],
            [0.0, 900.0, 360.0],
            [0.0, 0.0, 1.0],
        ],
        "distortion_coefficients": [0.0, 0.0, 0.0, 0.0, 0.0],
        "reprojection_error_px": 0.3,
        "median_reprojection_error_px": 0.25,
        "maximum_reprojection_error_px": 0.6,
        "validation_error_px": 0.4,
        "per_image_errors": [],
        "stable": True,
        "score": 0.9,
        "width": 1280,
        "height": 720,
        "sample_count": 12,
        "coverage": {
            "accepted_sample_count": 12,
            "grid_coverage": 1.0,
            "edge_sample_count": 6,
            "scale_span": 0.2,
            "pose_diversity": 0.3,
            "ready": True,
        },
        "quality_status": "acceptable",
    }
    return {"opencv": dict(result)}, result


def extrinsic_solution(profile, _observations, _intrinsics):
    transforms = {
        "top": [0.0, 0.0, 0.0],
        "side": [120.0, 0.0, 0.0],
        "rotating": [0.0, 120.0, 0.0],
    }
    cameras = []
    for camera in profile.cameras:
        transform = np.eye(4, dtype=np.float64)
        transform[:3, 3] = transforms[camera.camera_id]
        cameras.append(camera.model_copy(
            update={
                "transform_rig_from_camera": transform.tolist(),
                "transform_world_from_camera": transform.tolist(),
            },
            deep=True,
        ))
    motion = profile.motion_model.model_copy(
        update={
            "arm_radius_mm": 120.0,
            "rotation_axis_origin_mm": [0.0, 0.0, 0.0],
            "rotation_axis_direction": [0.0, 0.0, 1.0],
            "motor_zero_offset_deg": 0.0,
            "mount_transform_from_camera": np.eye(4).tolist(),
            "lift_axis_direction": [0.0, 0.0, 1.0],
            "fitted_angles_deg": [0.0, 90.0, 180.0, 270.0],
        },
        deep=True,
    )
    world = profile.world_alignment.model_copy(
        update={"transform_world_from_rig": np.eye(4).tolist()},
        deep=True,
    )
    return {
        "cameras": cameras,
        "motion_model": motion,
        "world_alignment": world,
        "quality_status": "acceptable",
        "quality": {
            "mean_reprojection_error_px": 0.5,
            "maximum_reprojection_error_px": 0.9,
            "rotation_axis_fit_error_mm": 1.2,
            "motor_angle_residual_deg": 0.2,
            "arm_path_circularity_error_mm": 1.2,
            "world_scale_error_mm": 0.4,
            "board_pose_consistency_px": 0.3,
            "valid_shared_observation_count": 4,
            "observation_graph": {
                "connected": True,
                "components": [["top", "side", "rotating"]],
                "edge_count": 3,
                "adjacency": {
                    "top": ["side", "rotating"],
                    "side": ["top", "rotating"],
                    "rotating": ["top", "side"],
                },
            },
            "valid_image_count_by_camera": {
                "top": 4,
                "side": 4,
                "rotating": 4,
            },
            "rotation_samples": [],
            "global_optimization": {
                "optimizer": "scipy_least_squares_soft_l1",
                "converged": True,
                "initial_rms_error_px": 0.8,
                "final_rms_error_px": 0.5,
            },
        },
    }


def profile_request(name: str = "整合測試校正檔") -> dict:
    camera_ids = ["top", "side", "rotating"]
    return {
        "name": name,
        "board_profile_id": "default_charuco",
        "camera_ids": camera_ids,
        "cameras": [
            {
                "camera_id": camera_id,
                "position_label": f"{camera_id}-mount",
                "height_mm": 500,
                "offset_x_mm": 0,
                "offset_y_mm": 0,
                "offset_z_mm": 0,
                "mount_description": "integration test",
                "is_movable": camera_id == "rotating",
            }
            for camera_id in camera_ids
        ],
        "motion_model": {
            "arm_height_mm": 450,
            "arm_radius_mm": 120,
            "usable_angle_range_deg": [0, 360],
        },
        "world_alignment": {
            "origin_definition": "platform_center",
            "origin_offset_mm": [0, 0, 0],
            "plant_center_mm": [0, 0, 0],
            "platform_height_mm": 80,
        },
        "notes": "API integration",
    }


def test_unified_calibration_complete_api_flow(
    tmp_path,
    monkeypatch,
) -> None:
    write_test_config(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "app.services.intrinsic_calibration_service.solve_intrinsic_run",
        lambda run: intrinsic_solution(run.camera_id),
    )
    monkeypatch.setattr(
        "app.services.extrinsic_calibration_service.solve_extrinsic_profile",
        extrinsic_solution,
    )
    headers = authorized_headers()

    with TestClient(create_app(), headers=headers) as client:
        lock = client.post(
            "/api/calibration/lock",
            json={"mode": "unified"},
        )
        assert lock.status_code == 200
        assert lock.json()["locked"] is True

        status = client.get("/api/calibration/status")
        assert status.status_code == 200
        assert status.json()["lock_owned_by_requester"] is True
        assert client.post("/api/schedules/start", json={}).status_code == 400

        generated_board = client.post(
            "/api/calibration/boards",
            json={
                "paper_size": "a5",
                "paper_orientation": "portrait",
                "squares_x": 8,
                "squares_y": 6,
            },
        )
        assert generated_board.status_code == 200
        generated_payload = generated_board.json()
        assert generated_payload["name"] == "A5 直向 OpenCV 校正板"
        assert generated_payload["board_type"] == "charuco"
        assert generated_payload["aruco_dictionary"] == "DICT_5X5_100"
        assert generated_payload["paper_size"] == "a5"
        assert generated_payload["paper_orientation"] == "portrait"

        board_image = client.get(
            "/api/calibration/boards/default_charuco/image",
        )
        assert board_image.status_code == 200
        assert board_image.headers["content-type"] == "image/png"
        assert board_image.content.startswith(b"\x89PNG\r\n\x1a\n")
        assert b"pHYs" in board_image.content

        board_download = client.get(
            "/api/calibration/boards/default_charuco/image?download=true",
        )
        assert board_download.status_code == 200
        assert "attachment" in board_download.headers["content-disposition"]

        reconnect = client.post("/api/calibration/cameras/top/reconnect")
        assert reconnect.status_code == 200
        assert client.post("/api/calibration/motor/engage").status_code == 200
        move = client.post(
            "/api/calibration/motor/move",
            json={"angle_deg": 45},
        )
        assert move.status_code == 200

        for camera_id in ("top", "side", "rotating"):
            created = client.post(
                f"/api/calibration/intrinsics/{camera_id}/runs",
                json={
                    "board_profile_id": "default_charuco",
                    "capture_mode": "manual",
                    "camera_model": "auto",
                    "minimum_interval_seconds": 1,
                },
            )
            assert created.status_code == 200
            run_id = created.json()["run_id"]

            captured = client.post(
                f"/api/calibration/intrinsics/{camera_id}/capture",
                json={"run_id": run_id},
            )
            assert captured.status_code == 200
            assert len(captured.json()["samples"]) == 1

            solved = client.post(
                f"/api/calibration/intrinsics/{camera_id}/solve",
                json={"run_id": run_id},
            )
            assert solved.status_code == 200
            assert solved.json()["status"] == "solved"

            applied = client.post(
                f"/api/calibration/intrinsics/{camera_id}/apply",
                json={"run_id": run_id},
            )
            assert applied.status_code == 200
            assert applied.json()["camera_id"] == camera_id

        created_profile = client.post(
            "/api/calibration/extrinsics",
            json=profile_request(),
        )
        assert created_profile.status_code == 200
        profile_id = created_profile.json()["profile_id"]

        observation = client.post(
            f"/api/calibration/extrinsics/{profile_id}/capture",
            json={
                "camera_ids": ["top", "side", "rotating"],
                "motor_angle_deg": 45,
                "arm_height_mm": 450,
            },
        )
        assert observation.status_code == 200
        assert set(observation.json()["camera_images"]) == {
            "top",
            "side",
            "rotating",
        }

        solved_profile = client.post(
            f"/api/calibration/extrinsics/{profile_id}/solve"
        )
        assert solved_profile.status_code == 200
        assert solved_profile.json()["status"] == "validating"

        validated = client.post(
            f"/api/calibration/extrinsics/{profile_id}/validate"
        )
        assert validated.status_code == 200
        assert validated.json()["status"] == "valid"

        activated = client.post(
            f"/api/calibration/extrinsics/{profile_id}/activate"
        )
        assert activated.status_code == 200, activated.text
        assert activated.json()["is_active"] is True

        active_analysis = client.get(
            "/api/calibration/active-analysis-profile"
        )
        assert active_analysis.status_code == 200
        active_payload = active_analysis.json()
        assert active_payload["calibration_id"] == profile_id
        assert active_payload["status"] == "active"
        assert active_payload["rotating_camera_identifier"] == "rotating"
        assert np.asarray(active_payload["essential_matrix"]).shape == (3, 3)
        assert np.asarray(active_payload["fundamental_matrix"]).shape == (3, 3)
        assert np.asarray(active_payload["top_projection_matrix"]).shape == (3, 4)
        assert np.asarray(active_payload["side_projection_matrix"]).shape == (3, 4)
        assert np.asarray(active_payload["disparity_to_depth_matrix"]).shape == (4, 4)

        exported = client.get(
            f"/api/calibration/extrinsics/{profile_id}/export"
        )
        assert exported.status_code == 200
        assert exported.headers["content-type"] == "application/zip"

        released = client.delete("/api/calibration/lock")
        assert released.status_code == 200
        assert released.json()["locked"] is False

    calibration_root = tmp_path / "data" / "calibration"
    assert (calibration_root / "intrinsics" / "top.json").is_file()
    assert (calibration_root / "extrinsics" / profile_id / "profile.json").is_file()
    audit_path = tmp_path / "data" / "logs" / "audit.jsonl"
    audit_events = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
    ]
    assert any(
        event["action"].endswith(f"/extrinsics/{profile_id}/activate")
        and event["outcome"] == "ok"
        for event in audit_events
    )


def test_extrinsic_failure_is_persisted_and_can_be_retried(
    tmp_path,
    monkeypatch,
) -> None:
    write_test_config(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "app.services.intrinsic_calibration_service.solve_intrinsic_run",
        lambda run: intrinsic_solution(run.camera_id),
    )
    monkeypatch.setattr(
        "app.services.extrinsic_calibration_service.solve_extrinsic_profile",
        lambda *_args: (_ for _ in ()).throw(ValueError("觀測圖不連通")),
    )

    with TestClient(
        create_app(),
        headers=authorized_headers(),
    ) as client:
        assert client.post(
            "/api/calibration/lock",
            json={"mode": "unified"},
        ).status_code == 200
        created = client.post(
            "/api/calibration/extrinsics",
            json=profile_request("失敗恢復測試"),
        )
        profile_id = created.json()["profile_id"]

        failed = client.post(
            f"/api/calibration/extrinsics/{profile_id}/solve"
        )
        assert failed.status_code == 400
        persisted = client.get(
            f"/api/calibration/extrinsics/{profile_id}"
        ).json()
        assert persisted["status"] == "invalid"
        assert "觀測圖不連通" in persisted["last_error"]

        monkeypatch.setattr(
            "app.services.extrinsic_calibration_service.solve_extrinsic_profile",
            extrinsic_solution,
        )
        retried = client.post(
            f"/api/calibration/extrinsics/{profile_id}/solve"
        )
        assert retried.status_code == 200
        assert retried.json()["last_error"] is None
        assert retried.json()["status"] == "validating"


def test_schedule_start_and_calibration_lock_are_atomic(
    tmp_path,
    monkeypatch,
) -> None:
    write_test_config(tmp_path, monkeypatch)

    with TestClient(
        create_app(),
        headers=authorized_headers(),
    ) as client:
        context = client.app.state.context
        original_start = context.schedule_service.start
        start_entered = Event()
        allow_start = Event()

        def delayed_start(request=None):
            start_entered.set()
            if not allow_start.wait(timeout=5):
                raise RuntimeError("測試排程啟動等待逾時。")
            return original_start(request)

        monkeypatch.setattr(
            context.schedule_service,
            "start",
            delayed_start,
        )

        with ThreadPoolExecutor(max_workers=2) as executor:
            schedule_future = executor.submit(
                client.post,
                "/api/schedules/start",
                json={},
            )
            assert start_entered.wait(timeout=2)
            calibration_future = executor.submit(
                client.post,
                "/api/calibration/lock",
                json={"mode": "unified"},
            )
            time.sleep(0.1)
            assert calibration_future.done() is False
            allow_start.set()
            schedule_response = schedule_future.result(timeout=5)
            calibration_response = calibration_future.result(timeout=5)

        assert schedule_response.status_code == 200
        assert calibration_response.status_code == 400
        assert "排程進行中" in calibration_response.json()["detail"]
        client.post("/api/schedules/stop")
