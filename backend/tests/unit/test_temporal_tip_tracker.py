from __future__ import annotations

from threading import Event
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from app.analysis.tip.temporal_tracker import TIP_TRACKING_VERSION, TipTrackingFrame, track_tip_sequence, validate_tip_seed
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


def test_unchanged_manual_identity_rejects_a_drifted_but_locally_consistent_template(tmp_path):
    original = _plant()
    changed = original.copy()
    changed[33:64, 55:86] = np.random.default_rng(51).integers(0, 90, (31, 31, 3), dtype=np.uint8)
    changed[33:64, 55:86, 1] += 130
    manual = _frame(tmp_path, "manual", original, "side")
    drifted = _frame(tmp_path, "previous-wrong-tissue", changed, "side")
    target = _frame(tmp_path, "next-wrong-tissue", changed, "side")
    local, _ = track_tip_sequence(drifted, (70., 48.), [target])
    assert local is not None  # A self-consistent wrong anchor is insufficient.
    verified, detail = track_tip_sequence(drifted, (70., 48.), [target], identity_seed=(manual, (70., 48.)))
    assert verified is None
    assert detail["reason"] == "appearance_ambiguous_or_lost"
    __import__("json").dumps(detail, allow_nan=False)


def test_model_disagreement_does_not_overrule_strong_fixed_image_evidence(tmp_path):
    image = _plant()
    seed = _frame(tmp_path, "seed", image, "side")
    target = _frame(tmp_path, "target", image, "side")
    candidate, quality = track_tip_sequence(seed, (70., 48.), [target], target_hint=(90., 48.))
    np.testing.assert_allclose([candidate.x_px, candidate.y_px], [70., 48.], atol=.1)
    assert quality["cross_view_checked"] and quality["cross_view_disagreement"]


def test_verified_keyframes_follow_appearance_change_without_moving_the_marked_tissue(tmp_path):
    image = _plant()
    changed = image.copy()
    patch = np.random.default_rng(71).integers(0, 90, (31, 31, 3), dtype=np.uint8)
    patch[:, :, 1] += 120
    changed[33:64, 55:86] = patch
    changed[41:56, 63:78] = image[41:56, 63:78]
    frames = [_frame(tmp_path, f"growth-{index}", cv2.addWeighted(image, 1 - index / 72, changed, index / 72, 0))
              for index in range(1, 73)]
    candidate, quality = track_tip_sequence(_frame(tmp_path, "seed", image), (70., 48.), frames)
    assert candidate is not None, quality
    np.testing.assert_allclose([candidate.x_px, candidate.y_px], [70, 48], atol=.5)
    assert quality["keyframe_updates"] >= 4 and quality["identity_verified"]


def test_smaller_shoot_patch_survives_leaf_change_but_rejects_duplicate_tissue(tmp_path):
    image = _plant()
    changed = image.copy()
    patch = np.random.default_rng(71).integers(0, 90, (31, 31, 3), dtype=np.uint8)
    patch[:, :, 1] += 120
    changed[33:64, 55:86] = patch
    changed[40:57, 62:79] = image[40:57, 62:79]
    seed = _frame(tmp_path, "seed", image)
    candidate, quality = track_tip_sequence(seed, (70., 48.), [_frame(tmp_path, "leaf-change", changed)])
    assert candidate is not None, quality
    np.testing.assert_allclose([candidate.x_px, candidate.y_px], [70, 48], atol=.5)
    assert quality["patch_radius_px"] == 7 and quality["minimum_correlation"] >= .86
    duplicate = np.full_like(image, 15)
    duplicate[41:56, 38:53] = image[41:56, 63:78]
    duplicate[41:56, 98:113] = image[41:56, 63:78]
    rejected, _ = track_tip_sequence(seed, (70., 48.), [_frame(tmp_path, "duplicate-small-shoot", duplicate)])
    assert rejected is None


