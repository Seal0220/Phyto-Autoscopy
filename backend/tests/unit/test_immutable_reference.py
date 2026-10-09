from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from threading import Event

import numpy as np
import pytest

from app.analysis.rounds.paths import round_artifact_directory
from app.analysis.pose_alignment.model_review import prepare_reference_point_preview, model_review_reference
from app.core.exceptions import AnalysisPausedError, AnalysisReviewRequiredError
from app.services import analysis_service
from test_model_reference import _reference_service_fixture, _reference_model_result, _rig


def _worker(reference, calls, *, missing_top=False, no_orbit=False, pause=False):
    def worker(job, output, event, **kwargs):
        calls.append((job, output))
        if job.get("kind") == "reference_sfm":
            assert job["refine_geometry"] is False
            assert {view["camera_id"] for view in job["selected_views"]} == {"top", "side", "rotating"}
            result = deepcopy(reference)
            moving_poses = iter(reference["views"])
            result["views"] = []
            for view in job["selected_views"]:
                if view["camera_id"] == "rotating":
                    pose = next(moving_poses)["pose"]
                elif missing_top and view["camera_id"] == "top":
                    continue
                else:
                    pose = _rig()[view["camera_id"]].tolist()
                result["views"].append({**view, "pose": pose})
            result["sparse_path"] = str(output / "sparse")
            if no_orbit:
                result["orbit"] = None
            return result
        assert job["purpose"] == "immutable_round_reference"
        assert job["parameters"]["use_constrained_bundle_adjustment"] is False
        if pause:
            raise AnalysisPausedError("pause initial model")
        return _reference_model_result(job, output)
    return worker


@pytest.mark.parametrize("per_round", [True, False])
def test_one_model_uses_original_sfm_poses_and_survives_measurement_edits(tmp_path, monkeypatch, per_round):
    service, state, reference, views, manifest = _reference_service_fixture(tmp_path)
    calls = []
    monkeypatch.setattr(analysis_service, "run_reconstruction_worker", _worker(reference, calls))
    options = {"round_key": views[0].round_key} if per_round else {}
    try:
        registration = service._prepare_model_reference(state["run"], views, manifest, Event(), **options)
        model = state["models"][views[0].round_key]
        path = tmp_path / model.model_path
        original = path.read_bytes(), path.stat().st_mtime_ns
        assert model.model_quality["immutable_reference"] is True
        assert model.model_quality["training_camera_counts"] == {"top": 1, "side": 1, "rotating": 12}
        assert len(calls) == 2
        for item in calls[1][0]["selected_views"]:
            expected = next(v["pose"] for v in reference["views"] if v["view_id"] == item["view_id"]) if item["camera_id"] == "rotating" else _rig()[item["camera_id"]]
            np.testing.assert_allclose(item["pose"], expected)
        edited = deepcopy(registration)
        edited["quality"]["manual_measurement_change"] = True
        service._store_model_registration(state["run"], edited, **options)
        run = state["run"].model_copy(update={"parameters": {**state["run"].parameters,
            "reconstruction": {"training_iterations": 50000}}})
        second = service._prepare_model_reference(run, views, manifest, Event(), **options)
        assert len(calls) == 2
        assert second["quality"]["manual_measurement_change"] is True
        assert (path.read_bytes(), path.stat().st_mtime_ns) == original
    finally:
        service._runner.close()


def test_reference_training_respects_selected_backend(tmp_path):
    service, state, reference, views, _ = _reference_service_fixture(tmp_path)
    try:
        state["run"].parameters["reconstruction"]["backend"] = "graphdeco_3dgs"
        reference["sparse_path"] = str(tmp_path / "sparse")
        training_views = [{**item, "round_key": views[0].round_key} for item in reference["views"]]
        job = service._reference_model_job(state["run"], reference, training_views, alignment_preview=True)
        assert job["backend"] == "graphdeco_3dgs"
    finally:
        service._runner.close()


