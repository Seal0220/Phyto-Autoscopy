from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.analysis.checkpoints import StepJournal
from app.analysis.pose_alignment.markerless_pose import _features
from app.analysis.reconstruction.constrained_bundle_adjustment import refine_sparse_camera_poses
from app.analysis.reconstruction.dataset_adapter import PreparedRoundDataset, PreparedRoundView
from app.analysis.reconstruction.sparse_initializer import initialize_sparse_geometry


def _cuda_colmap():
    module = pytest.importorskip("pycolmap")
    if not module.has_cuda:
        pytest.skip("PyCOLMAP CUDA build is unavailable")
    return module


def _dataset(tmp_path: Path):
    images = tmp_path / "images"
    masks = tmp_path / "masks"
    sparse = tmp_path / "sparse"
    for directory in (images, masks, sparse):
        directory.mkdir()
    matrix = np.array([[200., 0, 160], [0, 200, 120], [0, 0, 1]])
    random = np.random.default_rng(7)
    texture = cv2.GaussianBlur(random.integers(0, 256, (240, 320), np.uint8), (3, 3), .5)
    views = []
    for index, (camera_id, center) in enumerate((
        ("top", (0, 0, 0)), ("side", (10, 0, 0)), ("rotating", (3, 8, 0)),
    ), start=1):
        pose = np.eye(4)
        pose[:3, 3] = -np.asarray(center)
        image = cv2.warpAffine(texture, np.array([[1., 0, -2 * center[0]], [0, 1, -2 * center[1]]]), (320, 240))
        name = f"{camera_id}.tiff"
        assert cv2.imwrite(str(images / name), image, [cv2.IMWRITE_TIFF_COMPRESSION, 5])
        assert cv2.imwrite(str(masks / f"{name}.png"), np.full((240, 320), 255, np.uint8))
        views.append(PreparedRoundView(
            view_id=str(index), camera_id=camera_id, image_name=name, image_path=images / name,
            valid_mask_path=masks / f"{name}.png", plant_mask_path=None, image_width=320, image_height=240,
            camera_matrix=matrix, world_to_camera_matrix=pose, source_sha256=f"test-{index}",
            angle_deg=None, pose_source="rig_stereo", aruco_reprojection_error_px=None,
        ))
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps({"views": [{"view_id": view.view_id} for view in views]}), encoding="utf-8")
    return PreparedRoundDataset(
        analysis_id="test", round_key="round", root=tmp_path, images_dir=images, masks_dir=masks,
        database_path=tmp_path / "database.db", sparse_dir=sparse, metadata_path=metadata, views=tuple(views),
    )


def test_native_opencv_cuda_orb_is_used_and_features_are_saved(tmp_path):
    if cv2.cuda.getCudaEnabledDeviceCount() == 0 or not hasattr(cv2, "cuda_ORB"):
        pytest.skip("OpenCV CUDA build is unavailable")
    root = tmp_path / "analysis_test"
    root.mkdir()
    dataset = _dataset(root)
    path = dataset.views[0].image_path
    frame = {"file_path": str(path)}
    first = _features(frame, 500)
    assert first is not None and len(first[1]) >= 8
    with StepJournal(root) as journal:
        saved = journal.get("extracting_features", str(path))
    assert saved["backend"] == "cuda"
    second = _features(frame, 500)
    np.testing.assert_array_equal(first[2], second[2])


def test_native_colmap_cuda_sift_matching_and_constrained_adjustment(tmp_path, monkeypatch):
    pycolmap = _cuda_colmap()
    dataset = _dataset(tmp_path)
    original_poses = [view.world_to_camera_matrix.copy() for view in dataset.views]
    result = initialize_sparse_geometry(dataset, requested_device="cuda", use_constrained_bundle_adjustment=True)
    assert result["quality"]["point_count"] >= 4
    assert result["quality"]["triangulation_pose_difference"] < 1e-6
    assert result["quality"]["bundle_adjustment"]["status"] == "completed"
    assert result["quality"]["bundle_adjustment"]["backend"] == "cuda"
    with StepJournal(dataset.root) as journal:
        assert journal.get("extracting_features", "round")["backend"] == "cuda"
        assert journal.get("matching_features", "round")["backend"] == "cuda"
    # Completed geometry is reusable without extracting or matching again.
    # A restarted worker builds the dataset from the frozen input poses.
    for view, original in zip(dataset.views, original_poses):
        view.world_to_camera_matrix[:] = original
    def unexpected_extraction(**kwargs):
        raise AssertionError("Completed CUDA features must be reused")
    monkeypatch.setattr(pycolmap, "extract_features", unexpected_extraction)
    repeated = initialize_sparse_geometry(dataset, requested_device="cuda", use_constrained_bundle_adjustment=True)
    assert repeated["quality"]["point_count"] == result["quality"]["point_count"]


def test_cuda_bundle_adjustment_preserves_fixed_poses_and_prior_api(tmp_path):
    pycolmap = _cuda_colmap()
    dataset = _dataset(tmp_path)
    random = np.random.default_rng(13)
    points = random.uniform((-20, -20, 80), (20, 20, 120), (64, 3))
    reconstruction = pycolmap.Reconstruction()
    for index, view in enumerate(dataset.views, start=1):
        camera = pycolmap.Camera(camera_id=index, model="PINHOLE", width=320, height=240, params=[200, 200, 160, 120])
        reconstruction.add_camera_with_trivial_rig(camera)
        pixels = points + view.world_to_camera_matrix[:3, 3]
        pixels = pixels @ view.camera_matrix.T
        pixels = pixels[:, :2] / pixels[:, 2, None]
        image = pycolmap.Image(image_id=index, camera_id=index, name=view.image_name, keypoints=pixels)
        reconstruction.add_image_with_trivial_frame(image, pycolmap.Rigid3d(view.world_to_camera_matrix[:3]))
    for point_index, point in enumerate(points):
        track = pycolmap.Track()
        for image_id in range(1, 4):
            track.add_element(image_id, point_index)
        reconstruction.add_point3D(point + random.normal(0, .05, 3), track, np.full(3, 128, np.uint8))
    original = [view.world_to_camera_matrix.copy() for view in dataset.views]
    result = refine_sparse_camera_poses(pycolmap, reconstruction, dataset)
    assert result.quality["status"] == "completed"
    assert result.quality["gpu_requested"]
    assert result.quality["backend"] == "cuda"
    for index in (0, 1):
        np.testing.assert_allclose(dataset.views[index].world_to_camera_matrix, original[index], atol=1e-6)
    assert result.quality["final_reprojection_error_px"] <= result.quality["initial_reprojection_error_px"]
