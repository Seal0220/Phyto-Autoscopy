from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from app.analysis.pose_alignment.stable_features import augment_stable_tracks, localise_stable_camera, pot_rim_region, stable_camera_pose
from app.analysis.reconstruction import reference_sfm


def _pot():
    image = np.full((256, 256, 3), 12, np.uint8)
    soil = np.random.default_rng(20).integers(25, 150, (256, 256), dtype=np.uint8)
    mask = np.zeros((256, 256), np.uint8)
    cv2.circle(mask, (128, 128), 70, 255, -1)
    image[mask > 0] = np.repeat(soil[:, :, None], 3, axis=2)[mask > 0]
    cv2.circle(image, (128, 128), 70, (35, 80, 210), 6)
    cv2.ellipse(image, (128, 97), (35, 15), 20, 0, 360, (35, 200, 60), -1)
    cv2.circle(image, (225, 22), 15, (255, 255, 255), -1)
    return image, np.full(mask.shape, 255, np.uint8)


def test_rim_normalization_excludes_leaves_and_detached_lamps():
    image, valid = _pot()
    gray, mask, affine, quality = pot_rim_region(image, valid)
    assert gray.shape == mask.shape == (384, 384)
    np.testing.assert_allclose(quality["ellipse"][0], [128, 128], atol=1)
    for point in ([128, 97], [225, 22]):
        x, y = np.rint(affine[:, :2] @ point + affine[:, 2]).astype(int)
        assert not (0 <= x < 384 and 0 <= y < 384 and mask[y, x])
    assert np.count_nonzero(mask) > 20000
    with pytest.raises(ValueError, match="盆緣"):
        pot_rim_region(np.full_like(image, 20), valid)


def test_texture_matching_localizes_fixed_camera_in_original_model_frame():
    image, valid = _pot()
    region = pot_rim_region(image, valid)
    keys, _ = cv2.SIFT_create(nfeatures=2500, contrastThreshold=.02).detectAndCompute(region[0], region[1])
    inverse = cv2.invertAffineTransform(region[2])
    pixels = np.asarray([key.pt for key in keys]) @ inverse[:, :2].T + inverse[:, 2]
    objects = np.column_stack([(pixels - 128) / 100, np.zeros(len(pixels))])
    source = {"region": region, "pixels": pixels, "objects": objects, "point_ids": np.arange(len(keys))}
    matrix = np.array([[400., 0, 128], [0, 400, 128], [0, 0, 1]])
    target = cv2.warpAffine(image, np.float32([[.85, 0, 20], [0, .85, 15]]), (256, 256))
    pose, quality = localise_stable_camera(target, valid, matrix, [source])
    np.testing.assert_allclose(pose[:3, :3], np.eye(3), atol=.03)
    np.testing.assert_allclose(pose[:3, 3], [.8 / 85, -4.2 / 85, 4 / .85], atol=.08)
    assert quality["holdout_count"] >= 4
    assert quality["holdout_p75_error_px"] < 1
    assert quality["absolute_accuracy_verified"] is False


def test_independent_holdout_rejects_wrong_correspondences():
    objects = np.random.default_rng(18).uniform(-.3, .3, (32, 3))
    matrix = np.array([[400., 0, 128], [0, 400, 128], [0, 0, 1]])
    pixels = cv2.projectPoints(objects, np.zeros(3), np.array([0., 0., 3.]), matrix, None)[0].reshape(-1, 2)
    pixels[::4] += [15, -10]
    with pytest.raises(ValueError, match="保留特徵"):
        stable_camera_pose(objects, pixels, matrix)


def test_soil_tracks_acquire_depth_from_three_frozen_views_without_mutating_sources():
    image, valid = _pot()
    matrix = np.array([[400., 0, 128], [0, 400, 128], [0, 0, 1]])
    sources = []
    for index, shift in enumerate((-.1, 0., .1)):
        pose = np.eye(4)
        pose[:3, 3] = [shift, 0, 4]
        warped = cv2.warpAffine(image, np.float32([[1, 0, shift * 100], [0, 1, 0]]), (256, 256))
        sources.append({"region": pot_rim_region(warped, valid), "pose": pose, "angle_deg": index * 10,
                        "pixels": [], "objects": [], "point_ids": []})
    result = augment_stable_tracks(sources, matrix)
    assert min(len(source["objects"]) for source in result) >= 16
    assert all(not source["objects"] for source in sources)
    np.testing.assert_allclose(np.asarray(result[0]["objects"])[:, 2], 0, atol=.05)
    assert set(result[0]["point_ids"]) == set(result[1]["point_ids"])


@pytest.mark.parametrize("camera", ["top", "side", "rotating"])
def test_missing_fixed_camera_gets_automatic_fallback_without_moving_orbit(monkeypatch, camera):
    image, valid = _pot()
    source_view = {"view_id": "arm", "camera_id": "rotating", "undistorted_path": "arm.png", "valid_mask_path": "mask.png"}
    target_view = {"view_id": "target", "camera_id": camera, "undistorted_path": "target.png", "valid_mask_path": "mask.png"}
    points = {i: SimpleNamespace(xyz=np.array([i, i % 3, i % 5], float), error=1,
                                track=SimpleNamespace(length=lambda: 3)) for i in range(20)}
    orbit = SimpleNamespace(image_id=1, name=reference_sfm.reference_image_name(source_view),
        cam_from_world=lambda: SimpleNamespace(matrix=lambda: np.eye(4)[:3]),
        points2D=[SimpleNamespace(xy=[128 + i, 128], point3D_id=i, has_point3D=lambda: True) for i in points])
    reconstruction = SimpleNamespace(images={1: orbit}, reg_image_ids=lambda: [1], points3D=points)
    original = {i: point.xyz.copy() for i, point in points.items()}
    registered = [{**source_view, "pose": np.eye(4).tolist()}]
    monkeypatch.setattr(reference_sfm, "read_analysis_image", lambda path, flag: valid if flag == cv2.IMREAD_GRAYSCALE else image)
    calls = []
    def localize(*args, **kwargs):
        calls.append(args)
        return np.eye(4), {"inlier_indices": list(range(16))}
    monkeypatch.setattr(reference_sfm, "localise_stable_camera", localize)
    localized, quality = reference_sfm.localise_unregistered_fixed(reconstruction, registered, [source_view, target_view],
        {name: {"undistorted_camera_matrix": np.eye(3)} for name in (camera, "rotating")},
        progress=lambda *args: None, cancel_check=lambda: None)
    assert len(calls) == len(localized) == 1
    assert localized[0]["camera_id"] == camera
    assert quality["cameras"][camera]["status"] == "completed"
    assert len(registered) == 1
    for i, point in points.items():
        np.testing.assert_array_equal(point.xyz, original[i])