@pytest.mark.parametrize("tracking_version", [1, TIP_TRACKING_VERSION])
def test_backfill_repairs_existing_tips_without_models_or_future_rounds(pipeline, monkeypatch, tracking_version):
    from app.analysis.tip.temporal_tracker import TIP_TRACKING_VERSION
    from app.analysis.rounds.paths import round_artifact_directory
    service, repository, artifacts, events = _seeded_fixture(pipeline, monkeypatch)
    service._run_job("analysis-test", Event())
    monkeypatch.setattr(service._runner, "start", lambda key: True)
    first, second = repository.list_rounds("analysis-test")
    preview = service.get_round_model_preview("analysis-test", first.round_key)
    correction = service.save_tip_correction("analysis-test", TipCorrectionRequest(
        round_key=first.round_key, reason="seed", model_point_id=preview["gaussian_point_offset"], model_signature=preview["signature"],
        observations=[TipCorrectionObservation(view_id=view.view_id, x_px=70, y_px=48)
                      for view in repository.list_views("analysis-test", first.round_key) if view.camera_id in {"top", "side"}],
    ), "operator")
    # Only the first round has been processed; a backfill must not create round 2.
    old, _, _ = service._track_fixed_tip(repository.get("analysis-test"), first,
        repository.list_views("analysis-test", first.round_key), Event(), include_model_hints=False)
    repository.upsert_tip_landmark(old.model_copy(update={"image_tip_confirmed": False,
        "tracking": {**old.tracking, "version": tracking_version}}))
    repository.update_state("analysis-test", status="cancelled", stage="waiting_for_tip_seed", updated_at="2026-10-10T00:00:00+00:00")
    before = repository.get("analysis-test")
    models = repository.list_round_models("analysis-test")
    model_bytes = [(artifacts.root / model.model_path).read_bytes() for model in models]
    checkpoint = (artifacts.root / "checkpoints/steps.sqlite3").read_bytes()
    events.clear()
    result = service.refresh_existing_tip_tracks("analysis-test")
    assert result["updated_rounds"] == result["confirmed_rounds"] == 1
    assert repository.list_tip_landmarks("analysis-test")[0].tracking["version"] == TIP_TRACKING_VERSION
    assert repository.list_tip_corrections("analysis-test") == [correction]
    after = repository.get("analysis-test")
    assert (after.status, after.stage, after.progress, after.current_frame) == (before.status, before.stage, before.progress, before.current_frame)
    assert not events and not artifacts.undistortion_manifest_path(second.round_key).exists()
    assert repository.list_round_models("analysis-test") == models
    assert [(artifacts.root / model.model_path).read_bytes() for model in models] == model_bytes
    assert (artifacts.root / "checkpoints/steps.sqlite3").read_bytes() == checkpoint
    assert __import__("json").loads((round_artifact_directory(artifacts.root, first.round_key) / "tip/tip_marker.json").read_text(encoding="utf-8"))["image_tip_confirmed"]
    # An operator editing the seed while a repair computes must win atomically.
    saved_tip = repository.list_tip_landmarks("analysis-test")[0]
    changed_correction = correction.model_copy(update={"reason": "new operator edit"})
    repository.update_tip_correction(changed_correction)
    assert not repository.refresh_existing_tip_track(saved_tip.model_copy(update={"image_tip_confirmed": False}), [],
        expected_tip=saved_tip, expected_corrections=[correction])
    assert repository.list_tip_landmarks("analysis-test") == [saved_tip]
    assert repository.list_tip_corrections("analysis-test") == [changed_correction]


