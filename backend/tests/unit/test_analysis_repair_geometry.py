from copy import deepcopy
import json
from threading import Event

import numpy as np
import pytest

from app.analysis.checkpoints import StepJournal, step_signature
from app.analysis.export.json_export import write_json_atomic
from app.analysis.reconstruction.model_repair import repair_directory
from app.analysis.rounds.paths import round_artifact_directory
from app.core.exceptions import AnalysisPausedError, AnalysisReviewRequiredError
from app.services import analysis_service
from test_analysis_round_pipeline import pipeline  # noqa: F401
from test_immutable_reference import _worker
from test_model_reference import _reference_service_fixture


def _manual_geometry(pipeline, monkeypatch):
    service, repository, artifacts, events, _, tip = pipeline

    def missing_tip(**kwargs):
        raise ValueError("尖端失敗")

    monkeypatch.setattr(analysis_service, "analyze_round_tip", missing_tip)
    service._run_job("analysis-test", Event())
    monkeypatch.setattr(analysis_service, "analyze_round_tip", tip)
    first = repository.list_rounds("analysis-test")[0]
    poses = repository.list_camera_poses("analysis-test", first.round_key)
    matrices = {}
    for pose in poses:
        if pose.camera_id in {"top", "side"}:
            matrix = np.eye(4)
            matrix[:3, :3] = pose.rotation_matrix
            matrix[:3, 3] = pose.translation_vector_mm
            matrices[pose.camera_id] = matrix.tolist()
    registration = {"poses": matrices, "quality": {"estimation_source": "manual_model_reference"}, "reference_poses": {}}
    directory = round_artifact_directory(artifacts.root, first.round_key)
    review_path = directory / "pose_debug/stereo/manual_review.json"
    write_json_atomic(review_path, {"accepted": True, "reviewed_by": "operator", "request": {"correspondences": ["kept"]}})
    service._store_model_registration(repository.get("analysis-test"), registration, round_key=first.round_key)
    with StepJournal(artifacts.root) as journal:
        journal.save("estimating_camera_poses", first.round_key, "existing-camera-version", {"manual_pose": True})
    alignment_root = directory / "pose_debug/model_reference/fixed_alignment"
    with StepJournal(alignment_root) as journal:
        journal.save("reference_sfm", "model", "human-aligned", {"kept": True})
    pending = repair_directory(artifacts.root, first.round_key) / "request.json"
    write_json_atomic(pending, {"status": "pending"})
    protected_files = [review_path, directory / "pose_debug/model_reference/registration.json", pending,
                       *(artifacts.root / model.model_path for model in repository.list_round_models("analysis-test"))]
    protected = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in protected_files}
    events.clear()
    monkeypatch.setattr(service._runner, "start", lambda _: True)
    monkeypatch.setattr(service, "_run_round_preprocessing", lambda *args, **kwargs: pytest.fail("accepted cameras must not be re-aligned"))
    monkeypatch.setattr(analysis_service, "run_reconstruction_worker", lambda *args, **kwargs: pytest.fail("existing models must not be retrained"))
    monkeypatch.setattr(service, "_repair_requested_round_model", lambda *args: pytest.fail("a tip retry must not consume queued model repairs"))
    return service, repository, artifacts, events, first, poses, protected, alignment_root


