from __future__ import annotations

from threading import Event

import numpy as np
import pytest

from app.core.exceptions import AnalysisError
from app.models.analysis_models import TipCorrectionObservation, TipCorrectionRequest
from app.services import analysis_service
from app.analysis.pose_alignment.model_review import prepare_reference_point_preview, model_preview_reference
from test_analysis_round_pipeline import pipeline  # noqa: F401


def _clicks(repository, key, point=(1., 2., 100.)):
    views = repository.list_views("analysis-test", key)
    poses = repository.list_camera_poses("analysis-test", key)
    matrix = np.asarray([[24, 0, 16], [0, 24, 12], [0, 0, 1]])
    changed, observations = [], []
    for view in views:
        pose = next(p for p in poses if p.view_id == view.view_id)
        center = np.asarray([10., 0., 0.] if view.camera_id == "side" else [0., 0., 0.])
        changed.append(pose.model_copy(update={"rotation_matrix": np.eye(3).tolist(),
            "translation_vector_mm": (-center).tolist()}))
        if view.camera_id in {"top", "side"}:
            pixel = matrix @ (np.asarray(point) - center)
            observations.append(TipCorrectionObservation(view_id=view.view_id,
                x_px=pixel[0] / pixel[2], y_px=pixel[1] / pixel[2]))
    repository.replace_camera_poses("analysis-test", changed, round_key=key)
    return TipCorrectionRequest(round_key=key, reason="人工標記芽尖", observations=observations)


@pytest.mark.parametrize("found", [True, False])
def test_edit_found_or_missing_tip_updates_chart_while_next_model_trains(pipeline, monkeypatch, found):
    service, repository, artifacts, _, worker, original_tip = pipeline
    entered, release = Event(), Event()

    def blocked_worker(job, root, event, **kwargs):
        if job["round_key"].endswith("02"):
            kwargs["progress_callback"]("reconstructing_round_model", .5, None)
            entered.set()
            assert release.wait(10)
        return worker(job, root, event, **kwargs)

    def tip(**kwargs):
        if not found and kwargs["round_item"].round_id == "round.01":
            raise ValueError("missing tip")
        return original_tip(**kwargs)

    monkeypatch.setattr(analysis_service, "run_reconstruction_worker", blocked_worker)
    monkeypatch.setattr(analysis_service, "analyze_round_tip", tip)
    try:
        assert service._runner.start("analysis-test")
        assert entered.wait(5)
        first = repository.list_rounds("analysis-test")[0]
        model = repository.list_round_models("analysis-test")[0]
        path = artifacts.root / model.model_path
        before = path.read_bytes(), path.stat().st_mtime_ns
        progress = service.get_progress("analysis-test")
        correction = service.save_tip_correction("analysis-test", _clicks(repository, first.round_key), "operator")
        assert correction.automatic_tip.valid is found
        assert correction.corrected_tip.valid and not correction.pending_alignment
        current = service.get_progress("analysis-test")
        assert (current.status, current.stage, current.progress, current.current_round) == (
            progress.status, progress.stage, progress.progress, progress.current_round)
        assert current.results_revision
        trajectory = repository.list_tip_trajectory("analysis-test")
        assert len(trajectory) == 1
        np.testing.assert_allclose([trajectory[0].x_mm, trajectory[0].y_mm, trajectory[0].z_mm], [1, 2, 100], atol=1e-6)
        assert trajectory[0].manually_corrected
        modified = service.save_tip_correction("analysis-test", _clicks(repository, first.round_key, (3., 4., 100.)), "operator")
        assert modified.observations[0].x_px != correction.observations[0].x_px
        assert service.get_progress("analysis-test").results_revision != current.results_revision
        release.set()
        assert service._runner.wait_until_idle("analysis-test", timeout=5)
        trajectory = repository.list_tip_trajectory("analysis-test")
        np.testing.assert_allclose([trajectory[0].x_mm, trajectory[0].y_mm, trajectory[0].z_mm], [3, 4, 100], atol=1e-6)
        assert (path.read_bytes(), path.stat().st_mtime_ns) == before
        assert repository.list_tip_corrections("analysis-test")[-1].correction_id == modified.correction_id
    finally:
        release.set()


def test_pending_clicks_resolve_without_camera_review_or_model_work(pipeline):
    service, repository, artifacts, events, _, _ = pipeline
    service._run_job("analysis-test", Event())
    first = repository.list_rounds("analysis-test")[0]
    request = _clicks(repository, first.round_key)
    poses = repository.list_camera_poses("analysis-test", first.round_key)
    repository.replace_camera_poses("analysis-test", [], round_key=first.round_key)
    repository.update_round(first.model_copy(update={"status": "alignment_pending"}))
    model = repository.list_round_models("analysis-test")[0]
    path = artifacts.root / model.model_path
    before = path.read_bytes(), path.stat().st_mtime_ns
    work = events.copy()
    correction = service.save_tip_correction("analysis-test", request, "operator")
    assert correction.pending_alignment and not correction.corrected_tip.valid
    assert correction.corrected_tip.x_mm is None
    assert correction.observations == request.observations
    assert not repository.list_tip_trajectory("analysis-test")[0].valid
    repository.replace_camera_poses("analysis-test", poses, round_key=first.round_key)
    service._refresh_tip_correction_artifacts(repository.get("analysis-test"))
    resolved = repository.list_tip_corrections("analysis-test")[-1]
    assert resolved.correction_id == correction.correction_id
    assert not resolved.pending_alignment and resolved.corrected_tip.valid
    assert resolved.observations == request.observations
    assert repository.list_tip_trajectory("analysis-test")[0].manually_corrected
    assert events == work
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_late_automatic_tip_result_never_overwrites_live_manual_clicks(pipeline, monkeypatch):
    service, repository, _, _, _, original_tip = pipeline
    entered, release = Event(), Event()

    def blocked_tip(**kwargs):
        if kwargs["round_item"].round_id == "round.01":
            entered.set()
            assert release.wait(10)
        return original_tip(**kwargs)

    monkeypatch.setattr(analysis_service, "analyze_round_tip", blocked_tip)
    try:
        service._runner.start("analysis-test")
        assert entered.wait(5)
        first = repository.list_rounds("analysis-test")[0]
        correction = service.save_tip_correction("analysis-test", _clicks(repository, first.round_key, (4., 5., 100.)), "operator")
        assert correction.corrected_tip.valid
        assert correction.automatic_tip.valid is False
        release.set()
        assert service._runner.wait_until_idle("analysis-test", timeout=5)
        measured = repository.list_tip_trajectory("analysis-test")[0]
        assert measured.manually_corrected
        np.testing.assert_allclose([measured.x_mm, measured.y_mm, measured.z_mm], [4, 5, 100], atol=1e-6)
    finally:
        release.set()


