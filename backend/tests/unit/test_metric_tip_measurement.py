from types import SimpleNamespace

import numpy as np
import pytest

from app.analysis.tip.metric_measurement import measure_image_tip
from app.models.analysis_models import TipLandmark


def _fixture():
    matrix = [[500., 0., 320.], [0., 500., 240.], [0., 0., 1.]]
    views = [SimpleNamespace(view_id=camera, camera_id=camera, snapshot_id="same",
                             timestamp="same", image_width=640, image_height=480)
             for camera in ("top", "side")]
    poses = [SimpleNamespace(view_id=camera, valid=True, rotation_matrix=np.eye(3).tolist(),
                             translation_vector_mm=translation)
             for camera, translation in (("top", [0., 0., 0.]), ("side", [-100., 0., 0.]))]
    tip = TipLandmark(analysis_id="test", round_key="r:mode:round.01", tip_id="tip", round_id="round.01",
        confidence=.9, valid=False, source="temporal_tracking", detection_type="invalid", image_tip_confirmed=True,
        image_observations=[{"view_id": "top", "x_px": 340., "y_px": 250.},
                            {"view_id": "side", "x_px": 240., "y_px": 250.}],
        tracking={"model_tip": {"point_id": 7}, "cameras": {"top": {"identity_verified": True}}})
    return tip, views, poses, {camera: {"undistorted_camera_matrix": matrix} for camera in ("top", "side")}


def test_saved_image_tips_become_metric_without_changing_pixels_or_model_marks():
    tip, views, poses, intrinsics = _fixture()
    measured = measure_image_tip(tip, views, poses, intrinsics)
    assert measured.valid and measured.image_tip_confirmed
    np.testing.assert_allclose([measured.x_mm, measured.y_mm, measured.z_mm], [20., 10., 500.], atol=1e-4)
    assert measured.maximum_reprojection_error_px < 1e-4
    assert measured.image_observations == tip.image_observations
    assert measured.tracking["model_tip"] == tip.tracking["model_tip"]
    assert measured.tracking["metric_measurement"]["absolute_accuracy_verified"] is False
    assert tip.x_mm is None and not tip.valid


@pytest.mark.parametrize("problem", ["missing_pose", "different_snapshot", "wrong_tip", "unconfirmed", "nonfinite"])
def test_invalid_measurements_keep_original_image_identity_without_inventing_coordinates(problem):
    tip, views, poses, intrinsics = _fixture()
    if problem == "missing_pose":
        poses.pop()
    elif problem == "different_snapshot":
        views[1].snapshot_id = "different"
    elif problem == "wrong_tip":
        tip.image_observations[1]["y_px"] += 40
    elif problem == "unconfirmed":
        tip.image_tip_confirmed = False
    else:
        tip.image_observations[1]["x_px"] = float("nan")
    measured = measure_image_tip(tip, views, poses, intrinsics)
    assert not measured.valid and measured.x_mm is measured.y_mm is measured.z_mm is None
    assert measured.image_tip_confirmed == tip.image_tip_confirmed
    assert measured.image_observations == tip.image_observations


@pytest.mark.parametrize("direction", ["forward", "backward"])
def test_resuming_reuses_calibrated_original_observations_instead_of_redetecting(direction, monkeypatch):
    from threading import Event
    from app.services import analysis_service
    from app.services.analysis_service import AnalysisService
    tip, base_views, base_poses, intrinsics = _fixture()
    rounds = [SimpleNamespace(round_key=f"r:mode:round.{n:02d}", round_id=f"round.{n:02d}",
        mode_id="mode", record_id="r", started_at=f"2026-10-01T00:00:{n:02d}Z") for n in (1, 2, 3)]
    view_map = {}
    for number, item in enumerate(rounds, 1):
        view_map[item.round_key] = [SimpleNamespace(**{**vars(view), "view_id": f"{number}-{view.camera_id}",
            "round_key": item.round_key, "capture_id": number * 2 + index, "timestamp": item.started_at})
            for index, view in enumerate(base_views)]
    middle = rounds[1]
    tips = tip.model_copy(update={"round_key": middle.round_key, "round_id": middle.round_id,
        "image_observations": [{**observation, "view_id": f"2-{observation['view_id']}"} for observation in tip.image_observations]})
    poses = [SimpleNamespace(**{**vars(pose), "view_id": f"2-{pose.view_id}"}) for pose in base_poses]
    tips = measure_image_tip(tips, view_map[middle.round_key], poses, intrinsics)
    tips.tracking.update(seed_id="manual-1" if direction == "forward" else "manual-3", direction=direction,
        version=3, cameras={camera: {"identity_verified": True} for camera in ("top", "side")})
    corrections = [SimpleNamespace(round_key=rounds[number - 1].round_key, correction_id=f"manual-{number}", invalid=False,
        observations=[SimpleNamespace(view_id=f"{number}-{observation['view_id']}",
            x_px=observation["x_px"], y_px=observation["y_px"]) for observation in tip.image_observations]) for number in (1, 3)]
    service = object.__new__(AnalysisService)
    service.repository = SimpleNamespace(list_rounds=lambda _: rounds, list_tip_corrections=lambda _: corrections,
        list_views=lambda _, key: view_map[key], list_tip_landmarks=lambda _: [tips], list_camera_poses=lambda *_: poses)
    run = SimpleNamespace(analysis_id="test", parameters={"tip_analysis": {}}, intrinsics_snapshot=intrinsics)
    monkeypatch.setattr(analysis_service, "track_tip_sequence", lambda *args, **options: pytest.fail("The original image tip was already calibrated"))
    measured, candidates, rows = service._track_fixed_tip(run, middle, view_map[middle.round_key], Event(), include_model_hints=False)
    assert measured.valid and measured.image_observations == tips.image_observations
    assert measured.tracking["reused_image_tracking_version"] == 3
    assert len(candidates) == len(rows) == 2
