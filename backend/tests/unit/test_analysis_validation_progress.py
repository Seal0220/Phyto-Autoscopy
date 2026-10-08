from __future__ import annotations

from dataclasses import replace
from threading import Event, RLock
from types import SimpleNamespace

import pytest

from app.analysis.record_validator import CaptureFrame
from app.core.exceptions import AnalysisPausedError
from app.models.analysis_models import AnalysisRun
from app.services import analysis_service
from app.services.analysis_service import AnalysisService


def _service(tmp_path):
    service = AnalysisService.__new__(AnalysisService)
    service._preview_lock = RLock()
    service._validation_progress = {}
    service._validation_progress_times = {}
    service._live_progress = {}
    service._processing_previews = {}
    service.repository = SimpleNamespace(update_state=lambda *args, **kwargs: None)
    service._artifacts = lambda _: SimpleNamespace(root=tmp_path)
    service.progress_callback = None
    return service


def _run():
    return AnalysisRun(
        analysis_id="analysis-test", record_id="record", method_name="rotating",
        method_version="1", git_commit="test", parameters={}, created_by="test",
        created_at="2026-10-05T00:00:00+00:00", updated_at="2026-10-05T00:00:00+00:00",
        output_path="analysis-test", status="draft",
    )


def test_live_progress_bypasses_large_run_loads_and_throttles_without_losing_final_update(monkeypatch, tmp_path):
    service, run = _service(tmp_path), _run()
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
def test_validation_cache_is_removed_on_success_and_failure(fails, tmp_path):
    service, run = _service(tmp_path), _run()
    updates = []
    service.repository = SimpleNamespace(update_state=lambda *args, **kwargs: updates.append(kwargs))
    service._lock = RLock()
    service._runner = SimpleNamespace(is_active=lambda _: False, start=lambda _: True)
    state = [run]
    service._require_run = lambda _: state[0]

    def set_state(current, **kwargs):
        state[0] = current.model_copy(update=kwargs)
        return state[0]

    service._set_state = set_state
    service._record_failure = lambda *args, **kwargs: None

    def validate(current, event):
        service._update_validation_progress(current, "verifying_input_files", 32, 65, .69)
        if fails:
            raise ValueError("test failure")
        return set_state(current, status="ready", progress=1)

    service._validate_round_analysis = validate
    assert service.validate(run.analysis_id).status == "validating"
    service._run_job(run.analysis_id, Event())
    assert updates[-1]["current_frame"] == 32
    if not fails:
        assert state[0].progress == 1
    assert service._validation_progress == {}
    assert service._validation_progress_times == {}


@pytest.mark.parametrize("pause_during_runtime", [False, True])
def test_validation_checks_frozen_inputs_and_defers_round_processing(monkeypatch, tmp_path, pause_during_runtime):
    service, run = _service(tmp_path), _run()
    run.parameters["pose_strategy"] = {"baseline_mm": 100, "top_height_mm": 200}
    events, persisted = [], []
    probe = SimpleNamespace(backend_counts={"gpu": 0, "cpu": 0, "converted": 0, "verified": 65}, hashes={})
    monkeypatch.setattr(analysis_service, "FrozenImageProbe", lambda *args, **kwargs: probe)
    service.progress_callback = events.append
    artifacts = SimpleNamespace(root=tmp_path, write_parameters=persisted.append)
    service._artifacts = lambda _: artifacts

    def validate(current, *, progress_callback, image_probe):
        assert image_probe is probe
        progress_callback(65, 65)
        return SimpleNamespace(camera_resolutions={camera: (1280, 960) for camera in ("top", "side", "rotating")})

    service._validation_for_run = validate
    service._blocking_validation_messages = lambda _: []
    service._verify_frozen_manifest = lambda *args, progress_callback, hashes: [progress_callback(0, 65), progress_callback(65, 65)]
    service._intrinsics_for_run = lambda _: {camera: SimpleNamespace(width=1280, height=960) for camera in ("top", "side", "rotating")}
    service.repository = SimpleNamespace(
        list_rounds=lambda _: [SimpleNamespace(status="ready")],
        list_views=lambda _: [],
        update_parameters=lambda *args: None,
        update_state=lambda *args, **kwargs: None,
    )
    cancellation = Event()
    def runtime(_):
        if pause_during_runtime:
            cancellation.pause_requested = True
            cancellation.set()
        return {"available": True}
    service._reconstruction_backends = SimpleNamespace(probe_runtime=runtime)
    service._set_state = lambda current, **kwargs: current.model_copy(update=kwargs)
    service._log = lambda *args: None
    if pause_during_runtime:
        with pytest.raises(AnalysisPausedError):
            service._validate_round_analysis(run, cancellation)
        assert not persisted
        return
    completed = service._validate_round_analysis(run, cancellation)
    assert [event.stage for event in events] == ["validating_images", "verifying_input_files", "verifying_input_files", "checking_reconstruction_environment"]
    assert [event.progress for event in events] == [.45, .45, .95, .95]
    assert completed.status == "ready"
    assert completed.stage == "validation_completed"
    assert completed.progress == 1
    assert persisted[0]["validation_image_probe_backends"] == probe.backend_counts
