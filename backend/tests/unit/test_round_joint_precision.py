from __future__ import annotations

from threading import Event
from contextlib import nullcontext
from types import SimpleNamespace

import cv2
import numpy as np

from app.analysis.pose_alignment.model_reference import aggregate_fixed_camera_poses
from app.analysis.reconstruction.multiview import robust_multiview_triangulate
from app.analysis.reconstruction.reference_sfm import prepare_reference_feature_masks, reference_image_name, reference_initial_pair
from app.analysis.rounds.view_selector import select_round_reconstruction_views
from app.analysis.tip.candidate_detector import TipCandidate2D
from app.analysis.tip.candidate_matcher import TipCandidateView, triangulate_tip_hypotheses
from app.models.analysis_models import CameraPoseResult
from test_model_reference import _reference_service_fixture, _reference_model_result, _rig
from test_multiview_reconstruction import _projection, _project


def test_joint_sfm_initialization_uses_motor_baseline_instead_of_repeated_fixed_frames():
    views = [{"view_id": str(i), "camera_id": camera, "undistorted_path": f"{i}.tiff",
              "angle_deg": angle, "motor_position_deg": motor}
             for i, (camera, angle, motor) in enumerate((("side", 0., None), ("side", 10., None),
                  ("rotating", 355., None), ("rotating", None, 15.), ("rotating", 355.5, None)), 1)]
    images = [SimpleNamespace(image_id=i, name=reference_image_name(v)) for i, v in enumerate(views, 1)]
    pairs = [(1, 2), (3, 5), (3, 4)]
    geometries = [SimpleNamespace(inlier_matches=[None] * n) for n in (9999, 1000, 24)]
    database = SimpleNamespace(read_all_images=lambda: images, read_two_view_geometries=lambda: (pairs, geometries))
    pycolmap = SimpleNamespace(Database=SimpleNamespace(open=lambda _: nullcontext(database)), pair_id_to_image_pair=lambda p: p)
    assert reference_initial_pair(pycolmap, "database.db", views, 12) == {
        "image_ids": [3, 4], "motor_baseline_deg": 20., "camera_id": "rotating"}
    assert reference_initial_pair(pycolmap, "database.db", views, 25) is None


def test_every_valid_round_view_is_selected_including_repeated_fixed_and_motor_positions(tmp_path):
    service, state, reference, views, manifest = _reference_service_fixture(tmp_path)
    views += [views[-2].model_copy(update={"view_id": "top-repeat"}),
              views[-1].model_copy(update={"view_id": "side-repeat"}),
              views[0].model_copy(update={"view_id": "rotating-repeat", "angle_deg": None, "motor_position_deg": 0.}),
              views[0].model_copy(update={"view_id": "unresolved"})]
    poses = {v.view_id: CameraPoseResult(analysis_id=v.analysis_id, round_key=v.round_key,
             view_id=v.view_id, camera_id=v.camera_id, valid=True, pose_source="motor_prior",
             rotation_matrix=np.eye(3).tolist(), translation_vector_mm=[0., 0., 1.])
             for v in views if v.view_id != "unresolved"}
    try:
        result = select_round_reconstruction_views(views, poses, {})
        assert set(result.selected_view_ids) == {v.view_id for v in views if v.view_id != "unresolved"}
        assert next(v for v in result.views if v.view_id == "unresolved").exclusion_reason == "相機姿態無效。"
    finally:
        service._runner.close()


def test_fixed_pose_consensus_rejects_misregistration_and_handles_rotation_wraparound():
    observations = []
    for index, degrees in enumerate((179.8, 180., -179.8, 179.9, 80.)):
        rotation = cv2.Rodrigues(np.array([0., 0., np.deg2rad(degrees)]))[0]
        center = np.array([.001 * (index - 1.5), .2, 1.]) if index < 4 else np.array([8., 7., 1.])
        pose = np.eye(4); pose[:3, :3] = rotation; pose[:3, 3] = -rotation @ center
        observations.append({"camera_id": "top", "view_id": str(index), "pose": pose.tolist(), "point_count": 50})
    fixed, quality = aggregate_fixed_camera_poses(observations, orbit_radius=1.)
    pose = np.asarray(fixed["top"])
    assert abs(np.linalg.det(pose[:3, :3]) - 1.) < 1e-10
    assert np.linalg.norm(np.linalg.inv(pose)[:3, 3] - [0., .2, 1.]) < .002
    assert abs(np.rad2deg(cv2.Rodrigues(pose[:3, :3])[0][2, 0])) > 179.7
    assert quality["top"]["rejected_view_ids"] == ["4"]


def test_camera_balanced_estimate_is_unchanged_when_one_camera_has_duplicate_frames():
    expected = np.array([35., 22., 900.])
    projections = [_projection(0.), _projection(120.), _projection(30., 110.)]
    pixels = np.asarray([_project(p, expected) for p in projections]) + [[1.4, -.8], [-1.2, .7], [.1, -.2]]
    one = robust_multiview_triangulate(projections, pixels, camera_ids=["top", "side", "rotating"])
    many = robust_multiview_triangulate([*projections, *([projections[0]] * 60)], [*pixels, *([pixels[0]] * 60)],
                                      camera_ids=["top", "side", "rotating", *(["top"] * 60)])
    np.testing.assert_allclose(many.point, one.point, atol=1e-7)
    assert many.quality["accepted_observation_count"] == 63


