from types import SimpleNamespace
import hashlib

import cv2
import numpy as np
import pytest

from app.analysis.pose_alignment.model_reference import fit_motor_orbit
from app.analysis.reconstruction.reference_pose_refinement import refine_reference_geometry


def _pose(center):
    center = np.asarray(center, dtype=float)
    direction = np.array([0., 0., .15]) - center
    direction /= np.linalg.norm(direction)
    right = np.cross(direction, [0., 0., 1.])
    right /= np.linalg.norm(right)
    pose = np.eye(4)
    pose[:3, :3] = [right, np.cross(direction, right), direction]
    pose[:3, 3] = -pose[:3, :3] @ center
    return pose


def _scene(include_fixed=True, point_count=24):
    pycolmap = pytest.importorskip("pycolmap")
    rec = pycolmap.Reconstruction()
    generator = np.random.default_rng(26)
    points = generator.uniform([-.08, -.08, .05], [.08, .08, .25], (point_count, 3))
    views = []
    cameras = ["rotating"] * 12 + (["side"] * 3 if include_fixed else [])
    for camera_id, camera in enumerate(dict.fromkeys(cameras), 1):
        rec.add_camera_with_trivial_rig(pycolmap.Camera(
            camera_id=camera_id, model="PINHOLE", width=320, height=240, params=[400, 400, 160, 120],
        ))
    camera_ids = {name: index for index, name in enumerate(dict.fromkeys(cameras), 1)}
    for image_id, camera in enumerate(cameras, 1):
        angle = (image_id - 1) * 30 if camera == "rotating" else 0
        theta = np.deg2rad(angle)
        expected = _pose([.6 * np.cos(theta), .6 * np.sin(theta), .25]) if camera == "rotating" else _pose([.8, 0., .25])
        camera_points = points @ expected[:3, :3].T + expected[:3, 3]
        pixels = camera_points[:, :2] / camera_points[:, 2:] * 400 + [160, 120]
        observed = expected.copy()
        perturbation = cv2.Rodrigues(generator.normal(0, .0005, 3))[0]
        observed[:3, :3] = perturbation @ observed[:3, :3]
        observed[:3, 3] += generator.normal(0, .0003, 3)
        name = f"{camera}-{image_id}"
        image = pycolmap.Image(image_id=image_id, camera_id=camera_ids[camera], name=name, keypoints=pixels)
        rec.add_image_with_trivial_frame(image, pycolmap.Rigid3d(observed[:3]))
        views.append({"camera_id": camera, "image_name": name, "view_id": name, "angle_deg": angle,
                      "pose": observed.tolist(), "point_count": len(points)})
    for point_index, xyz in enumerate(points):
        track = pycolmap.Track()
        for image_id in range(1, len(cameras) + 1):
            track.add_element(image_id, point_index)
        point_id = rec.add_point3D(xyz + generator.normal(0, .0005, 3), track, np.full(3, 128, dtype=np.uint8))
        rec.point3D(point_id).error = 99
    return pycolmap, rec, views


@pytest.mark.parametrize("include_fixed", [True, False])
def test_reference_is_refined_before_training_without_changing_source(include_fixed):
    pycolmap, rec, views = _scene(include_fixed)
    originals = {image.image_id: image.cam_from_world().matrix().copy() for image in rec.images.values()}
    source_points = {point_id: point.xyz.copy() for point_id, point in rec.points3D.items()}
    result = refine_reference_geometry(pycolmap, rec, views, fit_motor_orbit(views), cancel_check=lambda: None)
    assert result.quality["final_reprojection_error_px"] < result.quality["initial_reprojection_error_px"]
    assert result.quality["status"] == "completed"
    assert result.quality["motor_pose_priors_used"] is False
    assert result.quality["angle_calibration"]["source"] == "sfm_rotations"
    assert result.quality["image_validation"]["status"] == "insufficient_observations"
    if include_fixed:
        poses = [result.reconstruction.image(image_id).cam_from_world().matrix()
                 for image_id in originals if rec.image(image_id).name.startswith("side-")]
        assert all(np.allclose(pose, poses[0], atol=1e-7) for pose in poses)
    else:
        np.testing.assert_allclose(result.reconstruction.image(1).cam_from_world().matrix(), originals[1], atol=1e-7)
    for image_id, original in originals.items():
        np.testing.assert_array_equal(rec.image(image_id).cam_from_world().matrix(), original)
    for point_id, original in source_points.items():
        np.testing.assert_array_equal(rec.point3D(point_id).xyz, original)
        assert rec.point3D(point_id).error == 99


