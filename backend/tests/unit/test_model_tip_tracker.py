import cv2
import numpy as np
import pytest

from app.analysis.tip.model_tracker import model_tip_projection, track_model_tip
from test_temporal_tip_tracker import _frame, _plant


def test_side_can_check_model_tip_without_a_registered_top_camera():
    matrix = np.array([[200., 0, 70], [0, 200, 48], [0, 0, 1]])
    reference = {"orbit": {"rotation_rmse_deg": .7, "position_rmse_over_radius": .01, "radius": 1},
                 "views": [{"view_id": "side", "camera_id": "side", "pose": np.eye(4).tolist()}]}
    tip = {"status": "tracked", "relative_xyz": [.06, -.03, 3.]}
    np.testing.assert_allclose(model_tip_projection(tip, reference, "side", "side", matrix), [74, 46])
    reference["orbit"]["rotation_rmse_deg"] = 3.2
    assert model_tip_projection(tip, reference, "side", "side", matrix) is None
    reference["orbit"]["rotation_rmse_deg"] = .7
    tip["relative_xyz"] = [0, 0, -3]
    assert model_tip_projection(tip, reference, "side", "side", matrix) is None


def _rounds(tmp_path):
    matrix = np.array([[200., 0, 70], [0, 200, 48], [0, 0, 1]])
    rotation = cv2.Rodrigues(np.array([0., 0., np.deg2rad(30)]))[0]
    translation = np.array([1., -.5, 2.])
    seed_point = np.array([0., 0., 3.])
    moved_point = seed_point + [.06, -.03, 0]
    source, target, frames = [], [], {}
    for index, center in enumerate((-.2, 0., .2)):
        pose = np.eye(4)
        pose[0, 3] = -center
        next_pose = np.eye(4)
        next_pose[:3, :3] = rotation.T
        next_pose[:3, 3] = 2 * pose[:3, 3] - rotation.T @ translation
        source_id, target_id = f"old-{index}", f"new-{index}"
        source.append({"view_id": source_id, "camera_id": "rotating", "angle_deg": index * 30, "pose": pose.tolist()})
        target.append({"view_id": target_id, "camera_id": "rotating", "angle_deg": index * 30, "pose": next_pose.tolist()})
        for view_id, point in ((source_id, seed_point), (target_id, moved_point)):
            projected = matrix @ (pose[:3] @ np.append(point, 1))
            shift = projected[:2] / projected[2] - [70, 48]
            image = cv2.warpAffine(_plant(), np.float32([[1, 0, shift[0]], [0, 1, shift[1]]]), (160, 120))
            frames[view_id] = _frame(tmp_path, view_id, image, "rotating")
    return {"views": source}, {"views": target}, frames, matrix, seed_point, 2 * rotation @ moved_point + translation


def test_tip_identity_moves_into_each_new_models_coordinate_frame(tmp_path):
    source, target, frames, matrix, point, expected = _rounds(tmp_path)
    result = track_model_tip(source, target, point, matrix, frames.__getitem__)
    assert result["status"] == "tracked"
    assert result["coordinate_space"] == "model"
    assert len(result["observations"]) == 3
    np.testing.assert_allclose(result["relative_xyz"], expected, atol=.06)
    assert not np.allclose(result["relative_xyz"], point)
    assert result["quality"]["absolute_accuracy_verified"] is False
    assert result["quality"]["parallax_deg"] > 2


def test_lost_tip_cannot_copy_a_previous_models_position(tmp_path):
    source, target, frames, matrix, point, _ = _rounds(tmp_path)
    for view in target["views"]:
        frames[view["view_id"]] = _frame(tmp_path, view["view_id"], np.full((120, 160, 3), 15, np.uint8), "rotating")
    with pytest.raises(ValueError, match="兩個"):
        track_model_tip(source, target, point, matrix, frames.__getitem__)


def test_cancellation_propagates_without_an_annotation(tmp_path):
    source, target, frames, matrix, point, _ = _rounds(tmp_path)
    def cancel():
        raise RuntimeError("cancelled")
    with pytest.raises(RuntimeError, match="cancelled"):
        track_model_tip(source, target, point, matrix, frames.__getitem__, cancel_check=cancel)