def test_existing_gap_recovers_backwards_from_a_later_manual_seed(pipeline, monkeypatch):
    from app.analysis.tip.temporal_tracker import TIP_TRACKING_VERSION
    service, repository, artifacts, events = _seeded_fixture(pipeline, monkeypatch)
    service._run_job("analysis-test", Event())
    first, second = repository.list_rounds("analysis-test")
    # Prepare existing captures only. Round 3 supplies the later manual anchor.
    second_views = repository.list_views("analysis-test", second.round_key)
    third = second.model_copy(update={"round_key": "record:mode:round.03", "round_id": "round.03",
                                      "started_at": "2026-10-07T00:00:30+00:00"})
    third_views = [view.model_copy(update={"round_key": third.round_key, "view_id": "3-" + view.camera_id,
                                          "capture_id": view.capture_id + 3, "timestamp": third.started_at})
                   for view in second_views]
    repository.replace_rounds_and_views("analysis-test", [first, second, third],
        repository.list_views("analysis-test") + third_views)
    run = repository.get("analysis-test")
    for item, views in ((second, second_views), (third, third_views)):
        undistort_analysis_views(views, run.intrinsics_snapshot, artifacts.root,
            manifest_path=artifacts.undistortion_manifest_path(item.round_key))
    from app.models.analysis_models import TipLandmark, TipCorrection
    base = TipLandmark(analysis_id=run.analysis_id, round_key=second.round_key, tip_id=f"{second.round_key}:tip",
        record_id=second.record_id, mode_id=second.mode_id, round_id=second.round_id, timestamp=second.started_at,
        valid=False, confidence=0, source="invalid", detection_type="invalid", tracking={"version": TIP_TRACKING_VERSION})
    repository.upsert_tip_landmark(base)
    seed_observations = [TipCorrectionObservation(view_id=view.view_id, x_px=73, y_px=46)
                         for view in third_views if view.camera_id in {"top", "side"}]
    seed_tip = base.model_copy(update={"round_key": third.round_key, "round_id": third.round_id,
        "tip_id": f"{third.round_key}:tip", "timestamp": third.started_at,
        "image_tip_confirmed": True, "image_observations": [item.model_dump(mode="json") for item in seed_observations]})
    correction = TipCorrection(correction_id="later-manual-seed", analysis_id=run.analysis_id,
        round_key=third.round_key, correction_type="views", reason="reidentify", operator_id="operator",
        created_at="2026-10-07T00:01:00+00:00", observations=seed_observations,
        automatic_tip=seed_tip, corrected_tip=seed_tip, confidence_before=0, confidence_after=1,
        tracking_seed_confirmed=True)
    repository.insert_tip_correction(correction)
    repository.upsert_tip_landmark(seed_tip)
    events.clear()
    result = service.refresh_existing_tip_tracks(run.analysis_id)
    restored = next(item for item in repository.list_tip_landmarks(run.analysis_id) if item.round_key == second.round_key)
    assert result["confirmed_rounds"] == 2 and restored.image_tip_confirmed
    assert restored.tracking["direction"] == "backward"
    assert restored.tracking["seed_id"] == correction.correction_id
    assert {item["view_id"] for item in restored.image_observations} == {"2-top", "2-side"}
    assert not events and repository.list_tip_corrections(run.analysis_id) == [correction]
    # Retracting the anchor also invalidates tracks derived from that anchor.
    repository.update_tip_correction(correction.model_copy(update={"invalid": True,
        "corrected_tip": seed_tip.model_copy(update={"image_tip_confirmed": False})}))
    service.refresh_existing_tip_tracks(run.analysis_id)
    assert not next(item for item in repository.list_tip_landmarks(run.analysis_id)
                    if item.round_key == second.round_key).image_tip_confirmed


def _seeded_fixture(pipeline, monkeypatch):
    from test_model_reference import _reference_model_result
    service, repository, artifacts, events, worker, _ = pipeline
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
    original_preprocess = service._run_round_preprocessing

    def preprocess(run, event, *, round_key):
        result = original_preprocess(run, event, round_key=round_key)
        undistort_analysis_views(repository.list_views(run.analysis_id, round_key), run.intrinsics_snapshot,
            artifacts.root, manifest_path=artifacts.undistortion_manifest_path(round_key))
        return result

    def model_worker(job, root, event, **kwargs):
        result = worker(job, root, event, **kwargs)
        preview = _reference_model_result(job, root / "reference")
        return {**result, **preview, "model_quality": {**preview["model_quality"], "immutable_reference": True,
            "initial_camera_pose": np.eye(4).tolist()}}

    monkeypatch.setattr(service, "_run_round_preprocessing", preprocess)
    monkeypatch.setattr(analysis_service, "run_reconstruction_worker", model_worker)
    return service, repository, artifacts, events


