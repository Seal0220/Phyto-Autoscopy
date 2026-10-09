from copy import deepcopy

import cv2
import numpy as np
import pytest

from app.analysis.pose_alignment.motor_angle_calibration import calibrated_motor_angle
from app.analysis.pose_alignment.model_reference import align_model_camera_poses, fit_motor_orbit
from test_model_reference import _look_at, _reference


def test_image_poses_calibrate_biased_motor_readings_without_moving_geometry():
    reference = _reference()
    views = reference["views"]
    for view in views:
        view["angle_deg"] = view["angle_deg"] * 1.04 + 7
    original = deepcopy(views)
    orbit = fit_motor_orbit(views)
    assert views == original
    assert orbit["radius"] == pytest.approx(.6)
    assert orbit["rotation_rmse_deg"] < 1e-5
    calibration = orbit["angle_calibration"]
    assert calibration["degree"] == 1
    assert calibration["validation_rmse_deg"] < 1e-6
    assert calibration["maximum_recorded_difference_deg"] > 10
    assert calibrated_motor_angle(45 * 1.04 + 7, orbit) == pytest.approx(45 + 7, abs=1e-6)
    assert all(item["recorded_angle_deg"] == view["angle_deg"]
               for item, view in zip(calibration["observations"], views))


def test_direct_image_pose_wins_over_calibrated_motor_fallback():
    reference = _reference()
    views = reference["views"]
    for view in views:
        view["angle_deg"] = view["angle_deg"] * 1.04 + 7
    orbit = fit_motor_orbit(views)
    registration = {"orbit": orbit, "poses": {}, "reference_poses": {"observed": views[1]["pose"]}}
    frames = [{"view_id": name, "camera_id": "rotating", "capture_id": i, "relative_path": name,
               "angle_deg": 45 * 1.04 + 7} for i, name in enumerate(("observed", "unregistered"))]
    result = align_model_camera_poses(frames, registration, required_camera_ids=["rotating"])
    direct, fallback = result.camera_poses
    np.testing.assert_array_equal(direct.world_to_camera_matrix, views[1]["pose"])
    assert direct.source == "sfm"
    expected = _look_at([.6 * np.cos(np.deg2rad(45)), .6 * np.sin(np.deg2rad(45)), .2])
    np.testing.assert_allclose(fallback.world_to_camera_matrix, expected, atol=1e-7)
    assert fallback.source == "motor_prior"
    assert fallback.motor_angle_deg == frames[1]["angle_deg"]


@pytest.mark.parametrize("direction", [-1, 1])
def test_image_angles_unwrap_full_turns_and_motor_direction(direction):
    raw = np.arange(0, 721, 15, dtype=float)
    views = []
    for index, recorded in enumerate(raw):
        actual = recorded * .985
        pose = _look_at([.6 * np.cos(np.deg2rad(direction * actual)),
                         .6 * np.sin(np.deg2rad(direction * actual)), .2])
        views.append({"camera_id": "rotating", "view_id": str(index), "angle_deg": recorded, "pose": pose.tolist()})
    orbit = fit_motor_orbit(views)
    observations = orbit["angle_calibration"]["observations"]
    np.testing.assert_allclose([item["image_angle_deg"] for item in observations], raw * .985, atol=1e-6)
    assert orbit["rotation_rmse_deg"] < 1e-5
    assert orbit["radius"] == pytest.approx(.6)
    assert calibrated_motor_angle(750, orbit) == pytest.approx(750 * .985, abs=1e-6)


def test_nonlinear_motor_bias_uses_validated_regression_and_monotone_extrapolation():
    raw = np.arange(0, 351, 5, dtype=float)
    x = (raw - 175) / 175
    # This cubic correction has positive angular velocity throughout the sweep.
    actual = raw - 4 * x + 2 * x ** 3
    views = [{"camera_id": "rotating", "view_id": str(index), "angle_deg": angle,
              "pose": _look_at([.6 * np.cos(np.deg2rad(observed)), .6 * np.sin(np.deg2rad(observed)), .2]).tolist()}
             for index, (angle, observed) in enumerate(zip(raw, actual))]
    orbit = fit_motor_orbit(views)
    calibration = orbit["angle_calibration"]
    assert calibration["degree"] == 3
    assert calibration["validation_rmse_deg"] < 1e-6
    assert calibrated_motor_angle(175, orbit) == pytest.approx(173, abs=1e-6)
    predictions = [calibrated_motor_angle(angle, orbit) for angle in range(-30, 391, 5)]
    assert np.all(np.diff(predictions) > 0)
    assert calibrated_motor_angle(360, {}) == 360


def test_non_axis_camera_wobble_remains_visible_after_angle_calibration():
    reference = _reference()
    for index, view in enumerate(reference["views"]):
        pose = np.asarray(view["pose"])
        center = np.linalg.inv(pose)[:3, 3]
        # Roll about the camera's optical axis cannot be absorbed into orbit yaw.
        pose[:3, :3] = cv2.Rodrigues(np.array([0., 0., np.deg2rad(.5 * (-1) ** index)]))[0] @ pose[:3, :3]
        pose[:3, 3] = -pose[:3, :3] @ center
        view["pose"] = pose.tolist()
    orbit = fit_motor_orbit(reference["views"])
    assert orbit["rotation_rmse_deg"] > .2
    assert orbit["rotation_error_angle_source"] == "sfm_rotations"


def test_an_average_below_one_degree_does_not_hide_large_prediction_errors():
    from app.analysis.pose_alignment.motor_angle_calibration import _regress_angles

    raw = np.arange(0, 351, 5, dtype=float)
    observed = raw.copy()
    observed[5::10] += 2.5
    calibration = _regress_angles(raw, observed)
    assert calibration["validation_rmse_deg"] < 1
    assert calibration["validation_absolute_p95_deg"] > 1
    assert calibration["prediction_p95_below_one_degree"] is False
    assert calibration["absolute_accuracy_verified"] is False
    assert calibration["validation_fraction_below_one_degree"] < 1
