from __future__ import annotations

import json

import cv2
import numpy as np
import pytest

from app.analysis.rounds.paths import round_artifact_directory
from app.analysis.tip import pipeline
from app.analysis.checkpoints import StepJournal, step_signature
from app.analysis.tip import candidate_detector
from app.analysis.tip.candidate_detector import TipCandidate2D, TipCandidateDetection, detect_tip_candidates
from app.analysis.tip.candidate_matcher import TipCandidateView, TriangulatedTipHypothesis, triangulate_tip_hypotheses
from app.analysis.tip.marker_optimizer import optimize_tip_marker
from app.models.analysis_models import AnalysisRound, AnalysisView, CameraPoseResult


def test_large_green_tinted_lamp_halo_cannot_displace_small_plant_candidates(tmp_path):
    image = np.full((240, 320, 3), (18, 27, 20), np.uint8)
    cv2.ellipse(image, (160, 40), (80, 30), 0, 0, 360, (75, 84, 68), -1)
    cv2.circle(image, (140, 30), 12, (255, 255, 255), -1)
    cv2.ellipse(image, (160, 155), (35, 10), 0, 0, 360, (40, 180, 60), -1)
    cv2.rectangle(image, (154, 150), (174, 157), (240, 245, 240), -1)
    cv2.line(image, (160, 165), (160, 190), (50, 120, 70), 2)
    cv2.rectangle(image, (135, 200), (185, 225), (30, 60, 120), -1)
    source = tmp_path / "plant-with-lamp.tiff"
    cv2.imencode(".tiff", image)[1].tofile(source)

    result = detect_tip_candidates(source)

    assert result.candidates and all(candidate.y_px > 130 for candidate in result.candidates)
    assert not result.plant_mask[:80].any()
    assert result.plant_mask[153, 160] == 255  # A pale leaf highlight stays attached.
    assert result.plant_mask[185, 160] == 255
    assert result.plant_mask[215, 160] == 0


def test_tip_candidate_upgrade_replaces_old_lamp_cache_then_reuses_new_detection(tmp_path, monkeypatch):
    image = np.zeros((120, 160, 3), np.uint8)
    cv2.ellipse(image, (80, 70), (30, 10), 0, 0, 360, (30, 160, 50), -1)
    source = tmp_path / "source.tiff"
    cv2.imencode(".tiff", image)[1].tofile(source)
    prefix = "side:01"
    stat = source.stat()
    old_signature = step_signature({
        "version": candidate_detector.TIP_CANDIDATE_VERSION - 1, "count": 12,
        "inputs": [(str(source), stat.st_size, stat.st_mtime_ns)],
    })
    arrays = tmp_path / "old-arrays.npz"
    np.savez_compressed(arrays, plant_mask=np.full((120, 160), 255, np.uint8),
                        skeleton=np.zeros((120, 160), np.uint8), heatmap=image)
    with StepJournal(tmp_path) as journal:
        journal.save("detecting_tip_candidates", prefix, old_signature, {
            "arrays": str(arrays), "candidates": [{"candidate_id": "lamp", "x_px": 20., "y_px": 20.,
                "confidence": 1., "visibility_confidence": 1., "source": "old"}],
            "mask_confidence": 1., "foreground_ratio": 1.,
        }, outputs=[arrays])

    refreshed = detect_tip_candidates(source, candidate_prefix=prefix, checkpoint_root=tmp_path)

    assert refreshed.candidates and all(candidate.candidate_id != "lamp" for candidate in refreshed.candidates)
    assert not refreshed.plant_mask[:40].any()
    monkeypatch.setattr(candidate_detector, "_detect_tip_candidates", lambda *args, **kwargs: pytest.fail("new detection cache was not reused"))
    cached = detect_tip_candidates(source, candidate_prefix=prefix, checkpoint_root=tmp_path)
    assert cached.candidates == refreshed.candidates
    np.testing.assert_array_equal(cached.plant_mask, refreshed.plant_mask)


def test_many_repeated_top_frames_cannot_remove_three_camera_hypothesis():
    expected = np.array([20., -15., 750.])
    other_leaf = np.array([100., 40., 680.])
    matrix = np.array([[800., 0., 640.], [0., 800., 480.], [0., 0., 1.]])
    views = []
    for camera, repeats, center in (("top", 30, (0., 0., 0.)), ("side", 1, (100., 0., 0.)), ("rotating", 3, (20., 90., 0.))):
        projection = matrix @ np.column_stack((np.eye(3), -np.asarray(center)))
        for index in range(repeats):
            view_id = f"{camera}:{index:02d}"
            candidates = []
            points = [expected] if camera == "side" else [other_leaf] if camera == "top" and index >= 2 else [expected, other_leaf]
            for ordinal, point in enumerate(points):
                pixel = projection @ np.append(point, 1.)
                candidates.append(TipCandidate2D(
                    candidate_id=f"{view_id}:{ordinal}", x_px=float(pixel[0] / pixel[2]),
                    y_px=float(pixel[1] / pixel[2]), confidence=1., visibility_confidence=1., source="synthetic",
                ))
            views.append(TipCandidateView(view_id, camera, projection, np.asarray(center), tuple(candidates)))

    hypotheses = triangulate_tip_hypotheses(views, rejection_threshold_px=5., maximum_hypotheses=1)

    assert len(hypotheses) == 1
    np.testing.assert_allclose(hypotheses[0].point_world_mm, expected, atol=1e-7)
    assert hypotheses[0].aggregation_quality["supporting_camera_counts"] == {"top": 2, "side": 1, "rotating": 3}


