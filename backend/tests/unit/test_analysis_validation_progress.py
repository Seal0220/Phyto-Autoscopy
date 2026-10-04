from __future__ import annotations

from dataclasses import replace
from threading import RLock
from types import SimpleNamespace

import pytest

from app.analysis.record_validator import CaptureFrame
from app.models.analysis_models import AnalysisRun
from app.services import analysis_service
from app.services.analysis_service import AnalysisService


def _service():
    service = AnalysisService.__new__(AnalysisService)
    service._preview_lock = RLock()
    service._validation_progress = {}
    service._validation_progress_times = {}
    service.progress_callback = None
    return service


def _run():
    return AnalysisRun(
        analysis_id="analysis-test", record_id="record", method_name="rotating",
        method_version="1", git_commit="test", parameters={}, created_by="test",
        created_at="2026-10-05T00:00:00+00:00", updated_at="2026-10-05T00:00:00+00:00",
        output_path="analysis-test", status="draft",
    )


def test_live_progress_bypasses_large_run_loads_and_throttles_without_losing_final_update(monkeypatch):
    service, run = _service(), _run()
    events = []
    service.progress_callback = events.append
    service._require_run = lambda _: pytest.fail("Progress must not load the frozen manifests")
    monkeypatch.setattr(analysis_service, "monotonic", lambda: 1.0)
    service._update_validation_progress(run, "validating_images", 0, 100, 0)
    service._update_validation_progress(run, "validating_images", 32, 100, .144)
    assert len(events) == 1
    service._update_validation_progress(run, "validating_images", 100, 100, .45,
                                        image_probe_backends={"gpu": 100, "cpu": 0, "converted": 100})
    assert len(events) == 2
    assert service.get_progress(run.analysis_id).current_frame == 100
    assert service.get_progress().progress == .45
    service._update_validation_progress(run, "verifying_input_files", 0, 100, .45)
    assert service.get_progress().image_probe_backends["gpu"] == 100


def test_hash_progress_preserves_integrity_checks_and_reports_processed_images(tmp_path):
    source = tmp_path / "source.png"
    source.write_bytes(b"original")
    frame = CaptureFrame(capture_id=1, camera_id="top", timestamp="2026-10-05T00:00:00+00:00",
                         file_path=source, relative_path="source.png", resolution=(30, 20))
    validation = SimpleNamespace(frames=tuple(replace(frame, capture_id=index) for index in range(65)))
    run = _run()
    run.parameters["source_manifest"] = AnalysisService._manifest(validation)
    events = []
    AnalysisService._verify_frozen_manifest(run, validation, progress_callback=lambda *args: events.append(args))
    assert events == [(0, 65), (32, 65), (64, 65), (65, 65)]
    source.write_bytes(b"changed")
    with pytest.raises(Exception, match="輸入在分析紀錄建立後已變更"):
        AnalysisService._verify_frozen_manifest(run, validation)


@pytest.mark.parametrize("fails", [False, True])
def test_validation_cache_is_removed_on_success_and_failure(fails):
    service, run = _service(), _run()
    updates = []
    service.repository = SimpleNamespace(update_state=lambda *args, **kwargs: updates.append(kwargs))
    service._lock = RLock()
    service._runner = SimpleNamespace(is_active=lambda _: False)
    service._require_run = lambda _: run
    service._set_state = lambda *args, **kwargs: run
    service._record_failure = lambda *args, **kwargs: None

    def validate(current):
        service._update_validation_progress(current, "verifying_input_files", 32, 65, .69)
        if fails:
            raise ValueError("test failure")
        return current.model_copy(update={"status": "ready", "progress": 1})

    service._validate_round_analysis = validate
    if fails:
        with pytest.raises(Exception, match="test failure"):
            service.validate(run.analysis_id)
        assert updates[-1]["current_frame"] == 32
    else:
        assert service.validate(run.analysis_id).progress == 1
    assert service._validation_progress == {}
    assert service._validation_progress_times == {}


def test_validation_connects_gpu_probe_all_stages_and_completed_counts(monkeypatch, tmp_path):
    service, run = _service(), _run()
    run.parameters["pose_strategy"] = {"baseline_mm": 100, "top_height_mm": 200}
    events, persisted = [], []
    probe = SimpleNamespace(backend_counts={"gpu": 65, "cpu": 0, "converted": 65}, close=lambda: None)
    monkeypatch.setattr(analysis_service, "AnalysisImageProbe", lambda root: probe)
    service.progress_callback = events.append
    artifacts = SimpleNamespace(root=tmp_path, write_parameters=persisted.append)
    service._artifacts = lambda _: artifacts

    def validate(current, *, progress_callback, image_probe):
        assert image_probe is probe
        progress_callback(65, 65)
        return SimpleNamespace(camera_resolutions={camera: (1280, 960) for camera in ("top", "side", "rotating")})

    service._validation_for_run = validate
    service._blocking_validation_messages = lambda _: []
    service._verify_frozen_manifest = lambda *args, progress_callback: [progress_callback(0, 65), progress_callback(65, 65)]
    service._intrinsics_for_run = lambda _: {camera: SimpleNamespace(width=1280, height=960) for camera in ("top", "side", "rotating")}
    service.repository = SimpleNamespace(
        list_rounds=lambda _: [SimpleNamespace(status="ready")],
        list_views=lambda _: [],
        update_parameters=lambda *args: None,
    )
    service._reconstruction_backends = SimpleNamespace(probe_runtime=lambda _: {"available": True})
    service._set_state = lambda current, **kwargs: current.model_copy(update=kwargs)
    service._log = lambda *args: None
    completed = service._validate_round_analysis(run)
    assert [event.stage for event in events] == ["validating_images", "verifying_input_files", "verifying_input_files", "checking_reconstruction_environment"]
    assert [event.progress for event in events] == [.45, .45, .95, .95]
    assert completed.status == "ready"
    assert completed.stage == "validation_completed"
    assert completed.progress == 1
    assert persisted[0]["validation_image_probe_backends"] == probe.backend_counts
