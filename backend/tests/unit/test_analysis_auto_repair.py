from threading import Event
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.analysis.checkpoints import StepJournal
from app.analysis.rounds.repair import rounds_needing_auto_repair
from app.api.analysis_routes import router
from app.core.exceptions import AnalysisError, AnalysisReviewRequiredError
from app.core.state import get_context
from app.models.analysis_models import TipCorrectionRequest
from app.services import analysis_service
from test_analysis_round_pipeline import pipeline  # noqa: F401


def _accept_job(service, monkeypatch):
    starts = []
    monkeypatch.setattr(service._runner, "start", lambda key: starts.append(key) or True)
    return starts


def test_auto_repair_retries_only_failed_round_and_keeps_successful_outputs(pipeline, monkeypatch):
    service, repository, artifacts, events, _, _ = pipeline
    preprocess = service._run_round_preprocessing

    def fail_first(run, event, *, round_key):
        if round_key.endswith("01"):
            raise AnalysisReviewRequiredError("待對齊")
        return preprocess(run, event, round_key=round_key)

    monkeypatch.setattr(service, "_run_round_preprocessing", fail_first)
    service._run_job("analysis-test", Event())
    first, second = repository.list_rounds("analysis-test")
    model = next(item for item in repository.list_round_models("analysis-test") if item.round_key == second.round_key)
    path = artifacts.root / model.model_path
    before = path.read_bytes(), path.stat().st_mtime_ns, repository.list_tip_landmarks("analysis-test")[-1]
    starts = _accept_job(service, monkeypatch)
    monkeypatch.setattr(service, "_run_round_preprocessing", preprocess)
    events.clear()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_context] = lambda: SimpleNamespace(analysis_service=service)
    with TestClient(app) as client:
        response = client.post("/api/analysis/analysis-test/auto-repair", json={})
    assert response.status_code == 200
    assert response.json()["status"] == "processing"
    assert "source_manifest" not in response.json()["parameters"]
    assert starts == ["analysis-test"]
    service._run_job("analysis-test", Event())
    assert events == [("preprocess", first.round_key), ("model", first.round_key), ("tip", first.round_key)]
    assert (path.read_bytes(), path.stat().st_mtime_ns, repository.list_tip_landmarks("analysis-test")[-1]) == before
    assert repository.get("analysis-test").status == "completed"
    with StepJournal(artifacts.root) as journal:
        assert journal.get("control", "auto_repair") is None


def test_auto_repair_preserves_model_and_manual_mark_when_retrying_tip_failure(pipeline, monkeypatch):
    service, repository, artifacts, events, _, tip = pipeline

    def no_tip(**kwargs):
        raise ValueError("missing tip")

    monkeypatch.setattr(analysis_service, "analyze_round_tip", no_tip)
    service._run_job("analysis-test", Event())
    first, second = repository.list_rounds("analysis-test")
    correction = service.save_tip_correction("analysis-test", TipCorrectionRequest(
        round_key=second.round_key, corrected_point_mm=[3, 2, 100], reason="人工尖端",
    ), actor_id="operator")
    models = {model.model_path: ((artifacts.root / model.model_path).read_bytes(), (artifacts.root / model.model_path).stat().st_mtime_ns)
              for model in repository.list_round_models("analysis-test")}
    _accept_job(service, monkeypatch)
    monkeypatch.setattr(analysis_service, "analyze_round_tip", tip)
    events.clear()
    service.auto_repair("analysis-test")
    service._run_job("analysis-test", Event())
    assert events == [("tip", first.round_key)]
    assert repository.list_tip_corrections("analysis-test") == [correction]
    for path, before in models.items():
        assert ((artifacts.root / path).read_bytes(), (artifacts.root / path).stat().st_mtime_ns) == before
    assert [(point.x_mm, point.manually_corrected) for point in repository.list_tip_trajectory("analysis-test")] == [(1, False), (3, True)]


def test_repair_leaves_unstarted_rounds_paused(pipeline, monkeypatch):
    service, repository, artifacts, events, _, _ = pipeline
    first, second = repository.list_rounds("analysis-test")
    repository.update_round(first.model_copy(update={"status": "alignment_pending"}))
    repository.update_state("analysis-test", status="paused", stage="snapshotting_intrinsics", progress=.2, updated_at="2026-10-13T00:00:00Z")
    states = []
    original_set_state = service._set_state

    def record_state(run, **options):
        states.append(options.get("status"))
        return original_set_state(run, **options)

    monkeypatch.setattr(service, "_set_state", record_state)
    _accept_job(service, monkeypatch)
    service.auto_repair("analysis-test")
    service._run_job("analysis-test", Event())
    assert all(key == first.round_key for _, key in events)
    assert repository.list_rounds("analysis-test")[1].status == "ready"
    assert repository.get("analysis-test").status == "paused"
    assert repository.get("analysis-test").stage == "snapshotting_intrinsics"
    assert "completed" not in states and "partially_completed" not in states


