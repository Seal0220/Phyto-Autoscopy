from __future__ import annotations

from threading import Event
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from app.analysis.tip.temporal_tracker import TipTrackingFrame, track_tip_sequence, validate_tip_seed
from app.analysis.tip.feature_correspondences import plant_feature_correspondences
from app.models.analysis_models import TipCorrectionObservation, TipCorrectionRequest
from app.services import analysis_service
from app.analysis.intrinsics.undistortion_pipeline import undistort_analysis_views
from app.core.exceptions import AnalysisReviewRequiredError
from test_analysis_round_pipeline import pipeline  # noqa: F401


def _plant():
    image = np.full((120, 160, 3), 15, np.uint8)
    cv2.line(image, (70, 96), (70, 48), (40, 180, 60), 3)
    cv2.ellipse(image, (70, 62), (20, 9), 0, 0, 360, (40, 180, 60), -1)
    patch = np.random.default_rng(8).integers(0, 80, (11, 11, 3), dtype=np.uint8)
    patch[:, :, 1] += 120
    image[43:54, 65:76] = patch
    return image


def _frame(tmp_path, name, image, camera="top"):
    image_path, valid_path = tmp_path / f"{name}.png", tmp_path / f"{name}.valid.png"
    cv2.imencode(".png", image)[1].tofile(image_path)
    cv2.imencode(".png", np.full(image.shape[:2], 255, np.uint8))[1].tofile(valid_path)
    return TipTrackingFrame(name, camera, image_path, valid_path)


def test_seeded_tracking_retains_subpixel_identity_and_recovers_short_occlusion(tmp_path):
    image = _plant()
    shifted = cv2.warpAffine(image, np.float32([[1, 0, 4.25], [0, 1, -2.5]]), (160, 120))
    seed = _frame(tmp_path, "seed", image)
    occluded = _frame(tmp_path, "arm", np.full_like(image, 15))
    target = _frame(tmp_path, "target", shifted)
    candidate, quality = track_tip_sequence(seed, (70., 48.), [occluded, target])
    assert candidate.source == "shoot_apex"
    np.testing.assert_allclose([candidate.x_px, candidate.y_px], [74.25, 45.5], atol=.5)
    assert quality["skipped_occluded_frames"] == 1
    assert quality["maximum_return_error_px"] < 2


def test_lamp_seed_and_occluded_target_never_become_confirmed_shoot(tmp_path):
    image = _plant()
    cv2.circle(image, (130, 24), 12, (255, 255, 255), -1)
    seed = _frame(tmp_path, "seed", image)
    with pytest.raises(ValueError, match="植物組織"):
        validate_tip_seed(seed, (130., 24.))
    candidate, quality = track_tip_sequence(seed, (70., 48.), [_frame(tmp_path, "lost", np.full_like(image, 15))])
    assert candidate is None
    assert quality["reason"] == "appearance_ambiguous_or_lost"


def test_ambiguous_duplicate_shoot_and_different_camera_are_rejected(tmp_path):
    image = _plant()
    target = np.full_like(image, 15)
    target[33:64, 30:61] = image[33:64, 55:86]
    target[33:64, 90:121] = image[33:64, 55:86]
    seed = _frame(tmp_path, "seed", image)
    candidate, _ = track_tip_sequence(seed, (70., 48.), [_frame(tmp_path, "ambiguous", target)])
    assert candidate is None
    with pytest.raises(ValueError, match="同一個"):
        track_tip_sequence(seed, (70., 48.), [_frame(tmp_path, "wrong-camera", image, "side")])


def _seeded_fixture(pipeline):
    service, repository, artifacts, events, _, _ = pipeline
    run = repository.get("analysis-test")
    run.parameters["tip_analysis"]["tracking_mode"] = "manual_seeded"
    # The same repository/runner fixture now exercises the production seeded path.
    repository.update_parameters(run.analysis_id, run.parameters, run.updated_at)
    views = repository.list_views(run.analysis_id)
    for view in views:
        image = _plant()
        if view.round_key.endswith("02"):
            image = cv2.warpAffine(image, np.float32([[1, 0, 3], [0, 1, -2]]), (160, 120))
        cv2.imencode(".png", image)[1].tofile(view.absolute_path)
        view.image_width, view.image_height = 160, 120
        import hashlib
        from pathlib import Path
        view.image_sha256 = hashlib.sha256(Path(view.absolute_path).read_bytes()).hexdigest()
    repository.replace_rounds_and_views(run.analysis_id, repository.list_rounds(run.analysis_id), views)
    snapshots = {camera: {**snapshot, "analysis_image_width": 160, "analysis_image_height": 120,
                         "adapted_camera_matrix": [[130, 0, 80], [0, 130, 60], [0, 0, 1]],
                         "undistorted_camera_matrix": [[130, 0, 80], [0, 130, 60], [0, 0, 1]]}
                 for camera, snapshot in run.intrinsics_snapshot.items()}
    # Fixture source identities changed intentionally before creating test work.
    run.parameters["source_manifest"] = []
    repository.database.execute("UPDATE analysis_runs SET intrinsics_snapshot_json=?, parameters_json=? WHERE analysis_id=?",
        (__import__("json").dumps(snapshots), __import__("json").dumps(run.parameters), run.analysis_id))
    return service, repository, artifacts, events


