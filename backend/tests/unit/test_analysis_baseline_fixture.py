from __future__ import annotations

import hashlib

from app.analysis.record_validator import validate_capture_record
from tests.fixtures.analysis_baseline import create_analysis_baseline


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_baseline_contains_fixed_pairs_labels_calibration_and_trajectory(tmp_path) -> None:
    dataset = create_analysis_baseline(tmp_path / "dataset")
    manifest = dataset["manifest"]

    assert manifest["frame_count"] == 8
    assert len(manifest["pairs"]) == 8
    assert len(manifest["manual_tip_labels"]) == 12
    assert len(manifest["known_world_points"]) == 6
    assert manifest["expected_trajectory_range_mm"]["z"] == [399.99, 400.01]
    assert dataset["calibration_path"].is_file()


def test_baseline_validates_without_modifying_raw_captures(tmp_path) -> None:
    dataset = create_analysis_baseline(tmp_path / "dataset")
    record_path = dataset["record_path"]
    before = {
        relative_path: _sha256(record_path / relative_path)
        for relative_path in dataset["manifest"]["raw_sha256"]
    }

    result = validate_capture_record({
        "record_id": dataset["manifest"]["record_id"],
        "status": "completed",
        "record_path": str(record_path),
    })

    after = {
        relative_path: _sha256(record_path / relative_path)
        for relative_path in dataset["manifest"]["raw_sha256"]
    }
    assert result.ready is True
    assert result.top_frame_count == 8
    assert result.side_frame_count == 8
    assert before == after == dataset["manifest"]["raw_sha256"]
