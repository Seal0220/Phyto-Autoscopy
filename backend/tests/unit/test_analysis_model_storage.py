from __future__ import annotations

import json
import sqlite3
from threading import Event

import pytest

from app.analysis.artifacts import AnalysisArtifacts
from app.database.connection import Database
from app.database.schema import initialize_schema
from app.models.analysis_models import AnalysisRound, RoundModelResult, TipLandmark
from app.repositories.analysis_repository import AnalysisRepository
from app.services import analysis_service
from test_analysis_checkpoint_resume import _service


@pytest.fixture
def storage(tmp_path):
    database = Database(tmp_path / "analysis.sqlite3")
    service, state = _service(tmp_path)
    try:
        initialize_schema(database)
        repository = AnalysisRepository(database)
        artifacts = AnalysisArtifacts.create(tmp_path / "outputs")
        run = state["run"].model_copy(update={
            "record_id": None, "output_path": str(artifacts.root),
        })
        repository.create(run)
        rounds = [
            AnalysisRound(
                analysis_id=run.analysis_id, round_key=f"record:mode-1:round.{number}",
                record_id="record", mode_id="mode-1", round_id=f"round.{number}", status="failed",
            )
            for number in (89, 90)
        ]
        repository.replace_rounds_and_views(run.analysis_id, rounds, [])
        service.repository = repository
        service._require_run = repository.get
        service._artifacts = lambda _: artifacts
        service.error_reporter = None
        yield service, repository, database, rounds
    finally:
        service._runner.close()
        database.close()


def _model(round_item, model_id):
    return RoundModelResult(
        analysis_id=round_item.analysis_id, round_key=round_item.round_key,
        model_id=model_id, backend="gsplat_3dgs", backend_version="test", status="failed",
        failure_reason="previous attempt",
    )


def test_new_model_id_updates_same_round_without_changing_links_or_manual_tip(storage):
    _, repository, database, rounds = storage
    round_item = rounds[0]
    legacy = _model(round_item, "analysis-test:mode-1:round.89:model")
    other = _model(rounds[1], "analysis-test:mode-1:round.90:model")
    repository.upsert_round_model(legacy)
    repository.upsert_round_model(other)
    tip = TipLandmark(
        analysis_id=round_item.analysis_id, round_key=round_item.round_key,
        tip_id=f"{round_item.round_key}:tip", confidence=1, valid=True,
        source="manual", detection_type="manual", manually_corrected=True,
        x_mm=1, y_mm=2, z_mm=3,
    )
    repository.upsert_tip_landmark(tip)
    linked_round = round_item.model_copy(update={
        "model_result_id": legacy.model_id, "tip_landmark_id": tip.tip_id,
    })
    repository.update_round(linked_round)
    completed = legacy.model_copy(update={
        "model_id": f"{round_item.analysis_id}:{round_item.round_key}:model",
        "status": "completed", "training_iterations": 30000,
        "model_path": "rounds/mode-1/round.89/model/gaussians.ply", "failure_reason": None,
    })

    for _ in range(2):
        saved = repository.upsert_round_model(completed)
        assert saved == completed.model_copy(update={"model_id": legacy.model_id})
    assert {model.round_key: model for model in repository.list_round_models("analysis-test")} == {
        round_item.round_key: saved, rounds[1].round_key: other,
    }
    row = database.fetchone(
        "SELECT model_id, payload_json FROM analysis_round_models WHERE round_key=?",
        (round_item.round_key,),
    )
    assert row["model_id"] == json.loads(row["payload_json"])["model_id"] == legacy.model_id
    assert repository.list_rounds("analysis-test")[0] == linked_round
    assert repository.list_tip_landmarks("analysis-test") == [tip]
    assert completed.model_id != legacy.model_id  # The caller's input is not mutated.


def test_model_id_collision_between_different_rounds_does_not_overwrite(storage):
    _, repository, database, rounds = storage
    original = _model(rounds[0], "same-id")
    repository.upsert_round_model(original)
    with pytest.raises(sqlite3.IntegrityError):
        repository.upsert_round_model(_model(rounds[1], original.model_id))
    assert repository.list_round_models("analysis-test") == [original]
    assert database.connection.in_transaction is False
    repository.update_state(
        "analysis-test", updated_at=repository.get("analysis-test").updated_at,
        status="failed", last_error="collision",
    )
    assert repository.get("analysis-test").last_error == "collision"


def test_failed_database_write_reports_failed_state_instead_of_staying_processing(storage, monkeypatch):
    service, repository, database, _ = storage
    database.execute("CREATE TABLE duplicate_test (id INTEGER PRIMARY KEY)")
    database.execute("INSERT INTO duplicate_test VALUES (1)")
    run = repository.get("analysis-test")
    service._set_state(run, stage="building_reference_model", progress=.26)

    def fail_write(run, event):
        database.execute("INSERT INTO duplicate_test VALUES (1)")

    monkeypatch.setattr(service, "_run_round_pipeline", fail_write)
    service._run_job(run.analysis_id, Event())

    assert database.connection.in_transaction is False
    failed = repository.get(run.analysis_id)
    assert failed.status == "failed"
    assert "UNIQUE constraint failed" in failed.last_error
    progress = service.get_progress(run.analysis_id)
    assert progress.status == "failed" and progress.last_error == failed.last_error
    written = json.loads(
        (service._artifacts(failed).root / "progress.json").read_text(encoding="utf-8"),
    )
    assert written["status"] == "failed" and written["last_error"] == failed.last_error


def test_completed_reference_context_republishes_legacy_model_without_retraining(tmp_path, monkeypatch):
    from test_immutable_reference import _worker
    from test_model_reference import _reference_service_fixture

    service, state, reference, views, manifest = _reference_service_fixture(tmp_path)
    database = Database(tmp_path / "analysis.sqlite3")
    calls = []
    monkeypatch.setattr(analysis_service, "run_reconstruction_worker", _worker(reference, calls))
    key = views[0].round_key
    try:
        registration = service._prepare_model_reference(
            state["run"], views, manifest, Event(), round_key=key,
        )
        model = state["models"][key]
        path = tmp_path / model.model_path
        original = path.read_bytes(), path.stat().st_mtime_ns
        initialize_schema(database)
        repository = AnalysisRepository(database)
        run = state["run"].model_copy(update={"record_id": None})
        repository.create(run)
        round_item = AnalysisRound(
            analysis_id=run.analysis_id, round_key=key, record_id="record",
            mode_id="mode", round_id="round.01", status="failed",
            model_result_id="analysis-test:mode:round.01:model",
        )
        repository.replace_rounds_and_views(run.analysis_id, [round_item], views)
        repository.upsert_round_model(_model(round_item, round_item.model_result_id))
        service.repository = repository
        written_models = []
        service._artifacts(run).write_round_model_result = written_models.append

        def no_worker(*args, **kwargs):
            pytest.fail("Completed model and registration should be reused without a worker")

        monkeypatch.setattr(analysis_service, "run_reconstruction_worker", no_worker)
        restored = service._prepare_model_reference(run, views, manifest, Event(), round_key=key)

        assert {key: restored[key] for key in registration} == registration
        saved = repository.list_round_models(run.analysis_id)
        assert len(saved) == 1 and saved[0].status == "completed"
        assert saved[0].model_id == round_item.model_result_id
        assert saved[0].model_path == model.model_path
        assert written_models == saved
        assert (path.read_bytes(), path.stat().st_mtime_ns) == original
    finally:
        service._runner.close()
        database.close()