def test_round_tracking_uses_paired_instants_without_arm_sweep_occlusions(pipeline, monkeypatch, tmp_path):
    service, repository, artifacts, _ = _seeded_fixture(pipeline, monkeypatch)
    service._run_job("analysis-test", Event())
    monkeypatch.setattr(service._runner, "start", lambda key: True)
    run = repository.get("analysis-test")
    first, second = repository.list_rounds(run.analysis_id)
    first_views = repository.list_views(run.analysis_id, first.round_key)
    preview = service.get_round_model_preview(run.analysis_id, first.round_key)
    correction = service.save_tip_correction(run.analysis_id, TipCorrectionRequest(round_key=first.round_key,
        reason="seed", model_point_id=preview["gaussian_point_offset"], model_signature=preview["signature"],
        observations=[TipCorrectionObservation(view_id=view.view_id, x_px=70, y_px=48)
                      for view in first_views if view.camera_id in {"top", "side"}]), "operator")
    sweep = []
    for index in range(10):
        for view in first_views:
            if view.camera_id not in {"top", "side"}:
                continue
            path = tmp_path / f"arm-{index}-{view.camera_id}.png"
            cv2.imencode(".png", np.full((120, 160, 3), 15, np.uint8))[1].tofile(path)
            sweep.append(view.model_copy(update={"view_id": path.stem, "snapshot_id": f"arm-{index}",
                "capture_id": 100 + len(sweep), "absolute_path": str(path), "relative_path": path.name,
                "image_sha256": __import__("hashlib").sha256(path.read_bytes()).hexdigest(),
                "timestamp": f"2026-10-07T00:00:10.{index + 1:06d}+00:00"}))
    repository.replace_rounds_and_views(run.analysis_id, [first, second], repository.list_views(run.analysis_id) + sweep)
    repository.insert_tip_correction(correction)
    for item in (first, second):
        undistort_analysis_views(repository.list_views(run.analysis_id, item.round_key), run.intrinsics_snapshot,
            artifacts.root, manifest_path=artifacts.undistortion_manifest_path(item.round_key))
    tip, _, rows = service._track_fixed_tip(run, second, repository.list_views(run.analysis_id, second.round_key),
        Event(), include_model_hints=False)
    assert tip.image_tip_confirmed and len(rows) == 2
    assert all(detail["frame_count"] == 1 for detail in tip.tracking["cameras"].values())
    for observation in tip.image_observations:
        np.testing.assert_allclose([observation["x_px"], observation["y_px"]], [73, 46], atol=.5)


