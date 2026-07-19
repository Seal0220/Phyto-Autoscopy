from __future__ import annotations

import json
import os

import numpy as np
import pytest
from pydantic import ValidationError

from app.core.exceptions import CalibrationError
from app.models.calibration_models import CalibrationCreateRequest
from tests.calibration_support import (
    calibration_request,
    create_calibration_harness,
    render_chessboard,
    write_image_sets,
    write_png,
)


def test_create_request_requires_measured_parameters_and_world_transform() -> None:
    with pytest.raises(ValidationError) as error:
        CalibrationCreateRequest(
            top_image_paths=["top.png"],
            side_image_paths=["side.png"],
            stereo_image_pairs=[["top.png", "side.png"]],
        )

    missing_fields = {
        item["loc"][0]
        for item in error.value.errors()
        if item["type"] == "missing"
    }
    assert missing_fields == {
        "square_size_mm_x",
        "square_size_mm_y",
        "stereo_pattern_columns",
        "stereo_pattern_rows",
        "stereo_square_size_mm_x",
        "stereo_square_size_mm_y",
        "world_transform_matrix",
    }


def test_create_request_rejects_non_rigid_world_transform() -> None:
    with pytest.raises(ValidationError, match="必須正交"):
        CalibrationCreateRequest(
            top_image_paths=["top.png"],
            side_image_paths=["side.png"],
            stereo_image_pairs=[["top.png", "side.png"]],
            square_size_mm_x=12,
            square_size_mm_y=12,
            stereo_pattern_columns=10,
            stereo_pattern_rows=7,
            stereo_square_size_mm_x=12,
            stereo_square_size_mm_y=12,
            world_transform_matrix=[
                [2, 0, 0, 0],
                [0, 1, 0, 0],
                [0, 0, 1, 0],
                [0, 0, 0, 1],
            ],
        )


def test_create_request_rejects_shared_top_and_side_intrinsic_image() -> None:
    with pytest.raises(ValidationError, match="不得重複"):
        CalibrationCreateRequest(
            top_image_paths=["shared.png"],
            side_image_paths=["shared.png"],
            stereo_image_pairs=[["top.png", "side.png"]],
            square_size_mm_x=12,
            square_size_mm_y=12,
            stereo_pattern_columns=10,
            stereo_pattern_rows=7,
            stereo_square_size_mm_x=12,
            stereo_square_size_mm_y=12,
            world_transform_matrix=np.eye(4).tolist(),
        )


def test_create_rejects_images_outside_allowed_data_roots(tmp_path) -> None:
    harness = create_calibration_harness(tmp_path)
    top_paths, side_paths, stereo_pairs = write_image_sets(harness)
    outside = tmp_path / "outside.png"
    write_png(outside, render_chessboard())
    request = calibration_request(top_paths, side_paths, stereo_pairs)
    request.top_image_paths = [str(outside)]

    with pytest.raises(CalibrationError, match="必須位於"):
        harness.service.create(request)

    assert harness.repository.list() == []
    harness.database.close()


def test_create_writes_traceable_draft_and_lists_only_decodable_sources(
    tmp_path,
) -> None:
    harness = create_calibration_harness(tmp_path)
    top_paths, side_paths, stereo_pairs = write_image_sets(harness)
    (harness.captures_dir / "not-an-image.jpg").write_text(
        "not an image",
        encoding="utf-8",
    )

    profile = harness.service.create(
        calibration_request(top_paths, side_paths, stereo_pairs)
    )
    sources = harness.service.list_source_images()
    profile_directory = harness.settings.paths.calibration_dir / profile.calibration_id

    assert profile.status == "draft"
    assert profile.valid is False
    assert profile.stereo_chessboard_pattern == [10, 7]
    assert profile.stereo_square_size_mm == [12.0, 12.0]
    assert profile.world_transform_matrix == np.eye(4).tolist()
    assert profile.paper_baseline["stereo_pattern"] is None
    assert profile.actual_measurement_difference[
        "square_sizes_are_explicit_measurements"
    ] is True
    assert len(profile.selected_image_fingerprints) == 2
    assert all(item["name"] != "not-an-image.jpg" for item in sources)
    assert {item["source"] for item in sources} == {"captures"}
    assert (profile_directory / "calibration.json").is_file()
    assert (profile_directory / "selected_images.json").is_file()
    assert (profile_directory / "reprojection_errors.csv").is_file()
    assert (profile_directory / "previews").is_dir()
    harness.database.close()


def test_detect_corners_writes_all_previews_and_resets_old_solution(tmp_path) -> None:
    harness = create_calibration_harness(tmp_path)
    top_paths, side_paths, stereo_pairs = write_image_sets(harness)
    profile = harness.service.create(
        calibration_request(top_paths, side_paths, stereo_pairs)
    )
    profile.top_camera_matrix = np.eye(3).tolist()
    profile.top_distortion_coefficients = [0, 0, 0, 0, 0]
    profile.rotation_matrix = np.eye(3).tolist()
    profile.status = "valid"
    profile.valid = True
    harness.repository.update(profile)

    detected = harness.service.detect_corners(profile.calibration_id)
    preview_names = {
        detected.corner_detections["top"][0]["preview_name"],
        detected.corner_detections["side"][0]["preview_name"],
        detected.corner_detections["stereo"][0]["top"]["preview_name"],
        detected.corner_detections["stereo"][0]["side"]["preview_name"],
    }

    assert detected.status == "corners_detected"
    assert detected.last_error is None
    assert detected.top_camera_matrix is None
    assert detected.rotation_matrix is None
    assert preview_names == {
        "top_0001.jpg",
        "side_0001.jpg",
        "stereo_0001_top.jpg",
        "stereo_0001_side.jpg",
    }
    for preview_name in preview_names:
        assert harness.service.get_preview_path(
            profile.calibration_id,
            preview_name,
        ).is_file()
    assert all(
        item["name"] not in preview_names
        for item in harness.service.list_source_images()
    )
    with pytest.raises(CalibrationError, match="檔名無效"):
        harness.service.get_preview_path(profile.calibration_id, "../calibration.json")
    harness.database.close()


