from __future__ import annotations

import json
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.analysis.checkpoints import StepJournal
from app.analysis.pose_alignment import markerless_pose
from app.api.analysis_routes import router
from app.core.exceptions import AnalysisError, AnalysisReviewRequiredError
from app.core.state import get_context
from app.models.analysis_models import AnalysisView, MarkerlessPoseSettings, StereoPoseReviewRequest
from app.security.auth import Principal, get_request_principal
from test_analysis_checkpoint_resume import _service


def _geometry():
    matrix = np.array([[800., 0, 640], [0, 800, 480], [0, 0, 1]])
    top = np.eye(4)
    top[:3, :3] = np.diag([1., -1., -1.])
    top[:3, 3] = [0, 0, 1000]
    center = np.array([600., 0, 200])
    direction = (np.array([0., 0, 100]) - center)
    direction /= np.linalg.norm(direction)
    right = np.cross(direction, [0, 0, 1])
    right /= np.linalg.norm(right)
    side = np.eye(4)
    side[:3, :3] = [right, np.cross(direction, right), direction]
    side[:3, 3] = -side[:3, :3] @ center
    points = np.random.default_rng(19).uniform([-120, -120, 20], [120, 120, 180], (30, 3))
    def project(pose):
        camera = points @ pose[:3, :3].T + pose[:3, 3]
        pixels = camera @ matrix.T
        return pixels[:, :2] / pixels[:, 2:]
    pairs = [dict(top=dict(x_px=x, y_px=y), side=dict(x_px=a, y_px=b))
             for (x, y), (a, b) in zip(project(top), project(side))]
    settings = MarkerlessPoseSettings(baseline_mm=1000, top_height_mm=1000).model_dump()
    intrinsics = {camera: dict(camera_matrix=matrix.tolist(), width=1280, height=960) for camera in ("top", "side")}
    return pairs, settings, intrinsics, center


@pytest.mark.parametrize("count", [5, 6, 8, 30])
def test_manual_pairing_recovers_measured_pose_without_automatic_features(monkeypatch, count):
    pairs, settings, intrinsics, expected_center = _geometry()
    pairs = pairs[:count]
    reads = []
    def read_image(frame):
        reads.append(frame)
        return np.zeros((960, 1280), np.uint8)
    monkeypatch.setattr(markerless_pose, "_gray", read_image)
    monkeypatch.setattr(markerless_pose, "_features", lambda *args: pytest.fail("manual review extracted automatic features"))
    diagnostics = {}
    poses, quality = markerless_pose.estimate_manual_stereo_pose(
        {}, {}, intrinsics, settings, pairs, diagnostics=diagnostics,
    )
    actual_center = np.linalg.inv(np.asarray(poses["side"]))[:3, 3]
    assert np.linalg.norm(actual_center - expected_center) < .1
    assert quality["stereo_inliers"] == count
    assert quality["stereo_reprojection_rmse_px"] < .1
    assert quality["estimation_source"] == "manual_correspondences"
    assert diagnostics["validated_stage"] == "reprojection"
    assert diagnostics["inlier_indices"] == list(range(count))
    assert diagnostics["reprojection_inliers"] == quality["stereo_inliers"]
    assert len(reads) == 2


def test_five_pairs_with_multiple_valid_poses_require_another_point(monkeypatch):
    pairs, settings, intrinsics, _ = _geometry()
    monkeypatch.setattr(markerless_pose, "_gray", lambda _: np.zeros((960, 1280), np.uint8))
    settings["maximum_side_elevation_deg"] = 90
    diagnostics = {}
    with pytest.raises(ValueError, match="多個相機姿態解"):
        markerless_pose.estimate_manual_stereo_pose(
            {}, {}, intrinsics, settings, pairs[:5], diagnostics=diagnostics,
        )
    assert diagnostics["ambiguous"] is True
    assert diagnostics["essential_candidate_count"] > 1


def test_four_pairs_cannot_estimate_unknown_stereo_pose(monkeypatch):
    pairs, settings, intrinsics, _ = _geometry()
    monkeypatch.setattr(markerless_pose, "_gray", lambda _: np.zeros((960, 1280), np.uint8))
    monkeypatch.setattr(markerless_pose.cv2, "findEssentialMat", lambda *args, **kwargs: pytest.fail("four-point pose was attempted"))
    with pytest.raises(ValueError, match="至少 5 組"):
        markerless_pose.estimate_manual_stereo_pose({}, {}, intrinsics, settings, pairs[:4])