def test_tip_choice_favors_independent_cameras_and_allows_occluded_camera_fallback():
    def hypothesis(counts, position, error, confidence):
        return TriangulatedTipHypothesis(
            point_world_mm=np.asarray(position), observations=(), reprojection_errors_px=(),
            used_observations=(True,) * sum(counts.values()), mean_error_px=error,
            maximum_error_px=error, angular_spread_deg=45., confidence=confidence,
            aggregation_quality={"supporting_camera_counts": counts},
        )

    partial = hypothesis({"top": 70, "side": 0, "rotating": 5}, [30., 0., 150.], .1, .98)
    joint = hypothesis({"top": 2, "side": 2, "rotating": 2}, [10., 0., 150.], .5, .9)
    chosen = optimize_tip_marker((partial, joint))
    np.testing.assert_array_equal(chosen.position_world_mm, joint.point_world_mm)
    assert chosen.quality["supporting_camera_count"] == 3

    occluded = optimize_tip_marker((partial,))
    np.testing.assert_array_equal(occluded.position_world_mm, partial.point_world_mm)
    assert occluded.quality["supporting_camera_count"] == 2
    assert occluded.quality["camera_coverage_cost"] == 0


@pytest.mark.parametrize("minimum_confidence, valid", [(0.7, True), (0.99, False)])
def test_three_camera_tip_and_quality_are_saved_without_discarding_observations(
    tmp_path, monkeypatch, minimum_confidence, valid,
):
    round_item = AnalysisRound(
        analysis_id="analysis", round_key="record:mode:round.94", record_id="record",
        mode_id="mode", round_id="round.94", status="model_completed",
    )
    expected = np.array([20., -15., 300.])
    matrix = np.array([[80., 0., 64.], [0., 80., 48.], [0., 0., 1.]])
    image = np.zeros((96, 128, 3), np.uint8)
    mask = np.full((96, 128), 255, np.uint8)
    views, poses, manifest, detections = [], [], [], {}
    for snapshot in range(2):
        for camera, center in (("top", (0., 0., 0.)), ("side", (100., 0., 0.)), ("rotating", (20., 90., 0.))):
            view_id = f"{camera}:{snapshot}"
            source = tmp_path / f"{camera}-{snapshot}.tiff"
            valid_mask = source.with_suffix(".png")
            cv2.imencode(".tiff", image)[1].tofile(source)
            cv2.imencode(".png", mask)[1].tofile(valid_mask)
            views.append(AnalysisView(
                analysis_id="analysis", round_key=round_item.round_key, view_id=view_id,
                capture_id=len(views), camera_id=camera, timestamp="2026-10-08T00:00:00Z",
                relative_path=source.name, absolute_path=str(source),
                image_width=128, image_height=96, image_sha256="test",
            ))
            poses.append(CameraPoseResult(
                analysis_id="analysis", round_key=round_item.round_key, view_id=view_id,
                camera_id=camera, valid=True, pose_source="motor_prior",
                rotation_matrix=np.eye(3).tolist(), translation_vector_mm=(-np.asarray(center)).tolist(),
            ))
            pixel = matrix @ (expected - center)
            candidate = TipCandidate2D(
                candidate_id=f"{view_id}:tip", x_px=float(pixel[0] / pixel[2]),
                y_px=float(pixel[1] / pixel[2]), confidence=1., visibility_confidence=1., source="synthetic",
            )
            detections[view_id] = TipCandidateDetection(
                candidates=(candidate,), plant_mask=mask, skeleton=mask,
                heatmap=image, mask_confidence=1., foreground_ratio=1.,
            )
            manifest.append({
                "view_id": view_id, "undistorted_path": source.name,
                "valid_pixel_mask_path": valid_mask.name,
            })
    monkeypatch.setattr(pipeline, "detect_tip_candidates", lambda *args, candidate_prefix, **kwargs: detections[candidate_prefix])

    result = pipeline.analyze_round_tip(
        analysis_id="analysis", round_item=round_item, views=views, poses=poses,
        intrinsics_snapshot={camera: {"undistorted_camera_matrix": matrix.tolist()} for camera in ("top", "side", "rotating")},
        undistortion_manifest=manifest, artifacts_root=tmp_path, model_result=None,
        previous_landmark=None, minimum_confidence=minimum_confidence,
        minimum_supporting_views=2, maximum_reprojection_error_px=5.,
    )

    assert result.landmark.valid is valid
    assert result.landmark.confidence > .7
    assert result.landmark.visible_view_count == 6
    assert all(item.selected for item in result.observations)
    np.testing.assert_allclose([result.landmark.x_mm, result.landmark.y_mm, result.landmark.z_mm], expected, atol=1e-6)
    tip_root = round_artifact_directory(tmp_path, round_item.round_key) / "tip"
    saved = json.loads((tip_root / "tip_marker.json").read_text(encoding="utf-8"))
    assert saved["valid"] is valid
    assert saved["quality"]["supporting_camera_counts"] == {"top": 2, "side": 2, "rotating": 2}
    assert json.loads((tip_root / "marker_quality.json").read_text(encoding="utf-8")) == saved["quality"]
    reprojections = json.loads((tip_root / "reprojection.json").read_text(encoding="utf-8"))
    assert len(reprojections) == len(views)
    assert all((tmp_path / item["overlay_path"]).is_file() for item in reprojections)
    assert len(json.loads((tip_root / "observations_2d.json").read_text(encoding="utf-8"))) == 6