@pytest.mark.parametrize("problem", ["outside", "same_camera", "other_snapshot"])
def test_invalid_clicks_rejected_before_pending_save(pipeline, problem):
    service, repository, _, _, _, _ = pipeline
    service._run_job("analysis-test", Event())
    first = repository.list_rounds("analysis-test")[0]
    request = _clicks(repository, first.round_key)
    views = repository.list_views("analysis-test")
    if problem == "outside":
        request.observations[0].x_px = 999
    else:
        changed = next(v for v in views if v.view_id == request.observations[1].view_id)
        same_camera = next(v.camera_id for v in views if v.view_id == request.observations[0].view_id)
        changed = changed.model_copy(update={"camera_id": same_camera} if problem == "same_camera" else {"snapshot_id": "other"})
        repository.replace_rounds_and_views("analysis-test", repository.list_rounds("analysis-test"),
            [changed if v.view_id == changed.view_id else v for v in views])
    repository.replace_camera_poses("analysis-test", [], round_key=first.round_key)
    with pytest.raises(AnalysisError):
        service.save_tip_correction("analysis-test", request, "operator")
    assert repository.list_tip_corrections("analysis-test") == []


def test_model_tip_pick_uses_signed_server_anchor_and_resolves_pending_registration(pipeline, monkeypatch):
    service, repository, artifacts, events, _, _ = pipeline
    service._run_job("analysis-test", Event())
    first = repository.list_rounds("analysis-test")[0]
    _clicks(repository, first.round_key)
    preview = prepare_reference_point_preview({"points": [
        {"id": i, "xyz": xyz, "rgb": [180, 220, 100]}
        for i, xyz in enumerate([[1, 2, 100], [2, 2, 100], [1, 3, 100], [2, 3, 101]])
    ]}, artifacts.root / "tip-pick-test")
    path = artifacts.root / "tip-pick-test/alignment_points.ply"
    reference = model_preview_reference(path, artifacts.root)
    reference["model_quality"] = {"immutable_reference": True}
    reference["model_to_world"] = None
    monkeypatch.setattr(service, "get_round_model_preview", lambda *args: reference)
    before = path.read_bytes(), path.stat().st_mtime_ns
    work = events.copy()
    request = TipCorrectionRequest(round_key=first.round_key, reason="模型芽尖",
        model_point_id=0, model_signature=reference["signature"])
    correction = service.save_tip_correction("analysis-test", request, "operator")
    assert correction.pending_alignment and not correction.corrected_tip.valid
    assert correction.model_point_relative_xyz == [1., 2., 100.]
    assert correction.model_point_id == 0
    reference["model_to_world"] = {"scale": 2., "rotation": np.eye(3).tolist(), "translation": [4., 7., 3.]}
    service._refresh_tip_correction_artifacts(repository.get("analysis-test"))
    resolved = repository.list_tip_corrections("analysis-test")[-1]
    assert resolved.correction_id == correction.correction_id
    assert resolved.model_point_id == 0 and resolved.corrected_tip.valid
    assert not resolved.pending_alignment
    np.testing.assert_allclose([resolved.corrected_tip.x_mm, resolved.corrected_tip.y_mm, resolved.corrected_tip.z_mm], [6., 11., 203.])
    with pytest.raises(AnalysisError, match="模型已變更"):
        service.save_tip_correction("analysis-test", request.model_copy(update={"model_signature": "0" * 64}), "operator")
    with pytest.raises(AnalysisError, match="不存在"):
        service.save_tip_correction("analysis-test", request.model_copy(update={"model_point_id": 99}), "operator")
    modified = service.save_tip_correction("analysis-test", request.model_copy(update={"model_point_id": 2}), "operator")
    assert modified.corrected_tip.y_mm == 13.
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert events == work


def test_model_selection_cannot_mix_coordinates_or_missing_signature():
    from pydantic import ValidationError
    base = {"round_key": "round.01", "reason": "尖端", "model_point_id": 0, "model_signature": "a" * 64}
    for change in ({"corrected_point_mm": [1, 2, 3]}, {"invalid": True}, {"model_signature": None},
                   {"model_point_id": -1}, {"model_signature": "old"}):
        with pytest.raises(ValidationError):
            TipCorrectionRequest(**{**base, **change})