def test_reference_keeps_original_when_a_usable_solver_result_worsens_geometry(monkeypatch):
    pycolmap, rec, views = _scene()
    source_points = {point_id: point.xyz.copy() for point_id, point in rec.points3D.items()}

    def adjuster(*args):
        candidate = args[-1]

        def solve():
            for point in candidate.points3D.values():
                point.xyz += np.array([.2, 0, 0])
            return SimpleNamespace(is_solution_usable=lambda: True)

        return SimpleNamespace(solve=solve)

    monkeypatch.setattr(pycolmap, "create_default_bundle_adjuster", adjuster)
    result = refine_reference_geometry(pycolmap, rec, views, fit_motor_orbit(views), cancel_check=lambda: None)
    assert result.quality["status"] == "kept_original"
    assert result.quality["accepted"] is False
    assert "增加了重投影誤差" in result.quality["rejection_reason"]
    assert result.quality["final_reprojection_error_px"] == result.quality["initial_reprojection_error_px"]
    for point_id, xyz in source_points.items():
        np.testing.assert_array_equal(result.reconstruction.point3D(point_id).xyz, xyz)
    assert all(point.error == 99 for point in rec.points3D.values())


def test_recorded_motor_bias_cannot_pull_image_bundle_adjustment_back_onto_motor_orbit():
    from copy import deepcopy

    pycolmap, rec, views = _scene()
    biased = deepcopy(views)
    for view in biased:
        if view["camera_id"] == "rotating":
            view["angle_deg"] = 1.04 * view["angle_deg"] + 7
    unbiased_result = refine_reference_geometry(pycolmap, rec, views, cancel_check=lambda: None)
    biased_result = refine_reference_geometry(pycolmap, rec, biased, cancel_check=lambda: None)
    for image_id in rec.reg_image_ids():
        np.testing.assert_allclose(
            unbiased_result.reconstruction.image(image_id).cam_from_world().matrix(),
            biased_result.reconstruction.image(image_id).cam_from_world().matrix(), atol=1e-10,
        )
    assert biased_result.quality["angle_calibration"]["maximum_recorded_difference_deg"] > 10
    assert biased_result.quality["motor_pose_priors_used"] is False


