from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.analysis.reconstruction.constrained_bundle_adjustment import refine_sparse_camera_poses
from app.analysis.reconstruction.dataset_adapter import PreparedRoundDataset, PreparedRoundView


def _scene(tmp_path: Path):
    pycolmap = pytest.importorskip("pycolmap")
    reconstruction = pycolmap.Reconstruction()
    matrix = np.array([[200., 0, 160], [0, 200, 120], [0, 0, 1]])
    points = np.array([[-10., -10, 100], [10, -10, 100], [10, 10, 100], [-10, 10, 100]])
    views = []
    for image_id, camera_id in enumerate(("top", "side", "rotating"), start=1):
        pose = np.eye(4)
        pose[0, 3] = -image_id * 5
        camera = pycolmap.Camera(camera_id=image_id, model="PINHOLE", width=320, height=240, params=[200, 200, 160, 120])
        reconstruction.add_camera_with_trivial_rig(camera)
        camera_points = points + pose[:3, 3]
        pixels = camera_points @ matrix.T
        pixels = pixels[:, :2] / pixels[:, 2, None]
        image = pycolmap.Image(image_id=image_id, camera_id=image_id, name=camera_id, keypoints=pixels)
        reconstruction.add_image_with_trivial_frame(image, pycolmap.Rigid3d(pose[:3]))
        views.append(PreparedRoundView(
            view_id=camera_id, camera_id=camera_id, image_name=camera_id, image_path=tmp_path / camera_id,
            valid_mask_path=None, plant_mask_path=None, image_width=320, image_height=240,
            camera_matrix=matrix.copy(), world_to_camera_matrix=pose, source_sha256="test", angle_deg=None,
            pose_source="rig_stereo", aruco_reprojection_error_px=None,
        ))
    for index, point in enumerate(points):
        track = pycolmap.Track()
        for image_id in range(1, 4):
            track.add_element(image_id, index)
        point_id = reconstruction.add_point3D(point + np.array([.25, 0, 0]), track, np.full(3, 128, np.uint8))
        reconstruction.point3D(point_id).error = 99  # Deliberately stale, plausible cached error.
    dataset = PreparedRoundDataset(
        analysis_id="test", round_key="round", root=tmp_path, images_dir=tmp_path, masks_dir=tmp_path,
        database_path=tmp_path / "db", sparse_dir=tmp_path, metadata_path=tmp_path / "metadata.json", views=tuple(views),
    )
    return pycolmap, reconstruction, dataset, points


@pytest.mark.parametrize("worsens", [False, True])
def test_solver_errors_are_recomputed_and_worse_geometry_is_rejected(tmp_path, monkeypatch, worsens):
    pycolmap, reconstruction, dataset, points = _scene(tmp_path)
    original_poses = [view.world_to_camera_matrix.copy() for view in dataset.views]

    def adjuster(*args):
        candidate = args[-1]

        def solve():
            for point in candidate.points3D.values():
                index = point.track.elements[0].point2D_idx
                point.xyz = points[index] + np.array([10 if worsens else 0, 0, 0])
            return SimpleNamespace(is_solution_usable=lambda: True)

        return SimpleNamespace(solve=solve)

    monkeypatch.setattr(pycolmap, "create_pose_prior_bundle_adjuster", adjuster)
    if worsens:
        with pytest.raises(RuntimeError, match="增加了重投影誤差"):
            refine_sparse_camera_poses(pycolmap, reconstruction, dataset)
    else:
        result = refine_sparse_camera_poses(pycolmap, reconstruction, dataset)
        assert result.quality["initial_reprojection_error_px"] == pytest.approx(.5)
        assert result.quality["final_reprojection_error_px"] == pytest.approx(0, abs=1e-10)
    for view, original in zip(dataset.views, original_poses):
        np.testing.assert_array_equal(view.world_to_camera_matrix, original)
    assert all(point.error == 99 for point in reconstruction.points3D.values())