@pytest.mark.parametrize("problem", ["missing_top", "no_orbit"])
def test_measurement_failure_keeps_completed_reference_model(tmp_path, monkeypatch, problem):
    service, state, reference, views, manifest = _reference_service_fixture(tmp_path)
    calls = []
    monkeypatch.setattr(analysis_service, "run_reconstruction_worker", _worker(reference, calls, **{problem: True}))
    key = views[0].round_key
    try:
        for _ in range(2):
            with pytest.raises(AnalysisReviewRequiredError):
                service._prepare_model_reference(state["run"], views, manifest, Event(), round_key=key)
        assert len(calls) == 2
        model = state["models"][key]
        assert model.status == "completed"
        assert (tmp_path / model.model_path).is_file()
        assert model.model_quality["unregistered_view_ids"] == (["top"] if problem == "missing_top" else [])
        context = json.loads((round_artifact_directory(tmp_path, key) / "pose_debug/model_reference/context.json").read_text())
        assert model_review_reference(context, tmp_path)["gaussian_path"] == model.model_path
    finally:
        service._runner.close()


def test_pausing_initial_training_never_publishes_an_incomplete_model(tmp_path, monkeypatch):
    service, state, reference, views, manifest = _reference_service_fixture(tmp_path)
    calls = []
    key = views[0].round_key
    monkeypatch.setattr(analysis_service, "run_reconstruction_worker", _worker(reference, calls, pause=True))
    try:
        with pytest.raises(AnalysisPausedError):
            service._prepare_model_reference(state["run"], views, manifest, Event(), round_key=key)
        assert state["models"] == {}
        assert not (round_artifact_directory(tmp_path, key) / "pose_debug/model_reference/context.json").exists()
        monkeypatch.setattr(analysis_service, "run_reconstruction_worker", _worker(reference, calls))
        service._prepare_model_reference(state["run"], views, manifest, Event(), round_key=key)
        assert state["models"][key].status == "completed"
    finally:
        service._runner.close()


@pytest.mark.parametrize("sparse_only", [False, True])
def test_legacy_initial_model_and_draft_are_preserved(tmp_path, monkeypatch, sparse_only):
    service, state, reference, views, manifest = _reference_service_fixture(tmp_path)
    key = views[0].round_key
    root = round_artifact_directory(tmp_path, key) / "pose_debug/model_reference"
    reference["views"] = [{**view.model_dump(mode="json"), **pose} for view, pose in zip(views, reference["views"])]
    reference["sparse_path"] = str(root / "sparse")
    preview = prepare_reference_point_preview(reference, root / "initial") if sparse_only else _reference_model_result({"selected_views": reference["views"]}, root / "initial")
    context_path = root / "context.json"
    context_path.write_text(json.dumps({"reference": reference, "model": preview, "fixed_view_ids": ["top", "side"]}), encoding="utf-8")
    model_path = Path(preview["gaussian_model_path"])
    original = model_path.read_bytes(), model_path.stat().st_mtime_ns
    draft = root / "manual_review.json"
    draft.write_text('{"model_point_id": 101}', encoding="utf-8")
    calls = []
    monkeypatch.setattr(analysis_service, "run_reconstruction_worker", _worker(reference, calls, missing_top=True))
    try:
        with pytest.raises(AnalysisReviewRequiredError):
            service._prepare_model_reference(state["run"], views, manifest, Event(), round_key=key)
        assert len(calls) == (2 if sparse_only else 0)
        assert draft.read_text() == '{"model_point_id": 101}'
        assert (model_path.read_bytes(), model_path.stat().st_mtime_ns) == original
        frozen = json.loads(context_path.read_text())
        assert frozen["reference_model_policy"] == "immutable_per_round_v1"
        assert frozen["model"]["model_quality"].get("representation") != "sfm_points"
    finally:
        service._runner.close()