def test_failed_pose_reports_actual_count_and_original_pair_indices(monkeypatch):
    pairs, settings, intrinsics, _ = _geometry()
    pairs = pairs[:9]
    monkeypatch.setattr(markerless_pose, "_gray", lambda _: np.zeros((960, 1280), np.uint8))
    recover_pose = markerless_pose.cv2.recoverPose
    selected = [0, 2, 4, 8]

    def recover_with_fewer_inliers(*args, **kwargs):
        _, rotation, translation, mask = recover_pose(*args, **kwargs)
        mask[:] = 0
        mask[selected] = 1
        return len(selected), rotation, translation, mask

    monkeypatch.setattr(markerless_pose.cv2, "recoverPose", recover_with_fewer_inliers)
    diagnostics = {}
    with pytest.raises(ValueError, match="本次內點 4/9 組"):
        markerless_pose.estimate_manual_stereo_pose(
            {}, {}, intrinsics, settings, pairs, diagnostics=diagnostics,
        )
    assert diagnostics["validated_stage"] == "geometric"
    assert diagnostics["epipolar_inliers"] == 9
    assert diagnostics["geometric_inliers"] == 4
    assert diagnostics["inlier_indices"] == selected


def test_manual_pairing_still_rejects_invalid_geometry(monkeypatch):
    pairs, settings, intrinsics, _ = _geometry()
    monkeypatch.setattr(markerless_pose, "_gray", lambda _: np.zeros((960, 1280), np.uint8))
    invalid = [{**pair, "side": pairs[(i + 7) % len(pairs)]["side"]} for i, pair in enumerate(pairs)]
    with pytest.raises(ValueError, match="人工配對未通過幾何檢查"):
        markerless_pose.estimate_manual_stereo_pose({}, {}, intrinsics, settings, invalid)


def test_legacy_review_request_outside_round_pipeline_remains_reviewable(tmp_path):
    from app.analysis.artifacts import AnalysisArtifacts

    service, state = _service(tmp_path)
    artifacts = AnalysisArtifacts.create(tmp_path)
    service._artifacts = lambda _: artifacts
    def needs_review(*args, **kwargs):
        raise AnalysisReviewRequiredError("共同特徵配對不足")
    service._run_round_pipeline = needs_review
    service._run_round_models = lambda *args: pytest.fail("models started before pose review")
    service._record_failure = lambda *args, **kwargs: pytest.fail("review was marked failed")
    try:
        service._run_job("analysis-test", Event())
        assert state["run"].status == "needs_review"
        assert state["run"].stage == "waiting_for_stereo_review"
        assert state["run"].last_error is None
        assert json.loads((tmp_path / "pose_debug/stereo/manual_review.json").read_text(encoding="utf-8"))["accepted"] is False
        with StepJournal(tmp_path) as journal:
            assert journal.get("phase", "preprocessing") is None
    finally:
        service._runner.close()


def test_existing_failed_stereo_run_becomes_reviewable_on_restart(tmp_path):
    service, state = _service(tmp_path, "failed")
    state["run"] = state["run"].model_copy(update={
        "stage": "estimating_stereo_pose", "last_error": "無法建立無標記雙鏡頭姿態：共同特徵配對不足。",
    })
    service.repository.list = lambda: [state["run"]]
    try:
        service.recover_interrupted_runs()
        assert (state["run"].status, state["run"].stage) == ("needs_review", "waiting_for_stereo_review")
        with pytest.raises(AnalysisError, match="人工雙鏡頭配對"):
            service.resume("analysis-test")
        with pytest.raises(AnalysisError, match="人工配對"):
            service.reconstruct("analysis-test", manual_review_completed=False)
    finally:
        service._runner.close()


def _review_service(tmp_path, monkeypatch):
    service, state = _service(tmp_path, "needs_review")
    service._runner.close()
    starts = []
    service._runner = SimpleNamespace(wait_until_idle=lambda _: True, start=lambda name: starts.append(name) or True)
    pairs, settings, intrinsics, _ = _geometry()
    state["run"] = state["run"].model_copy(update={
        "stage": "waiting_for_stereo_review", "parameters": {"pose_strategy": settings},
        "intrinsics_snapshot": {camera: {"undistorted_camera_matrix": item["camera_matrix"]} for camera, item in intrinsics.items()},
    })
    views = [AnalysisView(
        analysis_id="analysis-test", round_key="record:mode:round.01", view_id=f"view-{camera}",
        capture_id=i, camera_id=camera, snapshot_id="one", timestamp="2026-10-05T00:00:00+00:00",
        relative_path=f"{camera}.png", absolute_path=str(tmp_path / f"{camera}.png"),
        image_width=1280, image_height=960, image_sha256="test",
    ) for i, camera in enumerate(("top", "side"))]
    service.repository.get_view = lambda _, view_id: next((view for view in views if view.view_id == view_id), None)
    service.repository.get_image_context = lambda _: state["run"]
    service._write_processing_preview(state["run"], views)
    for camera in ("top", "side"):
        (tmp_path / f"{camera}.tiff").write_bytes(b"lossless fixture")
    service.get_view_image_path = lambda _, view_id: tmp_path / f"{view_id.removeprefix('view-')}.jpg"
    monkeypatch.setattr(markerless_pose, "_gray", lambda _: np.zeros((960, 1280), np.uint8))
    request = StereoPoseReviewRequest(top_view_id="view-top", side_view_id="view-side", correspondences=pairs)
    return service, state, request, starts