def test_round_consensus_reduces_noise_and_rejects_wrong_tip_observations():
    expected = np.array([35., 22., 900.])
    rng = np.random.default_rng(1024)
    projections, pixels, cameras = [], [], []
    for index in range(30):
        for camera, center in (("top", (0., 0.)), ("side", (120., 0.)), ("rotating", (40. + index * 3., 110.))):
            projection = _projection(*center)
            pixel = np.asarray(_project(projection, expected)) + rng.normal(0., .7, 2)
            if index > 20 and camera == "side":
                pixel += [70., -90.]
            projections.append(projection); pixels.append(pixel); cameras.append(camera)
    seed = robust_multiview_triangulate(projections[:2], pixels[:2])
    result = robust_multiview_triangulate(projections, pixels, camera_ids=cameras, rejection_threshold_px=5.)
    assert np.linalg.norm(result.point - expected) < np.linalg.norm(seed.point - expected)
    assert np.linalg.norm(result.point - expected) < 2.
    assert result.quality["accepted_observation_count"] == 81
    assert result.quality["rejected_observation_count"] == 9


def test_bounded_tip_seeds_still_fuse_all_three_cameras_and_every_snapshot():
    expected = np.array([20., -15., 750.])
    views = []
    for index in range(20):
        for camera, center in (("top", (0., 0.)), ("side", (100., 0.)), ("rotating", (20. + index * 3., 90.))):
            projection = _projection(*center); x, y = _project(projection, expected)
            name = f"{camera}:{index}"
            views.append(TipCandidateView(name, camera, projection, np.array([*center, 0.]),
                         (TipCandidate2D(candidate_id=name, x_px=x, y_px=y, confidence=1., visibility_confidence=1., source="synthetic"),)))
    result = triangulate_tip_hypotheses(views)
    assert result and sum(result[0].used_observations) == 60
    np.testing.assert_allclose(result[0].point_world_mm, expected, atol=1e-7)
    assert result[0].aggregation_quality["supporting_camera_counts"] == {"top": 20, "side": 20, "rotating": 20}


def test_reference_auto_alignment_trains_all_fixed_frames_once_in_shared_coordinates(tmp_path, monkeypatch):
    from app.services import analysis_service
    service, state, reference, views, manifest = _reference_service_fixture(tmp_path)
    for camera in ("top", "side"):
        source = next(v for v in views if v.camera_id == camera)
        for index in range(2):
            extra = source.model_copy(update={"view_id": f"{camera}-extra-{index}", "snapshot_id": f"snapshot-{index}"})
            views.append(extra); manifest[extra.view_id] = manifest[source.view_id]
        later = source.model_copy(update={"view_id": f"{camera}-later", "round_key": "record:mode:round.02"})
        views.append(later); manifest[later.view_id] = manifest[source.view_id]
    calls = []

    def worker(job, output, event, **kwargs):
        calls.append(job.get("reference_action") or "train")
        if job.get("reference_action") == "rotating":
            by_id = {v["view_id"]: v for v in reference["views"]}
            reference["views"] = [{**v, "pose": _rig()[v["camera_id"]].tolist() if v["camera_id"] in {"top", "side"}
                                   else by_id[v["view_id"]]["pose"]} for v in job["selected_views"]]
            reference["sparse_path"] = str(tmp_path / "sparse")
            return reference
        assert job.get("reference_action") is None
        assert len(job["selected_views"]) == 18
        assert all("later" not in v["view_id"] for v in job["selected_views"])
        return _reference_model_result(job, output)

    monkeypatch.setattr(analysis_service, "run_reconstruction_worker", worker)
    try:
        registration = service._prepare_model_reference(state["run"], views, manifest, Event())
        service._prepare_model_reference(state["run"], views, manifest, Event())
        assert calls == ["rotating", "train"]
        assert registration["quality"]["fixed_pose_consensus"]["top"]["observation_count"] == 3
    finally:
        service._runner.close()


def test_reference_feature_masks_keep_pot_and_plant_but_remove_background_and_resume(tmp_path):
    image = np.full((160, 160, 3), 8, np.uint8)
    cv2.rectangle(image, (0, 0), (20, 20), (255, 255, 255), -1)
    cv2.rectangle(image, (60, 38), (100, 74), (25, 150, 50), -1)
    cv2.rectangle(image, (62, 80), (98, 120), (20, 25, 35), -1)
    cv2.ellipse(image, (80, 82), (20, 8), 0, 0, 360, (40, 80, 180), 3)
    source, valid = tmp_path / 'frame.tiff', tmp_path / 'valid.png'
    cv2.imencode('.tiff', image)[1].tofile(source)
    cv2.imencode('.png', np.full((160, 160), 255, np.uint8))[1].tofile(valid)
    views = [{"view_id": "side-frame", "camera_id": "side", "undistorted_path": str(source), "valid_mask_path": str(valid)}]
    masks = prepare_reference_feature_masks(views, tmp_path / 'sfm', 'signature', cancel_check=lambda: None)
    path = masks / (reference_image_name(views[0]) + '.png')
    result = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_GRAYSCALE)
    assert result[55, 80] and result[105, 80]
    assert result[10, 10] == 0 and result[150, 150] == 0
    modified = path.stat().st_mtime_ns
    prepare_reference_feature_masks(views, tmp_path / 'sfm', 'signature', cancel_check=lambda: None)
    assert path.stat().st_mtime_ns == modified