@pytest.mark.parametrize("action", ["auto_repair", "retry_round"])
def test_manual_camera_steps_points_and_model_files_survive_tip_retry(pipeline, monkeypatch, action):
    service, repository, artifacts, events, first, poses, protected, alignment_root = _manual_geometry(pipeline, monkeypatch)
    with StepJournal(artifacts.root) as journal:
        before = journal.connection.execute("SELECT stage,signature,payload,updated_at FROM steps WHERE item=? AND stage IN (?,?,?,?)",
            (first.round_key, "aligning_model_cameras", "estimating_camera_poses", "round_preprocessing", "round_model")).fetchall()
    getattr(service, action)("analysis-test", *([first.round_key] if action == "retry_round" else []))
    service._run_job("analysis-test", Event())
    assert events and all(kind == "tip" for kind, _ in events)
    assert repository.list_camera_poses("analysis-test", first.round_key) == poses
    for path, content in protected.items():
        assert (path.read_bytes(), path.stat().st_mtime_ns) == content
    with StepJournal(alignment_root) as journal:
        assert journal.get("reference_sfm", "model", "human-aligned")["kept"]
    with StepJournal(artifacts.root) as journal:
        after = journal.connection.execute("SELECT stage,signature,payload,updated_at FROM steps WHERE item=? AND stage IN (?,?,?,?)",
            (first.round_key, "aligning_model_cameras", "estimating_camera_poses", "round_preprocessing", "round_model")).fetchall()
    assert after == before


@pytest.mark.parametrize("missing_image", [False, True])
def test_missing_image_or_old_preprocessing_version_does_not_reopen_manual_alignment(pipeline, monkeypatch, missing_image):
    service, repository, artifacts, events, first, poses, protected, _ = _manual_geometry(pipeline, monkeypatch)
    with StepJournal(artifacts.root) as journal:
        journal.invalidate(first.round_key, ("round_preprocessing",))
    if missing_image:
        manifest = artifacts.read_undistortion_manifest(first.round_key)
        (artifacts.root / manifest[0]["undistorted_path"]).unlink()
    service.retry_round("analysis-test", first.round_key)
    service._run_job("analysis-test", Event())
    assert events == [("tip", first.round_key)]
    assert repository.list_camera_poses("analysis-test", first.round_key) == poses
    for path, content in protected.items():
        assert (path.read_bytes(), path.stat().st_mtime_ns) == content


@pytest.mark.parametrize("archive", [False, True])
def test_deleted_manual_checkpoint_is_restored_without_sfm_or_pnp(tmp_path, monkeypatch, archive):
    service, state, reference, views, manifest = _reference_service_fixture(tmp_path)
    key = views[0].round_key
    calls = []
    monkeypatch.setattr(analysis_service, "run_reconstruction_worker", _worker(reference, calls))
    try:
        registration = service._prepare_model_reference(state["run"], views, manifest, Event(), round_key=key)
        registration["quality"]["estimation_source"] = "manual_model_reference"
        service._store_model_registration(state["run"], registration, round_key=key)
        directory = round_artifact_directory(tmp_path, key)
        review_path = directory / "pose_debug/stereo/manual_review.json"
        registration_path = directory / "pose_debug/model_reference/registration.json"
        payload = {"accepted": True, "reviewed_by": "operator", "request": {"correspondences": ["original points"]}}
        write_json_atomic(review_path, payload)
        if archive:
            write_json_atomic(review_path.with_name("accepted_alignment.json"), {
                **payload, "registration": registration, "intrinsics_signature": step_signature(state["run"].intrinsics_snapshot),
            })
            automatic = deepcopy(registration)
            automatic["quality"]["estimation_source"] = "automatic"
            write_json_atomic(registration_path, automatic)
        original_review = review_path.read_bytes(), review_path.stat().st_mtime_ns
        model_path = tmp_path / state["models"][key].model_path
        original_model = model_path.read_bytes(), model_path.stat().st_mtime_ns
        with StepJournal(tmp_path) as journal:
            journal.invalidate(key, ("aligning_model_cameras",))
        monkeypatch.setattr(analysis_service, "run_reconstruction_worker", lambda *args, **kwargs: pytest.fail("must reuse manual pose"))
        monkeypatch.setattr(analysis_service, "model_camera_pose", lambda *args, **kwargs: pytest.fail("must not rerun manual PnP"))
        restored = service._prepare_model_reference(state["run"], views, manifest, Event(), round_key=key)
        assert restored["poses"] == registration["poses"]
        assert restored["quality"]["model_to_world"] == registration["quality"]["model_to_world"]
        assert (review_path.read_bytes(), review_path.stat().st_mtime_ns) == original_review
        assert (model_path.read_bytes(), model_path.stat().st_mtime_ns) == original_model
        with StepJournal(tmp_path) as journal:
            assert journal.get("aligning_model_cameras", key)["quality"]["estimation_source"] == "manual_model_reference"
    finally:
        service._runner.close()