def test_manual_review_saves_verified_rig_and_continues_from_checkpoint(tmp_path, monkeypatch):
    service, state, request, starts = _review_service(tmp_path, monkeypatch)
    result = service.submit_stereo_review("analysis-test", request, "reviewer")
    assert result.status == "processing" and starts == ["analysis-test"]
    with StepJournal(tmp_path) as journal:
        saved = journal.get("estimating_stereo_pose", "rig", service._stereo_pose_signature(result))
        assert saved["quality"]["estimation_source"] == "manual_correspondences"
        assert saved["quality"]["stereo_inliers"] >= 8
    data = json.loads((tmp_path / "pose_debug/stereo/manual_review.json").read_text(encoding="utf-8"))
    assert data["accepted"] and data["reviewed_by"] == "reviewer"
    assert len(data["request"]["correspondences"]) == 30
    assert data["validation"]["validated_stage"] == "reprojection"
    assert data["validation"]["inlier_indices"] == list(range(30))


def test_failed_manual_geometry_keeps_editable_draft_without_starting_job(tmp_path, monkeypatch):
    service, state, request, starts = _review_service(tmp_path, monkeypatch)
    invalid = request.model_copy(update={"correspondences": [
        pair.model_copy(update={"side": request.correspondences[(i + 7) % 30].side})
        for i, pair in enumerate(request.correspondences)
    ]})
    with pytest.raises(AnalysisError, match="人工配對未通過"):
        service.submit_stereo_review("analysis-test", invalid, "reviewer")
    assert not starts and state["run"].status == "needs_review"
    data = service.get_stereo_review("analysis-test")
    assert len(data["draft"]["correspondences"]) == 30
    assert "人工配對未通過" in data["reason"]
    assert data["validation"]["validated_stage"] in {"epipolar", "geometric", "reprojection"}
    assert len(data["validation"]["inlier_indices"]) <= 30
    assert "本次內點" in data["reason"]
    saved = json.loads((tmp_path / "pose_debug/stereo/manual_review.json").read_text(encoding="utf-8"))
    assert data["validation"] == saved["validation"]


def test_manual_request_rejects_missing_duplicate_nonfinite_points():
    pairs, *_ = _geometry()
    for invalid in [pairs[:4], [pairs[0]] * 5, [{**pairs[0], "top": {"x_px": float("nan"), "y_px": 3}}, *pairs[1:5]]]:
        with pytest.raises(ValidationError):
            StereoPoseReviewRequest(top_view_id="a", side_view_id="b", correspondences=invalid)


@pytest.mark.parametrize("invalid", ["camera", "snapshot", "bounds"])
def test_review_rejects_wrong_images_and_outside_points_before_saving(tmp_path, monkeypatch, invalid):
    service, state, request, starts = _review_service(tmp_path, monkeypatch)
    get_view = service.repository.get_view
    if invalid == "camera":
        request = request.model_copy(update={"side_view_id": "view-top"})
    elif invalid == "snapshot":
        service.repository.get_view = lambda analysis_id, view_id: get_view(analysis_id, view_id).model_copy(
            update={"snapshot_id": "another" if view_id == "view-side" else "one"},
        )
    else:
        first = request.correspondences[0]
        first = first.model_copy(update={"top": first.top.model_copy(update={"x_px": 1280})})
        request = request.model_copy(update={"correspondences": [first, *request.correspondences[1:]]})
    with pytest.raises(AnalysisError):
        service.submit_stereo_review("analysis-test", request, "reviewer")
    assert not starts and state["run"].status == "needs_review"
    assert not (tmp_path / "pose_debug/stereo/manual_review.json").exists()
    with StepJournal(tmp_path) as journal:
        assert journal.get("estimating_stereo_pose", "rig") is None


def test_review_api_validates_pairs_and_preserves_authenticated_reviewer(tmp_path, monkeypatch):
    service, _, request, starts = _review_service(tmp_path, monkeypatch)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_context] = lambda: SimpleNamespace(analysis_service=service)
    app.dependency_overrides[get_request_principal] = lambda: Principal("verified-reviewer", "operator", frozenset({"*"}))
    with TestClient(app) as client:
        response = client.get("/api/analysis/analysis-test/stereo-review")
        assert response.status_code == 200
        assert response.json()["minimum_pairs"] == 5
        assert [view["camera_id"] for view in response.json()["views"]] == ["top", "side"]
        invalid = request.model_dump(mode="json")
        invalid["correspondences"] = invalid["correspondences"][:4]
        assert client.post("/api/analysis/analysis-test/stereo-review", json=invalid).status_code == 422
        assert not starts
        response = client.post("/api/analysis/analysis-test/stereo-review", json=request.model_dump(mode="json"))
        assert response.status_code == 200
        assert response.json()["status"] == "processing"
        assert "input_manifest" not in response.json()["parameters"]
        assert starts == ["analysis-test"]
    saved = json.loads((tmp_path / "pose_debug/stereo/manual_review.json").read_text(encoding="utf-8"))
    assert saved["reviewed_by"] == "verified-reviewer"
