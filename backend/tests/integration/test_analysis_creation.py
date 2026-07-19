from __future__ import annotations

import json
import os

import cv2
import numpy as np
import pytest

from app.core.exceptions import AnalysisError
from app.models.analysis_models import AnalysisCreateRequest
from tests.fixtures.analysis_baseline import (
    BASELINE_CALIBRATION_ID,
    BASELINE_RECORD_ID,
    FRAME_COUNT,
)
from tests.integration.analysis_test_support import (
    analysis_parameters,
    assert_raw_unchanged,
    create_analysis_service,
)


def test_analysis_creation_freezes_reproducible_read_only_input(
    tmp_path,
    monkeypatch,
) -> None:
    service, dataset = create_analysis_service(tmp_path, monkeypatch)
    try:
        run = service.create(
            AnalysisCreateRequest(
                record_id=BASELINE_RECORD_ID,
                calibration_id=BASELINE_CALIBRATION_ID,
                parameters=analysis_parameters(),
            ),
            "pytest-operator",
        )

        assert run.status == "draft"
        assert run.method_name == "top_side"
        assert run.method_version
        assert run.created_by == "pytest-operator"
        assert len(run.parameters["input_manifest"]) == FRAME_COUNT * 2
        assert run.parameters["runtime_versions"]["opencv"] != "not-installed"
        assert "minimum_path_edge_weight" in run.parameters["implementation_choices"]
        output = service.settings.paths.analysis_dir / run.record_id / run.analysis_id
        assert (output / "analysis.json").is_file()
        assert (output / "parameters.json").is_file()
        assert (output / "calibration_reference.json").is_file()
        stored = json.loads((output / "analysis.json").read_text(encoding="utf-8"))
        assert stored["git_commit"] == run.git_commit

        validated = service.validate(run.analysis_id)
        assert validated.status == "ready"
        assert validated.total_frames == FRAME_COUNT
        assert len(service.list_frame_pairs(run.analysis_id)) == FRAME_COUNT
        frame_pair_header = (
            output / "frame_pairs.csv"
        ).read_text(encoding="utf-8-sig").splitlines()[0]
        assert "top_frame_id" in frame_pair_header
        assert "side_frame_id" in frame_pair_header
        assert "top_capture_id" not in frame_pair_header
        assert "side_capture_id" not in frame_pair_header
        query_counts = {
            "pairs": 0,
            "detections": 0,
            "corrections": 0,
        }
        original_pairs = service.repository.list_frame_pairs
        original_detections = service.repository.list_detections
        original_corrections = service.repository.list_corrections

        def counted_pairs(analysis_id):
            query_counts["pairs"] += 1
            return original_pairs(analysis_id)

        def counted_detections(analysis_id, camera_id=None):
            query_counts["detections"] += 1
            return original_detections(analysis_id, camera_id)

        def counted_corrections(analysis_id):
            query_counts["corrections"] += 1
            return original_corrections(analysis_id)

        monkeypatch.setattr(
            service.repository,
            "list_frame_pairs",
            counted_pairs,
        )
        monkeypatch.setattr(
            service.repository,
            "list_detections",
            counted_detections,
        )
        monkeypatch.setattr(
            service.repository,
            "list_corrections",
            counted_corrections,
        )

        assert len(service.list_frames(run.analysis_id)) == FRAME_COUNT
        assert query_counts == {
            "pairs": 1,
            "detections": 1,
            "corrections": 1,
        }
        sources = service.list_sources()
        assert len(sources) == 1
        assert sources[0].total_frame_count == FRAME_COUNT
        assert_raw_unchanged(dataset)
    finally:
        service.close()
        dataset["database"].close()