def test_first_round_builds_model_then_requires_all_three_marks_before_tracking(pipeline, monkeypatch):
    service, repository, artifacts, events = _seeded_fixture(pipeline, monkeypatch)
    service._run_job("analysis-test", Event())
    run = repository.get("analysis-test")
    assert (run.status, run.stage) == ("paused", "waiting_for_tip_seed")
    assert events == [("preprocess", "record:mode:round.01"), ("model", "record:mode:round.01")]
    assert len(repository.list_round_models(run.analysis_id)) == 1
    assert not artifacts.undistortion_manifest_path("record:mode:round.02").exists()
    starts = []
    monkeypatch.setattr(service._runner, "start", lambda key: starts.append(key) or True)
    first = repository.list_rounds(run.analysis_id)[0]
    views = repository.list_views(run.analysis_id, first.round_key)
    observations = [TipCorrectionObservation(view_id=view.view_id, x_px=70, y_px=48)
                    for view in views if view.camera_id in {"top", "side"}]
    from app.core.exceptions import AnalysisError
    with pytest.raises(AnalysisError, match="第一輪模型"):
        service.save_tip_correction(run.analysis_id, TipCorrectionRequest(
            round_key=first.round_key, reason="images only", observations=observations), "operator")
    reference = service.get_round_model_preview(run.analysis_id, first.round_key)
    model_point = reference["gaussian_point_offset"]
    request = TipCorrectionRequest(round_key=first.round_key, reason="identify shoot",
        observations=observations, model_point_id=model_point, model_signature=reference["signature"])
    correction = service.save_tip_correction(run.analysis_id, request, "operator")
    assert correction.tracking_seed_confirmed and correction.pending_alignment
    assert correction.corrected_tip.image_tip_confirmed and not correction.corrected_tip.valid
    assert correction.corrected_tip.x_mm is None
    assert correction.model_point_id == model_point
    assert correction.model_point_relative_xyz is not None
    assert len(correction.observations) == 2
    assert starts == [run.analysis_id]
    assert repository.get(run.analysis_id).status == "processing"
    # Picking an auxiliary model point later must not erase the image identity.
    repository.insert_tip_correction(correction.model_copy(update={
        "correction_id": "later-model-pick", "correction_type": "point", "observations": [],
        "model_point_id": model_point, "model_signature": reference["signature"],
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


def test_model_preview_tracks_the_seed_with_a_bounded_cache_and_preserves_model_bytes(pipeline, monkeypatch):
    import json
    from app.analysis.rounds.paths import round_artifact_directory
    service, repository, artifacts, _ = _seeded_fixture(pipeline, monkeypatch)
    service._run_job("analysis-test", Event())
    monkeypatch.setattr(service._runner, "start", lambda key: True)
    first, second = repository.list_rounds("analysis-test")
    views = repository.list_views("analysis-test", first.round_key)
    reference = service.get_round_model_preview("analysis-test", first.round_key)
    correction = service.save_tip_correction("analysis-test", TipCorrectionRequest(round_key=first.round_key, reason="shoot seed",
        model_point_id=reference["gaussian_point_offset"], model_signature=reference["signature"],
        observations=[TipCorrectionObservation(view_id=view.view_id, x_px=70, y_px=48)
                      for view in views if view.camera_id in {"top", "side"}]), "operator")
    service._run_job("analysis-test", Event())
    models = repository.list_round_models("analysis-test")
    assert len(models) == 2 and all(model.status == "completed" for model in models)
    snapshot = repository.get("analysis-test").intrinsics_snapshot
    snapshot["rotating"] = snapshot["top"]
    repository.database.execute("UPDATE analysis_runs SET intrinsics_snapshot_json=? WHERE analysis_id=?",
                                (json.dumps(snapshot), "analysis-test"))
    original = [(artifacts.root / model.model_path).read_bytes() for model in models]
    for item in (first, second):
        path = round_artifact_directory(artifacts.root, item.round_key) / "pose_debug/model_reference/context.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"reference": {"signature": item.round_key, "views": []}}), encoding="utf-8")
    calls = []
    def track(source, target, point, matrix, frame_for, **kwargs):
        calls.append((source["signature"], target["signature"], point))
        return {"status": "tracked", "source": "temporal_tracking", "coordinate_space": "model", "relative_xyz": [4., 5., 6.]}
    monkeypatch.setattr(analysis_service, "track_model_tip", track)
    preview = service.get_round_model_preview("analysis-test", second.round_key)
    assert preview["model_tip"]["status"] == "tracked", (preview["model_tip"], calls)
    assert preview["model_tip"]["seed_id"] == correction.correction_id
    assert preview["model_tip"]["model_signature"] == preview["signature"]
    assert service.get_round_model_preview("analysis-test", second.round_key)["model_tip"] == preview["model_tip"]
    assert len(calls) == 1
    service.save_tip_correction("analysis-test", TipCorrectionRequest(round_key=second.round_key, invalid=True, reason="occluded"), "operator")
    assert service.get_round_model_preview("analysis-test", second.round_key)["model_tip"]["status"] == "unavailable"
    assert [(artifacts.root / model.model_path).read_bytes() for model in models] == original


def test_unregistered_rounds_track_fixed_images_after_one_seed_without_model_alignment(pipeline, monkeypatch):
    service, repository, artifacts, events = _seeded_fixture(pipeline, monkeypatch)
    service._run_job("analysis-test", Event())
    monkeypatch.setattr(service._runner, "start", lambda key: True)
    first = repository.list_rounds("analysis-test")[0]
    views = repository.list_views("analysis-test", first.round_key)
    repository.replace_camera_poses("analysis-test", [], round_key=first.round_key)
    reference = service.get_round_model_preview("analysis-test", first.round_key)
    service.save_tip_correction("analysis-test", TipCorrectionRequest(round_key=first.round_key, reason="shoot seed",
        model_point_id=reference["gaussian_point_offset"], model_signature=reference["signature"],
        observations=[TipCorrectionObservation(view_id=view.view_id, x_px=70, y_px=48)
                      for view in views if view.camera_id in {"top", "side"}]), "operator")
    saved_preview = service.get_round_model_preview("analysis-test", first.round_key)
    assert saved_preview["model_tip"]["status"] == "manual"
    assert saved_preview["model_tip"]["model_signature"] == saved_preview["signature"]
    from app.analysis.checkpoints import StepJournal
    with StepJournal(artifacts.root) as journal:
        journal.invalidate(first.round_key, ("round_preprocessing",))

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
    completed_reference_round = repository.list_rounds("analysis-test")[0]
    assert completed_reference_round.status == "tip_only"
    assert repository.list_tip_landmarks("analysis-test")[0].tracking["measurement_warning"] == "no metric cameras"
    assert all(point.x_mm is None for point in repository.list_tip_trajectory("analysis-test"))
    assert len([item for item in events if item[0] == "model"]) == 1, "Tracking must not retrain the first model"
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