def test_intrinsics_reject_mixed_resolutions_and_persists_recoverable_error(
    tmp_path,
) -> None:
    harness = create_calibration_harness(tmp_path)
    top_paths, side_paths, stereo_pairs = write_image_sets(harness)
    second_top = harness.captures_dir / "top_different_resolution.png"
    write_png(
        second_top,
        render_chessboard(image_size=(800, 600)),
    )
    top_paths.append(str(second_top))
    profile = harness.service.create(
        calibration_request(top_paths, side_paths, stereo_pairs)
    )
    harness.service.detect_corners(profile.calibration_id)

    with pytest.raises(CalibrationError, match="單鏡頭相機校正失敗"):
        harness.service.solve_intrinsics(profile.calibration_id)

    failed = harness.repository.get(profile.calibration_id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.valid is False
    assert "解析度不一致" in failed.last_error
    assert failed.top_camera_matrix is None
    harness.database.close()


def test_profile_file_is_restored_if_database_update_fails(
    tmp_path,
    monkeypatch,
) -> None:
    harness = create_calibration_harness(tmp_path)
    top_paths, side_paths, stereo_pairs = write_image_sets(harness)
    profile = harness.service.create(
        calibration_request(top_paths, side_paths, stereo_pairs)
    )
    profile_path = (
        harness.settings.paths.calibration_dir
        / profile.calibration_id
        / "calibration.json"
    )
    before = json.loads(profile_path.read_text(encoding="utf-8"))

    def fail_update(_profile) -> None:
        raise OSError("simulated database failure")

    monkeypatch.setattr(harness.repository, "update", fail_update)
    with pytest.raises(CalibrationError, match="寫入"):
        harness.service.mark_potentially_invalid(
            profile.calibration_id,
            "鏡頭已重新安裝",
        )

    after = json.loads(profile_path.read_text(encoding="utf-8"))
    assert after == before
    assert list(profile_path.parent.glob(".*.tmp")) == []
    harness.database.close()


def test_delete_restores_profile_directory_if_database_delete_fails(
    tmp_path,
    monkeypatch,
) -> None:
    harness = create_calibration_harness(tmp_path)
    top_paths, side_paths, stereo_pairs = write_image_sets(harness)
    profile = harness.service.create(
        calibration_request(top_paths, side_paths, stereo_pairs)
    )
    profile_directory = (
        harness.settings.paths.calibration_dir / profile.calibration_id
    )

    def fail_delete(_calibration_id: str) -> None:
        raise OSError("simulated database failure")

    monkeypatch.setattr(harness.repository, "delete", fail_delete)
    with pytest.raises(CalibrationError, match="刪除"):
        harness.service.delete(profile.calibration_id)

    assert profile_directory.is_dir()
    assert (profile_directory / "calibration.json").is_file()
    assert list(profile_directory.parent.glob(".*.deleting")) == []
    assert harness.repository.get(profile.calibration_id) is not None
    harness.database.close()


def test_stale_check_hashes_content_even_when_size_and_mtime_match(
    tmp_path,
) -> None:
    harness = create_calibration_harness(tmp_path)
    top_paths, side_paths, stereo_pairs = write_image_sets(harness)
    profile = harness.service.create(
        calibration_request(top_paths, side_paths, stereo_pairs)
    )
    source = harness.service._safe_image_path(top_paths[0])
    original = source.read_bytes()
    original_stat = source.stat()
    tampered = bytearray(original)
    tampered[-20] ^= 1
    source.write_bytes(tampered)
    os.utime(
        source,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
    )

    try:
        projected = harness.service.get_profile(profile.calibration_id)

        assert projected.potentially_invalid_reasons
        assert any(
            "內容已變更" in reason
            for reason in projected.potentially_invalid_reasons
        )
    finally:
        source.write_bytes(original)
        harness.database.close()


def test_referenced_calibration_solution_is_immutable(tmp_path) -> None:
    harness = create_calibration_harness(tmp_path)
    top_paths, side_paths, stereo_pairs = write_image_sets(harness)
    profile = harness.service.create(
        calibration_request(top_paths, side_paths, stereo_pairs)
    )
    harness.database.execute(
        """
        INSERT INTO records(record_id, created_at, status, record_path)
        VALUES (?, ?, ?, ?)
        """,
        (
            "record-reference",
            "2026-07-17T00:00:00+00:00",
            "completed",
            str(tmp_path / "record-reference"),
        ),
    )
    harness.database.execute(
        """
        INSERT INTO analysis_runs(
            analysis_id, record_id, calibration_id, method_name,
            method_version, git_commit, parameters_json, created_at,
            updated_at, created_by, output_path, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "analysis-reference",
            "record-reference",
            profile.calibration_id,
            "test-method",
            "1",
            "unknown",
            "{}",
            "2026-07-17T00:00:00+00:00",
            "2026-07-17T00:00:00+00:00",
            "pytest",
            str(tmp_path / "analysis-reference"),
            "draft",
        ),
    )
    before = harness.repository.get(profile.calibration_id)

    try:
        with pytest.raises(CalibrationError, match="已被分析引用"):
            harness.service.detect_corners(profile.calibration_id)

        assert harness.repository.get(profile.calibration_id) == before
    finally:
        harness.database.close()
