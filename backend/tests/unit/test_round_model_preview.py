from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.analysis.pose_alignment.model_review import model_preview_reference, prepare_reference_point_preview
from app.api.analysis_routes import router
from app.core.exceptions import AnalysisError
from app.core.state import get_context
from app.models.analysis_models import CameraPoseResult, RoundModelResult
from app.services.analysis_service import AnalysisService


def _model(root, name):
    return prepare_reference_point_preview({"points": [
        {"id": i, "xyz": [i * .1, i % 2 * .2, i * .03], "rgb": [20, 180, 30]}
        for i in range(12)
    ]}, root / name)


def test_round_preview_frames_exact_gaussians_and_keeps_the_trained_camera(tmp_path):
    model = _model(tmp_path, "round-1")
    path = Path(model["gaussian_model_path"])
    rotation = np.array([[1., 0., 0.], [0., 0., -1.], [0., 1., 0.]])
    position = np.array([.5, -3., .2])
    pose = np.eye(4)
    pose[:3, :3], pose[:3, 3] = rotation, -rotation @ position
    before = {file: (file.stat().st_mtime_ns, file.read_bytes()) for file in tmp_path.rglob("*") if file.is_file()}

    reference = model_preview_reference(path, tmp_path, pose)

    assert reference["gaussian_path"] == "round-1/alignment_points.ply"
    assert reference["gaussian_count"] == 12
    assert reference["gaussian_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert reference["gaussian_point_offset"] == 0 and reference["points"] == []
    np.testing.assert_allclose(reference["initial_camera"]["position"], position)
    np.testing.assert_allclose(reference["initial_camera"]["up"], -rotation[1])
    assert np.isfinite(reference["center"]).all() and reference["radius"] > 0
    assert model_preview_reference(path, tmp_path, pose) == reference
    assert {file: (file.stat().st_mtime_ns, file.read_bytes()) for file in tmp_path.rglob("*") if file.is_file()} == before
    with pytest.raises(ValueError):
        model_preview_reference(path, tmp_path / "other-round")


def test_round_preview_without_poses_uses_finite_framing_and_new_model_signature(tmp_path):
    path = Path(_model(tmp_path, "round-1")["gaussian_model_path"])
    reference = model_preview_reference(path, tmp_path)
    assert np.isfinite(reference["initial_camera"]["position"]).all()
    assert np.linalg.norm(np.asarray(reference["initial_camera"]["position"]) - reference["center"]) > reference["radius"]
    _model(tmp_path, "round-2")
    other = model_preview_reference(tmp_path / "round-2/alignment_points.ply", tmp_path)
    assert other["signature"] != reference["signature"]


@pytest.fixture
def preview_service(tmp_path):
    full = Path(_model(tmp_path, "full")["gaussian_model_path"]).relative_to(tmp_path).as_posix()
    foreground = Path(_model(tmp_path, "plant-and-pot")["gaussian_model_path"]).relative_to(tmp_path).as_posix()
    model = RoundModelResult(analysis_id="analysis-test", round_key="record:mode:round.02", model_id="model-2",
                            backend="gsplat_3dgs", backend_version="test", status="completed",
                            model_path=full, plant_model_path=foreground)
    camera = CameraPoseResult(analysis_id=model.analysis_id, round_key=model.round_key, view_id="rotating",
                             camera_id="rotating", valid=True, pose_source="motor_prior",
                             rotation_matrix=np.eye(3).tolist(), translation_vector_mm=[0, 3, -1])
    service = AnalysisService.__new__(AnalysisService)
    service._require_image_context = lambda _: SimpleNamespace()
    service._artifacts = lambda _: SimpleNamespace(root=tmp_path)
    requested = []

    def poses(analysis_id, round_key):
        requested.append((analysis_id, round_key))
        return [camera]

    service.repository = SimpleNamespace(list_round_models=lambda _: [model], list_camera_poses=poses)
    return service, model, requested


def test_preview_api_selects_this_round_foreground_model_without_running_analysis(preview_service):
    service, model, requested = preview_service
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[get_context] = lambda: SimpleNamespace(analysis_service=service)
    with TestClient(application) as client:
        response = client.get(f"/api/analysis/{model.analysis_id}/round-model-preview", params={"round_key": model.round_key})
    assert response.status_code == 200
    assert response.json()["gaussian_path"] == model.plant_model_path
    assert response.json()["initial_camera"]["position"] == [0, -3, 1]
    assert requested == [(model.analysis_id, model.round_key)]
    with pytest.raises(AnalysisError, match="尚未完成"):
        service.get_round_model_preview(model.analysis_id, "record:mode:round.01")


def test_preview_rejects_incomplete_models_and_paths_outside_the_analysis(preview_service):
    service, model, _ = preview_service
    model.status = "training"
    with pytest.raises(AnalysisError, match="尚未完成"):
        service.get_round_model_preview(model.analysis_id, model.round_key)
    model.status = "completed"
    model.plant_model_path = "../another-analysis/plant.ply"
    with pytest.raises(AnalysisError, match="超出允許範圍"):
        service.get_round_model_preview(model.analysis_id, model.round_key)
    model.plant_model_path = None
    model.model_path = None
    with pytest.raises(AnalysisError, match="尚未輸出"):
        service.get_round_model_preview(model.analysis_id, model.round_key)


@pytest.mark.parametrize("foreground_only,foreground_kind", [(True, "plant_and_pot"), (False, "plant_and_pot"), (True, "plant")])
def test_preview_keeps_pot_in_the_trained_foreground_scene(preview_service, foreground_only, foreground_kind):
    service, model, _ = preview_service
    model.model_quality = {"foreground_only": foreground_only, "foreground_kind": foreground_kind}
    reference = service.get_round_model_preview(model.analysis_id, model.round_key)
    expected = model.model_path if foreground_only and foreground_kind == "plant_and_pot" else model.plant_model_path
    assert reference["gaussian_path"] == expected
