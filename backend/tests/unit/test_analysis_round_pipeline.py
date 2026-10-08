from __future__ import annotations

import hashlib
import json
from threading import Event
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.analysis.artifacts import AnalysisArtifacts
from app.analysis.checkpoints import StepJournal
from app.analysis.export.json_export import write_json_atomic
from app.analysis.intrinsics.undistortion_pipeline import undistort_analysis_views
from app.analysis.rounds.paths import round_artifact_directory
from app.database.connection import Database
from app.database.schema import initialize_schema
from app.models.analysis_models import AnalysisRound, AnalysisView, CameraPoseResult, TipCorrectionRequest, TipLandmark
from app.repositories.analysis_repository import AnalysisRepository
from app.services import analysis_service
from app.api.analysis_routes import router
from app.core.state import get_context
from test_analysis_checkpoint_resume import _service


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    service, state = _service(tmp_path)
    database = Database(tmp_path / "analysis.sqlite3")
    initialize_schema(database)
    repository = AnalysisRepository(database)
    artifacts = AnalysisArtifacts.create(tmp_path / "outputs")
    events = []
    snapshots = {}
    views, rounds, sources = [], [], []
    for index in (1, 2):
        key = f"record:mode:round.{index:02d}"
        rounds.append(AnalysisRound(analysis_id="analysis-test", round_key=key, record_id="record",
                                   mode_id="mode", round_id=f"round.{index:02d}", status="ready",
                                   started_at=f"2026-10-07T00:00:{index * 10:02d}+00:00"))
        for camera in ("top", "side", "rotating"):
            path = tmp_path / f"{index}-{camera}.png"
            image = np.full((24, 32, 3), 80 + index, np.uint8)
            cv2.imencode(".png", image)[1].tofile(path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            view = AnalysisView(analysis_id="analysis-test", round_key=key, view_id=f"{index}-{camera}",
                                capture_id=len(views), camera_id=camera, timestamp=rounds[-1].started_at,
                                relative_path=path.name, absolute_path=str(path), image_width=32, image_height=24,
                                image_sha256=digest, selected_for_reconstruction=True)
            views.append(view)
            stat = path.stat()
            sources.append({"absolute_path": str(path), "size_bytes": stat.st_size,
                            "modified_ns": stat.st_mtime_ns, "sha256": digest})
            snapshots[camera] = {"camera_id": camera, "intrinsics_version": "test", "camera_model": "opencv",
                                 "analysis_image_width": 32, "analysis_image_height": 24,
                                 "adapted_camera_matrix": [[24, 0, 16], [0, 24, 12], [0, 0, 1]],
                                 "undistorted_camera_matrix": [[24, 0, 16], [0, 24, 12], [0, 0, 1]],
                                 "distortion_coefficients": [0, 0, 0, 0, 0]}
    run = state["run"].model_copy(update={"method_name": "rotating", "record_id": None, "output_path": str(artifacts.root),
        "intrinsics_snapshot": snapshots, "round_count": 2,
        "parameters": {"source_manifest": sources, "reconstruction": {"backend": "gsplat_3dgs", "quality": "high"},
                       "background": {}, "outputs": {}, "tip_analysis": {}, "manual_review_required": False}})
    repository.create(run)
    repository.replace_rounds_and_views(run.analysis_id, rounds, views)
    service.repository = repository
    service._require_run = repository.get
    service._artifacts = lambda _: artifacts
    service._write_processing_preview = lambda *args, **kwargs: None
    service._reconstruction_backends = SimpleNamespace(check=lambda _: {"available": True, "backend_version": "test"})
    service._record_failure = lambda *args, **kwargs: pytest.fail(str(args[1]))

    def preprocess(run, event, *, round_key):
        events.append(("preprocess", round_key))
        current_views = repository.list_views(run.analysis_id, round_key)
        manifest = []
        poses = []
        for view in current_views:
            image = round_artifact_directory(artifacts.root, round_key) / "undistortion" / f"{view.view_id}.tiff"
            mask = image.with_suffix(".png")
            image.parent.mkdir(parents=True, exist_ok=True)
            cv2.imencode(".tiff", np.full((24, 32, 3), 80, np.uint8))[1].tofile(image)
            cv2.imencode(".png", np.full((24, 32), 255, np.uint8))[1].tofile(mask)
            manifest.append({"view_id": view.view_id, "round_key": round_key, "camera_id": view.camera_id,
                             "undistorted_path": str(image.relative_to(artifacts.root)),
                             "valid_pixel_mask_path": str(mask.relative_to(artifacts.root))})
            poses.append(CameraPoseResult(analysis_id=run.analysis_id, round_key=round_key, view_id=view.view_id,
                                          camera_id=view.camera_id, valid=True, pose_source="motor_prior",
                                          rotation_matrix=np.eye(3).tolist(), translation_vector_mm=[0, 0, 100]))
        write_json_atomic(artifacts.undistortion_manifest_path(round_key), {"views": manifest})
        repository.replace_camera_poses(run.analysis_id, poses, round_key=round_key)
        item = next(item for item in repository.list_rounds(run.analysis_id) if item.round_key == round_key)
        status = "ready_tip_only" if item.round_id == "round.00" else "preprocessed"
        repository.update_round(item.model_copy(update={"status": status}))
        return service._set_state(run, stage="saving_camera_poses", progress=.32)

    def worker(job, root, event, *, progress_callback):
        events.append(("model", job["round_key"]))
        assert {item["camera_id"] for item in job["selected_views"]} == {"top", "side", "rotating"}
        progress_callback("reconstructing_round_model", .5, None)
        path = root / "model" / "gaussians.ply"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test model")
        return {"gaussian_model_path": str(path), "source_view_ids": [item["view_id"] for item in job["selected_views"]],
                "training_iterations": 30000, "model_quality": {}, "refined_camera_poses": []}

    def tip(**kwargs):
        item = kwargs["round_item"]
        events.append(("tip", item.round_key))
        assert {view.camera_id for view in kwargs["views"]} == {"top", "side", "rotating"}
        if item.round_id == "round.02":
            previous = [landmark for landmark in repository.list_tip_landmarks(item.analysis_id) if landmark.valid]
            assert kwargs["previous_landmark"] == (previous[-1] if previous else None)
        landmark = TipLandmark(analysis_id=item.analysis_id, round_key=item.round_key, tip_id=f"{item.round_key}:tip",
                               record_id=item.record_id, mode_id=item.mode_id, round_id=item.round_id,
                               timestamp=item.started_at, x_mm=float(item.round_id.split(".")[-1]), y_mm=0, z_mm=100,
                               confidence=.9, valid=True, source="multiview_triangulation", detection_type="measured")
        artifacts.write_tip_landmark(landmark)
        return SimpleNamespace(landmark=landmark, model_result=None, observations=(), warnings=())

    monkeypatch.setattr(service, "_run_round_preprocessing", preprocess)
    monkeypatch.setattr(analysis_service, "run_reconstruction_worker", worker)
    monkeypatch.setattr(analysis_service, "analyze_round_tip", tip)
    try:
        yield service, repository, artifacts, events, worker, tip
    finally:
        service._runner.close()
        database.close()


def test_round_finishes_model_tip_and_global_chart_before_next_round(pipeline, monkeypatch):
    service, repository, artifacts, events, _, _ = pipeline
    published = []
    original = AnalysisArtifacts.write_tip_trajectory

    def publish(self, points, quality, **kwargs):
        events.append(("chart", len(points)))
        published.append(tuple(point.round_id for point in points))
        original(self, points, quality, **kwargs)

    monkeypatch.setattr(AnalysisArtifacts, "write_tip_trajectory", publish)
    service._run_job("analysis-test", Event())
    keys = [item.round_key for item in repository.list_rounds("analysis-test")]
    assert events[:8] == [("preprocess", keys[0]), ("model", keys[0]), ("tip", keys[0]), ("chart", 1),
                          ("preprocess", keys[1]), ("model", keys[1]), ("tip", keys[1]), ("chart", 2)]
    assert published == [("round.01",), ("round.01", "round.02"), ("round.01", "round.02")]
    assert len(repository.list_round_models("analysis-test")) == len(repository.list_tip_landmarks("analysis-test")) == 2
    assert len(repository.list_camera_poses("analysis-test")) == 6
    assert repository.get("analysis-test").status == "completed"
    assert (artifacts.root / "trajectory/tip_marker_trajectory.csv").is_file()
    assert service.get_progress("analysis-test").progress == 1


def test_bad_round_records_missing_tip_and_continues_other_rounds(pipeline, monkeypatch):
    service, repository, artifacts, events, _, tip = pipeline

    def fail_first(**kwargs):
        if kwargs["round_item"].round_id == "round.01":
            raise ValueError("no reliable tip")
        return tip(**kwargs)

    monkeypatch.setattr(analysis_service, "analyze_round_tip", fail_first)
    service._run_job("analysis-test", Event())
    rounds = repository.list_rounds("analysis-test")
    assert [item.status for item in rounds] == ["tip_invalid", "tip_completed"]
    assert len(repository.list_round_models("analysis-test")) == 2
    run = repository.get("analysis-test")
    assert run.status == "partially_completed" and run.progress == 1
    assert run.manual_review_completed is False
    assert [point.valid for point in repository.list_tip_trajectory("analysis-test")] == [False, True]
    missing = json.loads((round_artifact_directory(artifacts.root, rounds[0].round_key) / "tip/tip_marker.json").read_text(encoding="utf-8"))
    assert missing["valid"] is False and missing["x_mm"] is None


@pytest.mark.parametrize("legacy_checkpoint", [False, True])
def test_resume_repairs_old_tip_processing_errors_without_rebuilding_models(
    pipeline, monkeypatch, legacy_checkpoint,
):
    service, repository, artifacts, events, _, tip = pipeline
    monkeypatch.setattr(service, "_log", analysis_service.AnalysisService._log.__get__(service))

    def fail_first(**kwargs):
        if kwargs["round_item"].round_id == "round.01":
            raise TypeError("Object of type int64 is not JSON serializable")
        return tip(**kwargs)

    monkeypatch.setattr(analysis_service, "analyze_round_tip", fail_first)
    service._run_job("analysis-test", Event())
    key = repository.list_rounds("analysis-test")[0].round_key
    model_times = {model.model_path: (artifacts.root / model.model_path).stat().st_mtime_ns
                   for model in repository.list_round_models("analysis-test")}
    assert "TypeError: Object of type int64 is not JSON serializable" in artifacts.log_path.read_text(encoding="utf-8")
    with StepJournal(artifacts.root) as journal:
        failed_step = journal.get("triangulating_tip_marker", key)
        assert failed_step["processing_error"] is True
        if legacy_checkpoint:
            failed_step.pop("tip_analysis_version")
            failed_step.pop("processing_error")
        else:
            failed_step["tip_analysis_version"] = analysis_service.TIP_ANALYSIS_VERSION - 1
        journal.save("triangulating_tip_marker", key, "", failed_step)
    events.clear()
    monkeypatch.setattr(analysis_service, "analyze_round_tip", tip)
    repository.update_state("analysis-test", status="processing", updated_at="2026-10-08T00:00:00Z")

    service._run_job("analysis-test", Event())

    assert events == [("tip", key)]
    assert repository.get("analysis-test").status == "completed"
    assert all(point.valid for point in repository.list_tip_trajectory("analysis-test"))
    assert all((artifacts.root / path).stat().st_mtime_ns == timestamp for path, timestamp in model_times.items())
    with StepJournal(artifacts.root) as journal:
        repaired = journal.get("triangulating_tip_marker", key)
        assert repaired["tip_analysis_version"] == analysis_service.TIP_ANALYSIS_VERSION
        assert repaired["processing_error"] is False
    events.clear()
    repository.update_state("analysis-test", status="processing", updated_at="2026-10-08T00:01:00Z")
    service._run_job("analysis-test", Event())
    assert events == []


def test_resume_keeps_a_real_quality_rejection_instead_of_repeating_tip_detection(pipeline, monkeypatch):
    service, repository, artifacts, events, _, tip = pipeline

    def uncertain_tip(**kwargs):
        result = tip(**kwargs)
        landmark = result.landmark.model_copy(update={
            "valid": False, "confidence": .4, "detection_type": "invalid",
            "failure_reason": "尖端標記信心未通過檢查。",
        })
        artifacts.write_tip_landmark(landmark)
        return SimpleNamespace(**{**vars(result), "landmark": landmark})

    monkeypatch.setattr(analysis_service, "analyze_round_tip", uncertain_tip)
    service._run_job("analysis-test", Event())
    with StepJournal(artifacts.root) as journal:
        for item in repository.list_rounds("analysis-test"):
            rejected = journal.get("triangulating_tip_marker", item.round_key)
            assert rejected["processing_error"] is False
    events.clear()
    repository.update_state("analysis-test", status="processing", updated_at="2026-10-08T00:00:00Z")
    service._run_job("analysis-test", Event())
    assert events == []
    assert repository.get("analysis-test").status == "partially_completed"
    assert all(not point.valid for point in repository.list_tip_trajectory("analysis-test"))


@pytest.mark.parametrize("outdated_field", ["tip_candidate_version", "tip_analysis_version"])
def test_tip_upgrade_refreshes_old_confirmed_tips_without_rebuilding_models(pipeline, outdated_field):
    service, repository, artifacts, events, _, _ = pipeline
    service._run_job("analysis-test", Event())
    key = repository.list_rounds("analysis-test")[0].round_key
    model_times = {model.model_path: (artifacts.root / model.model_path).stat().st_mtime_ns
                   for model in repository.list_round_models("analysis-test")}
    with StepJournal(artifacts.root) as journal:
        outdated = journal.get("triangulating_tip_marker", key)
        assert outdated["valid"] is True
        outdated.pop(outdated_field)
        journal.save("triangulating_tip_marker", key, "", outdated)
    events.clear()
    repository.update_state("analysis-test", status="processing", updated_at="2026-10-08T00:00:00Z")

    service._run_job("analysis-test", Event())

    assert events == [("tip", key)]
    assert repository.get("analysis-test").status == "completed"
    assert all((artifacts.root / path).stat().st_mtime_ns == timestamp for path, timestamp in model_times.items())
    with StepJournal(artifacts.root) as journal:
        assert journal.get("triangulating_tip_marker", key)["tip_candidate_version"] == analysis_service.TIP_CANDIDATE_VERSION


@pytest.mark.parametrize("all_missing", [False, True])
def test_legacy_review_settings_never_block_completed_rounds(pipeline, monkeypatch, all_missing):
    service, repository, artifacts, events, _, tip = pipeline
    run = repository.get("analysis-test")
    repository.update_parameters("analysis-test", {
        **run.parameters, "manual_review_required": True,
        "tip_analysis": {"wait_for_low_confidence_review": True},
    }, run.updated_at)

    def detect(**kwargs):
        if all_missing:
            events.append(("tip", kwargs["round_item"].round_key))
            raise ValueError("no reliable tip")
        return tip(**kwargs)

    monkeypatch.setattr(analysis_service, "analyze_round_tip", detect)
    service._run_job("analysis-test", Event())
    run = repository.get("analysis-test")
    assert run.status == ("partially_completed" if all_missing else "completed")
    assert run.stage == "completed" and run.progress == 1 and run.last_error is None
    assert service.get_progress("analysis-test").status == run.status
    assert [kind for kind, _ in events] == ["preprocess", "model", "tip"] * 2
    assert len(repository.list_round_models("analysis-test")) == 2
    for model in repository.list_round_models("analysis-test"):
        assert (artifacts.root / model.model_path).is_file()
    trajectory = repository.list_tip_trajectory("analysis-test")
    assert len(trajectory) == 2
    if all_missing:
        assert all(not point.valid and point.x_mm is None for point in trajectory)
        assert run.trajectory_status == "unavailable" and run.tip_marker_count == 0


def test_manual_tip_backfill_updates_chart_without_rerunning_models_and_survives_resume(pipeline, monkeypatch):
    service, repository, artifacts, events, _, _ = pipeline

    def no_tip(**kwargs):
        raise ValueError("no reliable tip")

    monkeypatch.setattr(analysis_service, "analyze_round_tip", no_tip)
    service._run_job("analysis-test", Event())
    before = events.copy()
    model_times = {model.model_path: (artifacts.root / model.model_path).stat().st_mtime_ns
                   for model in repository.list_round_models("analysis-test")}
    first, second = repository.list_rounds("analysis-test")
    one = service.save_tip_correction("analysis-test", TipCorrectionRequest(
        round_key=first.round_key, corrected_point_mm=[1, 2, 100], reason="補正第一輪芽尖",
    ), actor_id="test-operator")
    assert one.automatic_tip.valid is False
    points = repository.list_tip_trajectory("analysis-test")
    assert points[0].valid and points[0].manually_corrected and points[0].x_mm == 1
    assert points[1].valid is False
    assert repository.get("analysis-test").status == "partially_completed"
    service.save_tip_correction("analysis-test", TipCorrectionRequest(
        round_key=second.round_key, corrected_point_mm=[3, 2, 101], reason="補正第二輪芽尖",
    ), actor_id="test-operator")
    assert service.get_progress("analysis-test").status == "completed"
    assert repository.get("analysis-test").tip_marker_count == 2
    assert len(repository.list_tip_corrections("analysis-test")) == 2
    assert events == before
    assert all((artifacts.root / path).stat().st_mtime_ns == timestamp for path, timestamp in model_times.items())
    repository.update_state("analysis-test", status="processing", updated_at="2026-10-08T00:00:00+00:00")
    service._run_job("analysis-test", Event())
    assert events == before
    assert [(point.x_mm, point.manually_corrected) for point in repository.list_tip_trajectory("analysis-test")] == [(1, True), (3, True)]
    assert repository.get("analysis-test").status == "completed"
    service.delete_tip_correction("analysis-test", one.correction_id)
    assert service.get_progress("analysis-test").status == "partially_completed"
    assert repository.list_tip_trajectory("analysis-test")[0].valid is False
    assert events == before


def test_explicit_review_can_keep_all_tip_gaps_without_rebuilding_models(pipeline, monkeypatch):
    service, repository, _, events, _, _ = pipeline

    def no_tip(**kwargs):
        raise ValueError("no reliable tip")

    monkeypatch.setattr(analysis_service, "analyze_round_tip", no_tip)
    service._run_job("analysis-test", Event())
    before = events.copy()
    result = service.reconstruct("analysis-test", manual_review_completed=True)
    assert result.status == "partially_completed" and result.progress == 1
    assert result.manual_review_completed is True
    assert all(not point.valid for point in repository.list_tip_trajectory("analysis-test"))
    assert events == before


def test_continuous_snapshot_uses_full_round_world_reference_without_global_preprocessing(pipeline):
    service, repository, _, events, _, _ = pipeline
    first, second = repository.list_rounds("analysis-test")
    repository.database.execute(
        "UPDATE analysis_rounds SET round_id='round.00' WHERE analysis_id=? AND round_key=?",
        ("analysis-test", first.round_key),
    )
    repository.update_round(first.model_copy(update={"round_id": "round.00", "status": "ready_tip_only"}))
    service._run_job("analysis-test", Event())
    assert events == [
        ("preprocess", second.round_key), ("model", second.round_key), ("tip", second.round_key),
        ("preprocess", first.round_key), ("tip", first.round_key),
    ]
    assert [point.round_id for point in repository.list_tip_trajectory("analysis-test")] == ["round.00", "round.02"]
    assert repository.get("analysis-test").status == "completed"


def test_missing_completed_model_rebuilds_only_that_round(pipeline):
    service, repository, artifacts, events, _, _ = pipeline
    service._run_job("analysis-test", Event())
    models = repository.list_round_models("analysis-test")
    (artifacts.root / models[0].model_path).unlink()
    events.clear()
    repository.update_state("analysis-test", status="processing", updated_at="2026-10-07T00:01:00+00:00")
    service._run_job("analysis-test", Event())
    assert events == [("model", models[0].round_key), ("tip", models[0].round_key)]
    assert len(repository.list_camera_poses("analysis-test")) == 6


def test_pause_mid_second_model_retains_first_tip_and_resumes_current_round(pipeline, monkeypatch):
    service, repository, artifacts, events, worker, _ = pipeline
    entered = Event()

    def pause_worker(job, root, event, **kwargs):
        if job["round_key"].endswith("02") and not entered.is_set():
            kwargs["progress_callback"]("reconstructing_round_model", .5, None)
            entered.set()
            assert event.wait(5)
            service._check_cancel(event)
        return worker(job, root, event, **kwargs)

    monkeypatch.setattr(analysis_service, "run_reconstruction_worker", pause_worker)
    service._runner.start("analysis-test")
    assert entered.wait(5)
    first = repository.list_tip_landmarks("analysis-test")
    assert [item.round_id for item in first] == ["round.01"]
    assert [item.round_id for item in repository.list_tip_trajectory("analysis-test")] == ["round.01"]
    service.pause("analysis-test")
    assert service._runner.wait_until_idle("analysis-test", timeout=5)
    progress = service.get_progress("analysis-test")
    assert progress.status == "paused" and progress.current_round == 2
    assert progress.progress == pytest.approx(.98 * 1.5 / 2)
    service.resume("analysis-test")
    assert service._runner.wait_until_idle("analysis-test", timeout=5)
    assert repository.get("analysis-test").status == "completed"
    assert [kind for kind, key in events if key == first[0].round_key] == ["preprocess", "model", "tip"]
    assert sum(kind == "preprocess" for kind, _ in events) == 2


def test_round_pose_replacement_keeps_other_round_and_rejects_cross_round_payload(pipeline):
    _, repository, _, _, _, _ = pipeline
    for item in repository.list_rounds("analysis-test"):
        poses = [CameraPoseResult(analysis_id="analysis-test", round_key=item.round_key, view_id=view.view_id,
                                  camera_id=view.camera_id, valid=True, pose_source="motor_prior")
                 for view in repository.list_views("analysis-test", item.round_key)]
        repository.replace_camera_poses("analysis-test", poses, round_key=item.round_key)
    before = repository.list_camera_poses("analysis-test")
    key = before[0].round_key
    updated = [item.model_copy(update={"translation_vector_mm": [1, 2, 3]}) for item in before if item.round_key == key]
    repository.replace_camera_poses("analysis-test", updated, round_key=key)
    assert [item.model_dump() for item in repository.list_camera_poses("analysis-test") if item.round_key != key] == [item.model_dump() for item in before if item.round_key != key]
    with pytest.raises(ValueError):
        repository.replace_camera_poses("analysis-test", before, round_key=key)
    assert len(repository.list_camera_poses("analysis-test")) == 6


def test_resume_repairs_missing_preprocessed_image_only_in_unfinished_round(pipeline, monkeypatch):
    from app.core.exceptions import AnalysisPausedError

    service, repository, artifacts, events, worker, _ = pipeline
    paused = False

    def pause_once(job, root, event, **kwargs):
        nonlocal paused
        if job["round_key"].endswith("02") and not paused:
            paused = True
            raise AnalysisPausedError("pause before model")
        return worker(job, root, event, **kwargs)

    monkeypatch.setattr(analysis_service, "run_reconstruction_worker", pause_once)
    event = Event()
    event.pause_requested = True
    service._run_job("analysis-test", event)
    key = repository.list_rounds("analysis-test")[1].round_key
    missing = artifacts.root / artifacts.read_undistortion_manifest(key)[0]["undistorted_path"]
    missing.unlink()
    events.clear()
    repository.update_state("analysis-test", status="processing", updated_at="2026-10-07T00:01:00+00:00")
    service._run_job("analysis-test", Event())
    assert events == [("preprocess", key), ("model", key), ("tip", key)]
    assert missing.is_file()
    assert repository.get("analysis-test").status == "completed"


def test_round_manifests_merge_legacy_and_never_overwrite_another_round(pipeline):
    service, repository, artifacts, _, _, _ = pipeline
    rounds = repository.list_rounds("analysis-test")
    views = repository.list_views("analysis-test")
    snapshots = repository.get("analysis-test").intrinsics_snapshot
    first = [view for view in views if view.round_key == rounds[0].round_key]
    second = [view for view in views if view.round_key == rounds[1].round_key]
    undistort_analysis_views(first, snapshots, artifacts.root, maximum_workers=2,
                            manifest_path=artifacts.undistortion_manifest_path(rounds[0].round_key))
    path = artifacts.undistortion_manifest_path(rounds[0].round_key)
    before = path.stat().st_mtime_ns
    assert not artifacts.undistortion_manifest_path(rounds[1].round_key).exists()
    assert not (artifacts.root / "undistortion_manifest.json").exists()
    undistort_analysis_views(second, snapshots, artifacts.root, maximum_workers=2,
                            manifest_path=artifacts.undistortion_manifest_path(rounds[1].round_key))
    assert path.stat().st_mtime_ns == before
    assert len(artifacts.read_undistortion_manifest(rounds[0].round_key)) == 3
    assert len(artifacts.read_undistortion_manifest()) == 6
    write_json_atomic(artifacts.root / "undistortion_manifest.json", {"views": [
        *artifacts.read_undistortion_manifest(),
        {"view_id": "legacy", "round_key": "record:mode:round.99"},
    ]})
    assert len(artifacts.read_undistortion_manifest()) == 7
    assert artifacts.read_undistortion_manifest("record:mode:round.99")[0]["view_id"] == "legacy"


def test_live_result_summary_does_not_parse_frozen_inputs(pipeline):
    service, repository, _, _, _, _ = pipeline
    repository.database.execute("UPDATE analysis_runs SET parameters_json='invalid JSON', camera_pose_results_json='invalid JSON' WHERE analysis_id='analysis-test'")
    summary = service.get_result_summary("analysis-test")
    assert summary.parameters == {} and summary.camera_pose_results == []
    assert summary.round_count == 2
    assert service.list_rounds("analysis-test")
    assert service.list_round_models("analysis-test") == []
    assert service.list_tip_landmarks("analysis-test") == []
    assert service.list_tip_trajectory("analysis-test") == []
    assert service.get_tip_trajectory_quality("analysis-test") == {}


def test_result_api_publishes_each_finished_round_while_analysis_is_running(pipeline, monkeypatch):
    service, repository, _, _, worker, _ = pipeline
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_context] = lambda: SimpleNamespace(analysis_service=service)
    with TestClient(app) as client:
        def inspect_second_round(job, root, event, **kwargs):
            if job["round_key"].endswith("02"):
                summary = client.get("/api/analysis/analysis-test?summary=true")
                assert summary.status_code == 200
                assert summary.json()["parameters"] == {}
                assert summary.json()["status"] == "processing"
                assert summary.json()["tip_marker_count"] == 1
                assert summary.json()["completed_round_count"] == 1
                models = client.get("/api/analysis/analysis-test/round-models")
                assert models.status_code == 200
                assert sum(model["status"] == "completed" for model in models.json()) == 1
                points = client.get("/api/analysis/analysis-test/tip-trajectory")
                assert points.status_code == 200
                assert [point["round_id"] for point in points.json()] == ["round.01"]
                assert client.get("/api/analysis/analysis-test/tip-trajectory-quality").status_code == 200
            return worker(job, root, event, **kwargs)

        monkeypatch.setattr(analysis_service, "run_reconstruction_worker", inspect_second_round)
        service._run_job("analysis-test", Event())
        assert repository.get("analysis-test").status == "completed"