def test_analysis_accepts_and_adapts_different_fixed_camera_resolutions(
    tmp_path,
    monkeypatch,
) -> None:
    service, dataset = create_analysis_service(tmp_path, monkeypatch)
    try:
        for path in dataset["record_path"].rglob("*.png"):
            encoded = np.fromfile(path, dtype=np.uint8)
            image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
            assert image is not None
            target_size = (
                (320, 240)
                if "top" in path.parts
                else (240, 180)
            )
            resized = cv2.resize(
                image,
                target_size,
                interpolation=cv2.INTER_NEAREST,
            )
            encoded_ok, output = cv2.imencode(".png", resized)
            assert encoded_ok
            path.write_bytes(output.tobytes())

        source = service.list_sources()[0]
        assert source.ready is True
        assert source.calibration_status == "valid"
        assert source.not_ready_reasons == []
        assert source.camera_resolutions == {
            "top": (320, 240),
            "side": (240, 180),
        }

        run = service.create(
            AnalysisCreateRequest(
                record_id=BASELINE_RECORD_ID,
                calibration_id=BASELINE_CALIBRATION_ID,
                parameters=analysis_parameters(),
            ),
            "pytest-operator",
        )
        metadata = run.parameters["calibration_resolution_adaptation"]
        assert metadata["calibration_resolution"] == [160, 120]
        assert metadata["cameras"]["top"] == {
            "analysis_resolution": [320, 240],
            "scale_x": 2.0,
            "scale_y": 2.0,
        }
        assert metadata["cameras"]["side"] == {
            "analysis_resolution": [240, 180],
            "scale_x": 1.5,
            "scale_y": 1.5,
        }

        validated = service.validate(run.analysis_id)
        assert validated.status == "ready"
        profile = service.calibration_repository.get(BASELINE_CALIBRATION_ID)
        assert profile is not None
        adaptation = service._adapted_calibration(
            profile,
            service._camera_resolutions(run),
        )
        maps = service._rectification_maps(profile, adaptation)
        assert maps["top"][0].shape == (240, 320)
        assert maps["side"][0].shape == (180, 240)
    finally:
        service.close()
        dataset["database"].close()


def test_unresolved_data_dependent_parameters_fail_without_defaults(
    tmp_path,
    monkeypatch,
) -> None:
    service, dataset = create_analysis_service(tmp_path, monkeypatch)
    try:
        run = service.create(
            AnalysisCreateRequest(
                record_id=BASELINE_RECORD_ID,
                calibration_id=BASELINE_CALIBRATION_ID,
            ),
            "pytest-operator",
        )
        with pytest.raises(AnalysisError, match="不能以虛構值執行"):
            service.validate(run.analysis_id)
        assert service.get_run(run.analysis_id).status == "failed"
        assert_raw_unchanged(dataset)
    finally:
        service.close()
        dataset["database"].close()


def test_frozen_sha256_detects_same_size_same_mtime_tampering(
    tmp_path,
    monkeypatch,
) -> None:
    service, dataset = create_analysis_service(tmp_path, monkeypatch)
    try:
        run = service.create(
            AnalysisCreateRequest(
                record_id=BASELINE_RECORD_ID,
                calibration_id=BASELINE_CALIBRATION_ID,
                parameters=analysis_parameters(),
            ),
            "pytest-operator",
        )
        path = next(dataset["record_path"].rglob("*.png"))
        original = path.read_bytes()
        original_stat = path.stat()
        tampered = bytearray(original)
        tampered[-20] ^= 1
        path.write_bytes(tampered)
        os.utime(
            path,
            ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
        )
        assert path.stat().st_size == original_stat.st_size
        assert path.stat().st_mtime_ns == original_stat.st_mtime_ns
        service._validator.image_probe = lambda _path: (160, 120)

        with pytest.raises(AnalysisError, match="輸入.*已變更"):
            service.validate(run.analysis_id)
    finally:
        if "original" in locals():
            path.write_bytes(original)
        service.close()
        dataset["database"].close()


def test_analysis_rejects_calibration_projected_as_stale(
    tmp_path,
    monkeypatch,
) -> None:
    service, dataset = create_analysis_service(tmp_path, monkeypatch)
    try:
        run = service.create(
            AnalysisCreateRequest(
                record_id=BASELINE_RECORD_ID,
                calibration_id=BASELINE_CALIBRATION_ID,
                parameters=analysis_parameters(),
            ),
            "pytest-operator",
        )
        profile = service.calibration_repository.get(BASELINE_CALIBRATION_ID)
        stale = profile.model_copy(
            update={
                "status": "potentially_invalid",
                "valid": False,
                "potentially_invalid_reasons": ["相機裝置索引已變更。"],
            },
            deep=True,
        )

        class StaleCalibrationService:
            def get_profile(self, _calibration_id):
                return stale

            def list_profiles(self):
                return [stale]

        service.calibration_service = StaleCalibrationService()
        with pytest.raises(AnalysisError, match="尚未通過驗證|可能已失效"):
            service.validate(run.analysis_id)
        source = service.list_sources()[0]
        assert source.calibration_status == "missing_or_invalid"
        assert source.ready is True
        assert "沒有有效的相機校正設定檔。" not in source.not_ready_reasons
    finally:
        service.close()
        dataset["database"].close()
