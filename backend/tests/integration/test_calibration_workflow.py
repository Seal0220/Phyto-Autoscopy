from __future__ import annotations

import json

import pytest

from app.core.exceptions import CalibrationError
from tests.calibration_support import (
    calibration_request,
    create_calibration_harness,
    seed_synthetic_corner_detections,
    synthetic_stereo_points,
    write_image_sets,
)


def test_complete_calibration_service_workflow_and_delete_protection(tmp_path) -> None:
    harness = create_calibration_harness(tmp_path)
    top_paths, side_paths, stereo_pairs = write_image_sets(harness, count=10)
    profile = harness.service.create(
        calibration_request(top_paths, side_paths, stereo_pairs)
    )
    seed_synthetic_corner_detections(profile, synthetic_stereo_points())
    harness.repository.update(profile)

    with pytest.raises(CalibrationError, match="請先完成俯視與側視單目校正"):
        harness.service.solve_stereo(profile.calibration_id)
    failed = harness.repository.get(profile.calibration_id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.last_error is not None

    intrinsics = harness.service.solve_intrinsics(profile.calibration_id)
    assert intrinsics.status == "intrinsics_solved"
    assert intrinsics.last_error is None
    assert intrinsics.top_camera_matrix is not None
    assert intrinsics.side_camera_matrix is not None
    assert len(intrinsics.top_distortion_coefficients) >= 5
    assert len(intrinsics.side_distortion_coefficients) >= 5
    assert intrinsics.camera_projection_models["top"] == "brown_pinhole"
    assert intrinsics.camera_projection_models["side"] == "brown_pinhole"
    assert set(intrinsics.camera_model_evaluations["top"]) == {
        "brown_pinhole",
        "fisheye",
    }
    assert intrinsics.camera_image_sizes == {
        "top": [640, 480],
        "side": [640, 480],
    }

    stereo = harness.service.solve_stereo(profile.calibration_id)
    assert stereo.status == "stereo_solved"
    assert stereo.last_error is None
    assert stereo.rotation_matrix is not None
    assert stereo.translation_vector is not None
    assert stereo.essential_matrix is not None
    assert stereo.fundamental_matrix is not None
    assert stereo.top_projection_matrix is not None
    assert stereo.side_projection_matrix is not None

    validated = harness.service.validate(profile.calibration_id)
    report = harness.service.report(profile.calibration_id)
    profile_directory = harness.settings.paths.calibration_dir / profile.calibration_id

    assert validated.status == "valid"
    assert validated.valid is True
    assert validated.last_error is None
    assert validated.distortion_coefficient_order == ["k1", "k2", "p1", "p2", "k3"]
    assert report.valid is True
    assert report.image_count == {
        "top": 10,
        "side": 10,
        "rotating": 0,
        "stereo": 10,
    }
    assert report.successful_corner_detections == {
        "top": 10,
        "side": 10,
        "rotating": 0,
        "stereo": 10,
    }
    assert set(report.reprojection_error_per_image) == {"top", "side", "stereo"}
    assert set(report.point_coverage) == {"top", "side", "stereo"}
    assert report.mean_reprojection_errors["top"] < 0.01
    assert report.mean_reprojection_errors["side"] < 0.01
    assert report.mean_reprojection_errors["stereo"] < 0.01
    for file_name in (
        "calibration.json",
        "selected_images.json",
        "reprojection_errors.csv",
        "top_intrinsics.json",
        "side_intrinsics.json",
        "stereo_extrinsics.json",
    ):
        assert (profile_directory / file_name).is_file()
    top_intrinsics = json.loads(
        (profile_directory / "top_intrinsics.json").read_text(encoding="utf-8")
    )
    assert top_intrinsics["distortion_coefficient_order"] == [
        "k1",
        "k2",
        "p1",
        "p2",
        "k3",
    ]
    assert set(top_intrinsics["distortion_named"]) == {"k1", "k2", "p1", "p2", "k3"}

    harness.database.execute(
        "INSERT INTO records(record_id, created_at, status, record_path) VALUES (?, ?, ?, ?)",
        ("record-1", "2026-07-17T00:00:00+00:00", "completed", str(tmp_path)),
    )
    harness.database.execute(
        """
        INSERT INTO analysis_runs(
            analysis_id, record_id, calibration_id, method_name, method_version,
            git_commit, parameters_json, created_at, updated_at, created_by,
            output_path, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "analysis-1",
            "record-1",
            profile.calibration_id,
            "top_side",
            "1.0.0",
            "test-commit",
            "{}",
            "2026-07-17T00:00:00+00:00",
            "2026-07-17T00:00:00+00:00",
            "pytest",
            str(tmp_path / "analysis"),
            "completed",
        ),
    )
    with pytest.raises(CalibrationError, match="已被分析引用"):
        harness.service.delete(profile.calibration_id)
    assert profile_directory.is_dir()
    assert harness.repository.get(profile.calibration_id) is not None

    harness.database.execute("DELETE FROM analysis_runs WHERE analysis_id='analysis-1'")
    harness.service.delete(profile.calibration_id)
    assert not profile_directory.exists()
    assert harness.repository.get(profile.calibration_id) is None
    harness.database.close()


def test_resolution_change_keeps_valid_profile_available_but_source_change_does_not(
    tmp_path,
) -> None:
    harness = create_calibration_harness(tmp_path)
    top_paths, side_paths, stereo_pairs = write_image_sets(harness, count=10)
    profile = harness.service.create(
        calibration_request(top_paths, side_paths, stereo_pairs)
    )
    seed_synthetic_corner_detections(profile, synthetic_stereo_points())
    harness.repository.update(profile)
    harness.service.solve_intrinsics(profile.calibration_id)
    harness.service.solve_stereo(profile.calibration_id)
    harness.service.validate(profile.calibration_id)

    harness.settings.cameras["top"].width = 800
    resized = harness.service.get_profile(profile.calibration_id)

    assert resized.status == "valid"
    assert resized.valid is True
    assert resized.potentially_invalid_reasons == []
    assert harness.repository.get(profile.calibration_id) is not None

    harness.settings.cameras["top"].width = 640
    first_image = top_paths[0]
    with open(first_image, "ab") as handle:
        handle.write(b"changed")
    changed_source = harness.service.get_profile(profile.calibration_id)
    assert changed_source.valid is False
    assert any(
        "校正來源影像內容已變更" in reason
        for reason in changed_source.potentially_invalid_reasons
    )
    harness.database.close()


def test_profile_recovers_from_persisted_resolution_only_invalidation(tmp_path) -> None:
    harness = create_calibration_harness(tmp_path)
    top_paths, side_paths, stereo_pairs = write_image_sets(harness, count=10)
    profile = harness.service.create(
        calibration_request(top_paths, side_paths, stereo_pairs)
    )
    seed_synthetic_corner_detections(profile, synthetic_stereo_points())
    harness.repository.update(profile)
    harness.service.solve_intrinsics(profile.calibration_id)
    harness.service.solve_stereo(profile.calibration_id)
    profile = harness.service.validate(profile.calibration_id)

    profile.status = "potentially_invalid"
    profile.valid = False
    profile.last_error = "相機設定已變更，請重新校正。"
    profile.potentially_invalid_reasons = ["top 的影像寬度已變更。"]
    harness.repository.update(profile)

    recovered = harness.service.get_profile(profile.calibration_id)

    assert recovered.status == "valid"
    assert recovered.valid is True
    assert recovered.last_error is None
    assert recovered.potentially_invalid_reasons == []
    harness.database.close()