def test_first_round_pauses_before_models_and_good_image_seed_resumes_without_metric_pose(pipeline, monkeypatch):
    service, repository, artifacts, events = _seeded_fixture(pipeline)
    service._run_job("analysis-test", Event())
    run = repository.get("analysis-test")
    assert (run.status, run.stage) == ("paused", "waiting_for_tip_seed")
    assert events == []
    assert repository.list_round_models(run.analysis_id) == []
    assert not artifacts.undistortion_manifest_path("record:mode:round.02").exists()
    starts = []
    monkeypatch.setattr(service._runner, "start", lambda key: starts.append(key) or True)
    first = repository.list_rounds(run.analysis_id)[0]
    views = repository.list_views(run.analysis_id, first.round_key)
    request = TipCorrectionRequest(round_key=first.round_key, reason="identify shoot",
        observations=[TipCorrectionObservation(view_id=view.view_id, x_px=70, y_px=48)
                      for view in views if view.camera_id in {"top", "side"}])
    correction = service.save_tip_correction(run.analysis_id, request, "operator")
    assert correction.tracking_seed_confirmed and correction.pending_alignment
    assert correction.corrected_tip.image_tip_confirmed and not correction.corrected_tip.valid
    assert correction.corrected_tip.x_mm is None
    assert starts == [run.analysis_id]
    assert repository.get(run.analysis_id).status == "processing"
    # Picking an auxiliary model point later must not erase the image identity.
    repository.insert_tip_correction(correction.model_copy(update={
        "correction_id": "later-model-pick", "correction_type": "point", "observations": [],
        "model_point_id": 0, "model_signature": "b" * 64,
    }))
    assert service._ensure_initial_tip_seed(run, first, views, Event())
    tracked, _, _ = service._track_fixed_tip(run, first, views, Event())
    assert tracked.image_tip_confirmed
    assert tracked.tracking["seed_id"] == correction.correction_id


def test_features_only_expose_observed_plant_tracks_shared_by_two_cameras(tmp_path):
    image = _plant()
    views, refs, manifest, cameras, images = [], [], [], {}, {}
    for index, camera in enumerate(["side", "rotating"], 1):
        frame = _frame(tmp_path, camera, image, camera)
        views.append(SimpleNamespace(view_id=camera, camera_id=camera))
        refs.append({"view_id": camera, "image_name": camera})
        manifest.append({"view_id": camera, "undistorted_path": frame.image_path.name, "valid_pixel_mask_path": frame.valid_mask_path.name})
        cameras[index] = SimpleNamespace(width=160, height=120)
        images[index] = SimpleNamespace(name=camera, camera_id=index,
            points2D=[SimpleNamespace(point3D_id=1, xy=np.array([70., 48.])),
                      SimpleNamespace(point3D_id=2, xy=np.array([130., 24.]))])
    reconstruction = SimpleNamespace(images=images, cameras=cameras, points3D={
        point_id: SimpleNamespace(error=.4, track=SimpleNamespace(length=lambda: 3)) for point_id in [1, 2]})
    result = plant_feature_correspondences(reconstruction, refs, views, manifest, tmp_path)
    assert [item["feature_id"] for item in result["features"]] == ["1"]
    assert len(result["features"][0]["observations"]) == 2
    assert result["unregistered_view_ids"] == []


def test_unregistered_rounds_track_fixed_images_after_one_seed_without_model_alignment(pipeline, monkeypatch):
    service, repository, artifacts, events = _seeded_fixture(pipeline)
    service._run_job("analysis-test", Event())
    monkeypatch.setattr(service._runner, "start", lambda key: True)
    first = repository.list_rounds("analysis-test")[0]
    views = repository.list_views("analysis-test", first.round_key)
    service.save_tip_correction("analysis-test", TipCorrectionRequest(round_key=first.round_key, reason="shoot seed",
        observations=[TipCorrectionObservation(view_id=view.view_id, x_px=70, y_px=48)
                      for view in views if view.camera_id in {"top", "side"}]), "operator")

    def preprocess(run, event, *, round_key):
        undistort_analysis_views(repository.list_views(run.analysis_id, round_key), run.intrinsics_snapshot,
            artifacts.root, manifest_path=artifacts.undistortion_manifest_path(round_key))
        raise AnalysisReviewRequiredError("no metric cameras")

    monkeypatch.setattr(service, "_run_round_preprocessing", preprocess)
    service._run_job("analysis-test", Event())
    second = repository.list_tip_landmarks("analysis-test")[-1]
    assert second.image_tip_confirmed and not second.valid
    assert second.tracking["seed_id"] == repository.list_tip_corrections("analysis-test")[0].correction_id
    assert {item["view_id"] for item in second.image_observations} == {"2-top", "2-side"}
    for item in second.image_observations:
        np.testing.assert_allclose([item["x_px"], item["y_px"]], [73, 46], atol=.5)
    assert not repository.list_camera_poses("analysis-test")
    assert all(point.x_mm is None for point in repository.list_tip_trajectory("analysis-test"))
    assert events == [], "2D tracking must not invoke training or the unseeded contour detector"
    run = repository.get("analysis-test")
    second_round = repository.list_rounds(run.analysis_id)[1]
    service.save_tip_correction(run.analysis_id, TipCorrectionRequest(
        round_key=second_round.round_key, invalid=True, reason="occluded shoot",
    ), "operator")
    invalid, _, observations = service._track_fixed_tip(
        run, second_round, repository.list_views(run.analysis_id, second_round.round_key), Event(),
    )
    assert not invalid.image_tip_confirmed and not observations
    assert "人工標記為不可見" in invalid.failure_reason
    correction = service.save_tip_correction(run.analysis_id, TipCorrectionRequest(
        round_key=second_round.round_key, reason="reidentify shoot",
        observations=[TipCorrectionObservation(view_id=view_id, x_px=73, y_px=46)
                      for view_id in ["2-top", "2-side"]],
    ), "operator")
    restored, _, _ = service._track_fixed_tip(
        run, second_round, repository.list_views(run.analysis_id, second_round.round_key), Event(),
    )
    assert restored.image_tip_confirmed
    assert restored.tracking["seed_id"] == correction.correction_id