@pytest.mark.parametrize("status", ["processing", "reconstructing", "validating", "pausing"])
def test_auto_repair_cannot_modify_live_analysis(pipeline, status):
    service, repository, artifacts, events, _, _ = pipeline
    first = repository.list_rounds("analysis-test")[0]
    repository.update_round(first.model_copy(update={"status": "alignment_pending"}))
    before = repository.list_rounds("analysis-test")
    repository.update_state("analysis-test", status=status, updated_at="2026-10-13T00:00:00Z")
    with pytest.raises(AnalysisError, match="暫停"):
        service.auto_repair("analysis-test")
    assert repository.list_rounds("analysis-test") == before
    assert events == []


def test_manual_exclusion_or_valid_edit_is_not_an_automatic_tip_retry():
    item = SimpleNamespace(round_key="one", status="tip_invalid")
    for invalid, valid in [(True, False), (False, True)]:
        correction = SimpleNamespace(round_key="one", invalid=invalid, pending_alignment=False,
                                     corrected_tip=SimpleNamespace(valid=valid))
        assert rounds_needing_auto_repair([item], [], [], [correction]) == []


def test_no_unresolved_work_is_rejected_without_starting_worker(pipeline, monkeypatch):
    service, _, _, _, _, _ = pipeline
    service._run_job("analysis-test", Event())
    starts = _accept_job(service, monkeypatch)
    with pytest.raises(AnalysisError, match="沒有失敗"):
        service.auto_repair("analysis-test")
    assert starts == []


def test_batch_repairs_once_and_keeps_quality_rejections_pending(pipeline, monkeypatch):
    service, repository, artifacts, events, _, _ = pipeline
    preprocess = service._run_round_preprocessing

    def no_alignment(run, event, *, round_key):
        raise AnalysisReviewRequiredError("未通過精度檢查")

    monkeypatch.setattr(service, "_run_round_preprocessing", no_alignment)
    service._run_job("analysis-test", Event())
    starts = _accept_job(service, monkeypatch)
    keys = [item.round_key for item in repository.list_rounds("analysis-test")]

    def still_fails_first(run, event, *, round_key):
        events.append(("attempt", round_key))
        if round_key == keys[0]:
            raise AnalysisReviewRequiredError("仍未通過精度檢查")
        return preprocess(run, event, round_key=round_key)

    monkeypatch.setattr(service, "_run_round_preprocessing", still_fails_first)
    service.auto_repair("analysis-test")
    service._run_job("analysis-test", Event())
    assert starts == ["analysis-test"]
    assert [key for action, key in events if action == "attempt"] == keys
    assert [item.status for item in repository.list_rounds("analysis-test")] == ["alignment_pending", "tip_completed"]
    assert repository.get("analysis-test").status == "partially_completed"
    with StepJournal(artifacts.root) as journal:
        assert journal.get("control", "auto_repair") is None


def test_pausing_a_repair_keeps_its_scope_for_resume(pipeline, monkeypatch):
    from app.core.exceptions import AnalysisPausedError
    service, repository, artifacts, events, _, _ = pipeline
    first = repository.list_rounds("analysis-test")[0]
    repository.update_round(first.model_copy(update={"status": "alignment_pending"}))
    repository.update_state("analysis-test", status="paused", stage="snapshotting_intrinsics", progress=.2, updated_at="2026-10-13T00:00:00Z")
    starts = _accept_job(service, monkeypatch)
    preprocess = service._run_round_preprocessing

    def pause(run, event, *, round_key):
        raise AnalysisPausedError("暫停修正")

    monkeypatch.setattr(service, "_run_round_preprocessing", pause)
    service.auto_repair("analysis-test")
    event = Event()
    event.pause_requested = True
    service._run_job("analysis-test", event)
    assert repository.get("analysis-test").status == "paused"
    with StepJournal(artifacts.root) as journal:
        assert journal.get("control", "auto_repair")["round_keys"] == [first.round_key]
    monkeypatch.setattr(service, "_run_round_preprocessing", preprocess)
    service.resume("analysis-test")
    service._run_job("analysis-test", Event())
    assert starts == ["analysis-test", "analysis-test"]
    assert all(key == first.round_key for _, key in events)
    assert repository.list_rounds("analysis-test")[1].status == "ready"


def test_failed_worker_start_leaves_repair_queue_resumable(pipeline, monkeypatch):
    service, repository, artifacts, _, _, _ = pipeline
    first = repository.list_rounds("analysis-test")[0]
    repository.update_round(first.model_copy(update={"status": "alignment_pending"}))
    repository.update_state("analysis-test", status="paused", updated_at="2026-10-13T00:00:00Z")
    monkeypatch.setattr(service._runner, "start", lambda _: False)
    with pytest.raises(AnalysisError, match="背景工作"):
        service.auto_repair("analysis-test")
    assert repository.get("analysis-test").status == "paused"
    with StepJournal(artifacts.root) as journal:
        assert journal.get("control", "auto_repair")["round_keys"] == [first.round_key]
