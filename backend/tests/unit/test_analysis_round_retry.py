import json
from threading import Event

import pytest

from app.analysis.checkpoints import StepJournal
from app.analysis.export.json_export import write_json_atomic
from app.analysis.reconstruction.model_repair import repair_directory
from app.core.exceptions import AnalysisPausedError, AnalysisReviewRequiredError
from app.models.analysis_models import TipCorrectionRequest
from app.services import analysis_service
from test_analysis_round_pipeline import pipeline  # noqa: F401


def _paused_retry(pipeline, monkeypatch):
    service, repository, artifacts, events, _, _ = pipeline
    first, second = repository.list_rounds("analysis-test")
    repository.update_round(first.model_copy(update={"status": "alignment_pending"}))
    repository.update_state("analysis-test", status="paused", stage="snapshotting_intrinsics", progress=.2,
                            current_frame=1, total_frames=3, updated_at="2026-10-13T00:00:00Z")
    starts = []
    monkeypatch.setattr(service._runner, "start", lambda key: starts.append(key) or True)
    return service, repository, artifacts, events, first, second, starts


def test_retry_round_stops_before_unfinished_next_round_and_continue_is_explicit(pipeline, monkeypatch):
    service, repository, artifacts, events, first, second, starts = _paused_retry(pipeline, monkeypatch)
    other_round = repository.list_rounds("analysis-test")[1]
    service.retry_round("analysis-test", first.round_key)
    service._run_job("analysis-test", Event())
    assert starts == ["analysis-test"]
    assert events == [("preprocess", first.round_key), ("model", first.round_key), ("tip", first.round_key)]
    assert repository.list_rounds("analysis-test")[1] == other_round
    stopped = repository.get("analysis-test")
    assert (stopped.status, stopped.stage, stopped.current_frame, stopped.total_frames) == ("paused", "snapshotting_intrinsics", 1, 3)
    with StepJournal(artifacts.root) as journal:
        assert journal.get("control", "auto_repair") is None
    events.clear()
    service.resume("analysis-test")
    service._run_job("analysis-test", Event())
    assert starts == ["analysis-test", "analysis-test"]
    assert events == [("preprocess", second.round_key), ("model", second.round_key), ("tip", second.round_key)]
    assert repository.get("analysis-test").status == "completed"


@pytest.mark.parametrize("failure", [False, True])
def test_retry_scope_survives_pause_and_keeps_other_repairs_queued(pipeline, monkeypatch, failure):
    service, repository, artifacts, events, first, second, starts = _paused_retry(pipeline, monkeypatch)
    pending_repair = repair_directory(artifacts.root, second.round_key) / "request.json"
    write_json_atomic(pending_repair, {"status": "pending"})
    monkeypatch.setattr(service, "_repair_requested_round_model", lambda *args: pytest.fail("another round's repair must stay queued"))
    preprocess = service._run_round_preprocessing

    def pause(run, event, *, round_key):
        raise AnalysisPausedError("暫停本輪重試")

    monkeypatch.setattr(service, "_run_round_preprocessing", pause)
    service.retry_round("analysis-test", first.round_key)
    event = Event()
    event.pause_requested = True
    service._run_job("analysis-test", event)
    assert repository.get("analysis-test").status == "paused"
    with StepJournal(artifacts.root) as journal:
        assert journal.get("control", "auto_repair")["round_keys"] == [first.round_key]

    def retry(run, event, *, round_key):
        if failure:
            raise AnalysisReviewRequiredError("仍未對齊")
        return preprocess(run, event, round_key=round_key)

    monkeypatch.setattr(service, "_run_round_preprocessing", retry)
    service.resume("analysis-test")
    service._run_job("analysis-test", Event())
    assert repository.get("analysis-test").status == "paused"
    assert repository.list_rounds("analysis-test")[0].status == ("alignment_pending" if failure else "tip_completed")
    assert repository.list_rounds("analysis-test")[1].status == "ready"
    assert all(key == first.round_key for _, key in events)
    assert json.loads(pending_repair.read_text(encoding="utf-8")) == {"status": "pending"}
    assert starts == ["analysis-test", "analysis-test"]
    with StepJournal(artifacts.root) as journal:
        assert journal.get("control", "auto_repair") is None


def test_round_retry_preserves_existing_models_and_manual_marks(pipeline, monkeypatch):
    service, repository, artifacts, events, _, tip = pipeline

    def no_tip(**kwargs):
        raise ValueError("尖端待補標")

    monkeypatch.setattr(analysis_service, "analyze_round_tip", no_tip)
    service._run_job("analysis-test", Event())
    first, second = repository.list_rounds("analysis-test")
    correction = service.save_tip_correction("analysis-test", TipCorrectionRequest(
        round_key=second.round_key, corrected_point_mm=[3, 2, 100], reason="人工尖端",
    ), actor_id="operator")
    model_before = {model.model_path: ((artifacts.root / model.model_path).read_bytes(), (artifacts.root / model.model_path).stat().st_mtime_ns)
                    for model in repository.list_round_models("analysis-test")}
    monkeypatch.setattr(service._runner, "start", lambda _: True)
    monkeypatch.setattr(analysis_service, "analyze_round_tip", tip)
    events.clear()
    service.retry_round("analysis-test", first.round_key)
    service._run_job("analysis-test", Event())
    assert events == [("tip", first.round_key)]
    assert repository.get("analysis-test").status == "completed"
    assert repository.list_tip_corrections("analysis-test") == [correction]
    for path, before in model_before.items():
        assert ((artifacts.root / path).read_bytes(), (artifacts.root / path).stat().st_mtime_ns) == before