def test_metric_refresh_uses_this_rounds_manual_rig_instead_of_another_rounds_rig(pipeline, monkeypatch):
    from app.analysis.tip import metric_measurement
    service, repository, artifacts, _, first, poses, _, _ = _manual_geometry(pipeline, monkeypatch)
    run = repository.get("analysis-test")
    shared = {"poses": {camera: np.eye(4).tolist() for camera in ("top", "side")}, "quality": {"shared": True}}
    service._save_step(run, "aligning_model_cameras", "registration", service._stereo_pose_signature(run), shared)
    landmark = repository.list_tip_landmarks("analysis-test")[0].model_copy(update={"image_tip_confirmed": True})
    received = []

    def measure(landmark, views, measured_poses, intrinsics, **kwargs):
        received.extend(measured_poses)
        return landmark

    monkeypatch.setattr(metric_measurement, "measure_image_tip", measure)
    with StepJournal(artifacts.root) as journal:
        service._refresh_published_round_measurement(run, first, repository.list_views("analysis-test", first.round_key), landmark, journal)
    for original in poses:
        if original.camera_id in {"top", "side"}:
            actual = next(item for item in received if item.view_id == original.view_id)
            assert actual.rotation_matrix == original.rotation_matrix
            assert actual.translation_vector_mm == original.translation_vector_mm


def test_paused_tip_retry_resumes_without_invalidating_manual_geometry(pipeline, monkeypatch):
    service, repository, artifacts, events, first, poses, protected, _ = _manual_geometry(pipeline, monkeypatch)
    original_tip = analysis_service.analyze_round_tip

    def pause(**kwargs):
        raise AnalysisPausedError("暫停尖端修正")

    monkeypatch.setattr(analysis_service, "analyze_round_tip", pause)
    service.retry_round("analysis-test", first.round_key)
    event = Event()
    event.pause_requested = True
    service._run_job("analysis-test", event)
    with StepJournal(artifacts.root) as journal:
        assert journal.get("control", "auto_repair")["preserve_geometry_keys"] == [first.round_key]
    monkeypatch.setattr(analysis_service, "analyze_round_tip", original_tip)
    service.resume("analysis-test")
    service._run_job("analysis-test", Event())
    assert events == [("tip", first.round_key)]
    assert repository.list_camera_poses("analysis-test", first.round_key) == poses
    for path, before in protected.items():
        assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_rebuilding_a_failed_model_keeps_accepted_camera_poses(pipeline, monkeypatch):
    service, repository, artifacts, events, first, poses, _, _ = _manual_geometry(pipeline, monkeypatch)
    model = repository.list_round_models("analysis-test")[0]
    repository.upsert_round_model(model.model_copy(update={"status": "failed"}))
    worker = pipeline[4]

    def rebuild(job, root, event, **kwargs):
        assert job["parameters"]["use_constrained_bundle_adjustment"] is False
        assert job["camera_poses"] == [pose.model_dump(mode="json") for pose in poses]
        return {**worker(job, root, event, **kwargs), "refined_camera_poses": [{"should_not_apply": True}]}

    monkeypatch.setattr(analysis_service, "run_reconstruction_worker", rebuild)
    monkeypatch.setattr(service, "_apply_bundle_adjusted_camera_poses", lambda *args, **kwargs: pytest.fail("accepted poses must remain fixed"))
    service.retry_round("analysis-test", first.round_key)
    service._run_job("analysis-test", Event())
    assert events == [("model", first.round_key), ("tip", first.round_key)]
    assert repository.list_camera_poses("analysis-test", first.round_key) == poses