@pytest.mark.parametrize("refinement_rejected", [False, True])
def test_sfm_publishes_accepted_geometry_before_dense_training(tmp_path, monkeypatch, refinement_rejected):
    from app.analysis.reconstruction import reference_sfm

    pycolmap, rec, views = _scene()
    snapshots = {camera: {
        "undistorted_camera_matrix": [[400., 0, 160], [0, 400, 120], [0, 0, 1]],
        "analysis_image_width": 320, "analysis_image_height": 240,
    } for camera in ("top", "side", "rotating")}
    source = tmp_path / "source.png"
    source.write_bytes(b"read-only fixture")
    for image_id, view in enumerate(views, 1):
        view.update(undistorted_path=str(source), undistorted_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        rec.image(image_id).name = reference_sfm.reference_image_name(view)
    # An input image alone must not be reported as a registered camera.
    views.append({"camera_id": "top", "view_id": "top-unregistered", "undistorted_path": str(source),
                  "undistorted_sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
    monkeypatch.setattr(pycolmap, "extract_features", lambda **kwargs: None)
    monkeypatch.setattr(pycolmap, "match_exhaustive", lambda **kwargs: None)
    monkeypatch.setattr(pycolmap, "incremental_mapping", lambda *args, **kwargs: {0: rec})
    monkeypatch.setattr(reference_sfm, "prepare_reference_feature_masks", lambda *args, **kwargs: tmp_path)
    monkeypatch.setattr(reference_sfm, "reference_initial_pair", lambda *args, **kwargs: {"image_ids": [1, 2], "motor_baseline_deg": 30})
    if refinement_rejected:
        def adjuster(options, config, candidate):
            def solve():
                for point in candidate.points3D.values():
                    point.xyz += [.2, 0., 0.]
                return SimpleNamespace(is_solution_usable=lambda: True)
            return SimpleNamespace(solve=solve)
        monkeypatch.setattr(pycolmap, "create_default_bundle_adjuster", adjuster)
    progress_messages = []
    result = reference_sfm.build_reference_sfm(
        {"selected_views": views, "intrinsics_snapshot": snapshots, "parameters": {}, "artifact_root": str(tmp_path)},
        tmp_path / "reference", progress=lambda *args: progress_messages.append(args[-1]), cancel_check=lambda: None,
    )
    assert result["status"] == "completed"
    assert result["quality"]["geometry_refinement"]["status"] == ("kept_original" if refinement_rejected else "completed")
    if refinement_rejected:
        assert any("沿用已檢查的原始影像幾何" in message for message in progress_messages)
    assert result["quality"]["input_camera_counts"]["top"] == 1
    assert result["quality"]["registered_camera_counts"]["top"] == 0
    assert result["quality"]["camera_registration"] == {
        "status": "partial", "missing_camera_ids": ["top"], "all_three_cameras_registered": False,
    }
    assert result["quality"]["absolute_accuracy_verified"] is False
    saved = pycolmap.Reconstruction(result["sparse_path"])
    for view in result["views"]:
        image = next(image for image in saved.images.values() if image.name == view["image_name"])
        np.testing.assert_allclose(np.asarray(view["pose"])[:3], image.cam_from_world().matrix(), atol=1e-7)
        if view["camera_id"] == "rotating":
            assert "image_angle_deg" in view
    side = [np.asarray(view["pose"]) for view in result["views"] if view["camera_id"] == "side"]
    if not refinement_rejected:
        assert all(np.allclose(pose, side[0], atol=1e-7) for pose in side)
    else:
        for image_id in rec.reg_image_ids():
            np.testing.assert_array_equal(saved.image(image_id).cam_from_world().matrix(), rec.image(image_id).cam_from_world().matrix())
    assert all(point.error == 99 for point in rec.points3D.values())


def test_reference_validation_predicts_heldout_observations_without_claiming_absolute_accuracy():
    pycolmap, rec, views = _scene(point_count=240)
    result = refine_reference_geometry(pycolmap, rec, views, cancel_check=lambda: None)
    validation = result.quality["image_validation"]
    assert validation["status"] == "passed"
    assert validation["sample_count"] >= 12
    assert validation["final_rmse_px"] < validation["initial_rmse_px"]
    assert validation["absolute_accuracy_verified"] is False
    assert result.quality["absolute_accuracy_verified"] is False
    assert all(point.track.length() == len(views) for point in rec.points3D.values())


def test_reference_rejects_a_solution_that_damages_heldout_predictions(monkeypatch):
    pycolmap, rec, views = _scene(point_count=240)
    source_points = {point_id: point.xyz.copy() for point_id, point in rec.points3D.items()}
    source_poses = {image_id: rec.image(image_id).cam_from_world().matrix().copy() for image_id in rec.reg_image_ids()}

    def adjuster(options, config, candidate):
        def solve():
            for point_id, point in candidate.points3D.items():
                if point_id % 10 == 0 and point.track.length() < len(views):
                    point.xyz += [.05, 0., 0.]
            return SimpleNamespace(is_solution_usable=lambda: True)
        return SimpleNamespace(solve=solve)

    monkeypatch.setattr(pycolmap, "create_default_bundle_adjuster", adjuster)
    result = refine_reference_geometry(pycolmap, rec, views, cancel_check=lambda: None)
    assert result.quality["status"] == "kept_original"
    assert result.quality["accepted"] is False
    assert "保留觀測的重投影誤差" in result.quality["rejection_reason"]
    validation = result.quality["image_validation"]
    assert validation["status"] == "rejected"
    assert validation["final_rmse_px"] > validation["maximum_accepted_rmse_px"]
    assert result.quality["original_geometry_validation"]["status"] == "passed"
    for point_id, xyz in source_points.items():
        np.testing.assert_array_equal(result.reconstruction.point3D(point_id).xyz, xyz)
    for image_id, pose in source_poses.items():
        np.testing.assert_array_equal(result.reconstruction.image(image_id).cam_from_world().matrix(), pose)
    assert all(point.track.length() == len(views) and point.error == 99 for point in rec.points3D.values())


def test_original_geometry_must_pass_checks_before_refinement_can_fall_back(monkeypatch):
    from app.analysis.reconstruction import reference_pose_refinement as refinement

    pycolmap, rec, views = _scene()
    for point in rec.points3D.values():
        point.xyz += [.3, 0., 0.]

    def reject(*args, **kwargs):
        raise refinement._RefinementRejected("validation regression", {"image_validation": {"status": "rejected"}})

    monkeypatch.setattr(refinement, "_refine_reference_geometry", reject)
    with pytest.raises(ValueError, match="原始模型也缺少合格"):
        refine_reference_geometry(pycolmap, rec, views, cancel_check=lambda: None)


def test_unusable_refinement_keeps_original_geometry(monkeypatch):
    pycolmap, rec, views = _scene()
    monkeypatch.setattr(pycolmap, "create_default_bundle_adjuster", lambda *args:
                        SimpleNamespace(solve=lambda: SimpleNamespace(is_solution_usable=lambda: False)))
    result = refine_reference_geometry(pycolmap, rec, views, cancel_check=lambda: None)
    assert result.quality["status"] == "kept_original"
    assert "未取得有效解" in result.quality["rejection_reason"]


def test_refinement_never_converts_cancellation_into_a_geometry_fallback():
    from app.core.exceptions import OperationCancelledError

    pycolmap, rec, views = _scene()

    def cancel():
        raise OperationCancelledError("cancelled by user")

    with pytest.raises(OperationCancelledError, match="cancelled by user"):
        refine_reference_geometry(pycolmap, rec, views, cancel_check=cancel)


def test_refinement_never_hides_unexpected_solver_errors(monkeypatch):
    pycolmap, rec, views = _scene()

    def broken(*args):
        raise RuntimeError("unexpected solver bug")

    monkeypatch.setattr(pycolmap, "create_default_bundle_adjuster", broken)
    with pytest.raises(RuntimeError, match="unexpected solver bug"):
        refine_reference_geometry(pycolmap, rec, views, cancel_check=lambda: None)


def test_geometry_upgrade_invalidates_saved_camera_alignment_and_preview(monkeypatch):
    from app.services import analysis_service

    _, _, views = _scene()
    for view in views:
        view["round_key"] = "record:mode:round.01"
    run = SimpleNamespace(
        analysis_id="analysis-test", output_path="analysis-test", method_name="rotating",
        parameters={"reconstruction": {}, "pose_strategy": {}}, intrinsics_snapshot={}, aruco_layout_snapshot={},
    )
    reference = {"signature": "old-reference", "sparse_path": "sparse"}
    signature = analysis_service.AnalysisService._stereo_pose_signature(run)
    before = analysis_service.AnalysisService._reference_model_job(run, reference, views, alignment_preview=True)
    monkeypatch.setattr(analysis_service, "REFERENCE_GEOMETRY_VERSION", before["reference_geometry_version"] + 1)
    assert analysis_service.AnalysisService._stereo_pose_signature(run) != signature
    after = analysis_service.AnalysisService._reference_model_job(run, reference, views, alignment_preview=True)
    assert after != before
