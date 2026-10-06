from pathlib import Path
from dataclasses import replace

import cv2
import numpy as np
import pytest

from app.analysis.segmentation.plant_mask import create_plant_mask
from app.analysis.segmentation.reconstruction_mask import create_reconstruction_mask
from app.analysis.reconstruction import gsplat_trainer as trainer
from app.analysis.reconstruction.dataset_adapter import PreparedRoundDataset, PreparedRoundView, prepare_round_dataset
from app.analysis.reconstruction.plant_isolation import foreground_point_selection


def test_dark_green_enclosure_pot_and_detached_lamp_are_not_plant():
    image = np.full((240, 320, 3), (18, 27, 20), dtype=np.uint8)
    cv2.ellipse(image, (160, 100), (40, 15), 0, 0, 360, (40, 180, 60), -1)
    cv2.rectangle(image, (148, 94), (170, 105), (240, 245, 240), -1)
    cv2.line(image, (160, 108), (160, 150), (50, 120, 70), 2)
    cv2.rectangle(image, (130, 158), (190, 200), (30, 60, 120), -1)
    cv2.circle(image, (40, 30), 14, (255, 255, 255), -1)
    mask = create_plant_mask(image).mask
    assert mask[100, 155] == 255  # White leaf highlight connected to green tissue.
    assert mask[138, 160] == 255  # A thin stem survives morphology.
    assert mask[180, 160] == mask[30, 40] == mask[220, 310] == 0
    assert np.count_nonzero(mask) < image.shape[0] * image.shape[1] * .08
    assert not create_plant_mask(np.zeros_like(image)).mask.any()


def test_reconstruction_keeps_dark_pot_and_soil_without_filling_empty_stem_gap():
    image = np.full((240, 320, 3), (18, 27, 20), np.uint8)
    cv2.ellipse(image, (160, 75), (40, 15), 0, 0, 360, (40, 180, 60), -1)
    cv2.line(image, (160, 85), (160, 147), (50, 120, 70), 2)
    cv2.rectangle(image, (117, 150), (203, 197), (5, 6, 5), -1)
    cv2.ellipse(image, (160, 150), (46, 12), 0, 0, 360, (4, 5, 4), -1)
    cv2.ellipse(image, (160, 150), (46, 12), 0, 0, 360, (40, 90, 190), 3)
    cv2.circle(image, (40, 30), 14, (255, 255, 255), -1)
    valid = np.full(image.shape[:2], 255, np.uint8)
    valid[:5] = 0
    plant = create_plant_mask(image).mask
    mask = create_reconstruction_mask(image, plant_mask=plant, valid_pixel_mask=valid)
    cv2.randn(np.empty((100, 100), np.float32), 0, 1)
    np.testing.assert_array_equal(mask, create_reconstruction_mask(image, plant_mask=plant, valid_pixel_mask=valid))
    assert mask[75, 160] == mask[150, 160] == mask[180, 160] == 255
    assert plant[180, 160] == 0  # Biological measurements remain plant-only.
    assert mask[120, 190] == mask[30, 40] == mask[220, 310] == 0
    assert not mask[:5].any()
    assert np.count_nonzero(mask) < mask.size * .15
    assert not create_reconstruction_mask(np.zeros_like(image)).any()


def test_clipped_red_and_green_leaf_channels_still_seed_a_plant():
    image = np.full((120, 160, 3), (12, 18, 14), np.uint8)
    cv2.ellipse(image, (80, 45), (30, 12), 0, 0, 360, (140, 255, 255), -1)
    cv2.rectangle(image, (50, 80), (110, 100), (40, 80, 180), -1)
    mask = create_plant_mask(image).mask
    assert mask[45, 80] == 255 and mask[90, 80] == 0


def test_pot_guided_reconstruction_recovers_white_canopy_without_green_seeds():
    image = np.full((480, 640, 3), (12, 18, 14), np.uint8)
    cv2.ellipse(image, (320, 235), (65, 18), 0, 0, 360, (255, 255, 255), -1)
    cv2.rectangle(image, (274, 355), (366, 400), (4, 6, 4), -1)
    cv2.ellipse(image, (320, 355), (50, 12), 0, 0, 360, (40, 90, 190), 3)
    cv2.circle(image, (320, 40), 20, (255, 255, 255), -1)
    mask = create_reconstruction_mask(image)
    assert mask[235, 320] == 255 and mask[40, 320] == 0
    assert mask[295, 350] == 0


def test_dataset_writes_separate_pot_foreground_and_readonly_source(tmp_path):
    import json
    image = np.full((240, 320, 3), (12, 18, 14), np.uint8)
    cv2.ellipse(image, (160, 80), (35, 12), 0, 0, 360, (40, 180, 60), -1)
    cv2.rectangle(image, (130, 150), (190, 190), (4, 6, 4), -1)
    cv2.ellipse(image, (160, 150), (32, 8), 0, 0, 360, (40, 90, 190), 3)
    path = tmp_path / 'source.tiff'
    cv2.imencode('.tiff', image)[1].tofile(path)
    original = path.read_bytes()
    job = {'analysis_id': 'test', 'round_key': 'test', 'artifact_root': str(tmp_path), 'world_coordinate_unit': 'relative',
           'selected_views': [{'view_id': str(i), 'camera_id': 'rotating', 'undistorted_path': str(path)} for i in range(3)],
           'camera_poses': [{'view_id': str(i), 'valid': True, 'pose_source': 'sfm', 'rotation_matrix': np.eye(3).tolist(),
                             'translation_vector_mm': [i, 0, 0]} for i in range(3)],
           'intrinsics_snapshot': {'rotating': {'analysis_image_width': 320, 'analysis_image_height': 240,
               'undistorted_camera_matrix': [[160, 0, 160], [0, 160, 120], [0, 0, 1]]}}}
    dataset = prepare_round_dataset(job, tmp_path / 'dataset')
    for view in dataset.views:
        assert cv2.imdecode(np.fromfile(view.foreground_mask_path, np.uint8), 0)[170, 160] == 255
        assert cv2.imdecode(np.fromfile(view.plant_mask_path, np.uint8), 0)[170, 160] == 0
    metadata = json.loads(dataset.metadata_path.read_text(encoding='utf8'))
    assert metadata['reconstruction_foreground'] == 'plant_and_pot'
    assert all((dataset.root / v['foreground_mask']).is_file() for v in metadata['views'])
    assert path.read_bytes() == original


def _dataset(tmp_path: Path, size=32):
    intrinsic = np.array([[16., 0, size / 2], [0, 16., size / 2], [0, 0, 1]])
    mask = np.zeros((size, size), np.uint8)
    mask[size // 4:size * 3 // 4, size // 4:size * 3 // 4] = 255
    image = np.full((size, size, 3), 20, np.uint8)
    image[mask > 0] = [40, 180, 80]
    image_path, mask_path = tmp_path / "image.tiff", tmp_path / "mask.png"
    cv2.imencode(".tiff", image)[1].tofile(image_path)
    cv2.imencode(".png", mask)[1].tofile(mask_path)
    views = tuple(PreparedRoundView(
        view_id=str(index), camera_id="rotating", image_name="image.tiff", image_path=image_path,
        valid_mask_path=None, plant_mask_path=mask_path, image_width=size, image_height=size,
        camera_matrix=intrinsic.copy(), world_to_camera_matrix=np.eye(4), source_sha256="test",
        angle_deg=None, pose_source="sfm", aruco_reprojection_error_px=None,
    ) for index in range(2))
    return PreparedRoundDataset(
        analysis_id="test", round_key="round", root=tmp_path, images_dir=tmp_path,
        masks_dir=tmp_path, database_path=tmp_path / "database.db", sparse_dir=tmp_path,
        metadata_path=tmp_path / "metadata.json", views=views, coordinate_unit="relative",
    )


def test_training_uses_only_plant_rgb_and_tracks_background_opacity(tmp_path):
    dataset = _dataset(tmp_path)
    view = trainer._load_training_views(dataset, image_factor=1, center_world_mm=np.zeros(3),
                                        world_scale_mm=1, use_plant_mask_in_loss=True)[0]
    assert view.plant_mask[16, 16] and not view.plant_mask[0, 0]
    assert view.loss_weight[16, 16] == 1 and view.loss_weight[0, 0] == 0
    assert (view.image[0, 0] == 0).all()
    assert view.image[16, 16, 1] > .5


@pytest.mark.parametrize("factor", [2, 8])
def test_small_subject_crop_preserves_resolution_and_camera_projection(tmp_path, factor):
    dataset = _dataset(tmp_path)
    source = dataset.views[0]
    image = np.zeros((960, 1280, 3), np.uint8)
    image[400:550, 600:750] = (30, 150, 60)
    mask = np.zeros(image.shape[:2], np.uint8)
    mask[400:550, 600:750] = 255
    cv2.imencode('.tiff', image)[1].tofile(source.image_path)
    cv2.imencode('.png', mask)[1].tofile(source.plant_mask_path)
    matrix = np.array([[800., 0, 640], [0, 810., 480], [0, 0, 1]])
    source = replace(source, image_width=1280, image_height=960, camera_matrix=matrix)
    dataset = replace(dataset, views=(source,))
    view = trainer._load_training_views(dataset, image_factor=factor, center_world_mm=np.zeros(3),
                                       world_scale_mm=1, use_plant_mask_in_loss=True)[0]
    x0, y0, x1, y1 = view.crop_box
    sx, sy = view.image.shape[1] / (x1 - x0), view.image.shape[0] / (y1 - y0)
    point = np.array([.1, .2, 3])
    original = matrix @ point
    cropped = view.camera_matrix @ point
    np.testing.assert_allclose(cropped[:2] / cropped[2], (original[:2] / original[2] - [x0, y0]) * [sx, sy], atol=1e-5)
    np.testing.assert_array_equal(source.camera_matrix, matrix)
    np.testing.assert_array_equal(view.world_to_camera, np.eye(4))
    assert view.image.shape[1] <= 1280 // factor and view.image.shape[0] <= 960 // factor
    if factor == 2:
        assert sx == sy == 1  # The small plant is no longer halved in standard quality.


def test_foreground_ssim_is_not_diluted_by_empty_enclosure_pixels():
    torch = pytest.importorskip("torch")
    mask = torch.zeros((32, 32), dtype=torch.bool)
    mask[12:20, 12:20] = True
    target = mask[None, ..., None].float().expand(1, 32, 32, 3)
    prediction = target * .5
    original = trainer._ssim_loss(prediction, target, torch, mask)
    larger = torch.nn.functional.pad(prediction.permute(0, 3, 1, 2), (64, 64, 64, 64)).permute(0, 2, 3, 1)
    larger_target = larger * 2
    larger_mask = torch.nn.functional.pad(mask, (64, 64, 64, 64))
    torch.testing.assert_close(trainer._ssim_loss(larger, larger_target, torch, larger_mask), original)
    assert original > .1


def test_shape_regularization_rejects_needles_and_preserves_thin_leaves():
    torch = pytest.importorskip("torch")
    disk = torch.log(torch.tensor([[1., 1., 1e-6]], dtype=torch.float64))
    needle = torch.log(torch.tensor([[1., .01, 1e-6]], dtype=torch.float64)).requires_grad_()
    disk_loss = trainer._gaussian_shape_loss(disk, torch)
    needle_loss = trainer._gaussian_shape_loss(needle, torch)
    assert disk_loss < 1e-5 and needle_loss > 5
    # A thinner normal axis must not be penalized if the two surface axes
    # remain substantial. Reducing the dominant axis or widening the second
    # axis, rather than inflating leaf thickness, must reduce a needle's loss.
    needle_loss.backward()
    assert needle.grad[0, 0] > 0 and needle.grad[0, 1] < 0
    assert abs(needle.grad[0, 2]) < abs(needle.grad[0, 1]) * 1e-6


@pytest.mark.parametrize("offset", [-80., 0., 80.])
def test_shape_regularization_is_scale_invariant_and_finite(offset):
    torch = pytest.importorskip("torch")
    scales = torch.tensor([[0., -2., -12.], [0., -500., -1000.]], dtype=torch.float64)
    shifted = (scales + offset).requires_grad_()
    loss = trainer._gaussian_shape_loss(shifted, torch)
    torch.testing.assert_close(loss, trainer._gaussian_shape_loss(scales, torch))
    torch.testing.assert_close(loss, trainer._gaussian_shape_loss(shifted[:, [2, 0, 1]], torch))
    loss.backward()
    assert torch.isfinite(loss) and torch.isfinite(shifted.grad).all()


def test_saturated_opacities_split_and_export_without_losing_all_vertices(tmp_path):
    torch = pytest.importorskip("torch")
    pytest.importorskip("gsplat")
    from gsplat.strategy.ops import split
    from app.analysis.reconstruction.backends.gsplat_backend import _export_splats
    params = torch.nn.ParameterDict({
        "means": torch.nn.Parameter(torch.tensor([[0., 0., 1.], [1., 0., 1.]])),
        "scales": torch.nn.Parameter(torch.zeros((2, 3))),
        "quats": torch.nn.Parameter(torch.tensor([[1., 0., 0., 0.]]).repeat(2, 1)),
        "opacities": torch.nn.Parameter(torch.tensor([100., -100.])),
        "sh0": torch.nn.Parameter(torch.zeros((2, 1, 3))),
        "shN": torch.nn.Parameter(torch.zeros((2, 3, 3))),
    })
    optimizers = {name: torch.optim.Adam([value]) for name, value in params.items()}
    trainer._bound_opacity_logits(params["opacities"], torch)
    split(params=params, optimizers=optimizers, state={}, mask=torch.ones(2, dtype=torch.bool),
          revised_opacity=True)
    assert torch.isfinite(params["opacities"]).all()
    path = _export_splats(tmp_path / "split.ply", params)
    header = path.read_bytes().split(b"end_header\n", 1)[0]
    assert b"element vertex 4\n" in header
    assert path.stat().st_size > len(header) + 4 * 20 * 4


def test_reconstruction_and_plant_export_use_distinct_masks(tmp_path):
    from app.analysis.reconstruction.backends.gsplat_backend import GsplatRoundResult, _plant_splat_selection
    torch = pytest.importorskip("torch")
    dataset = _dataset(tmp_path)
    foreground = np.zeros((32, 32), np.uint8)
    foreground[4:28, 4:28] = 255
    path = tmp_path / 'foreground.png'
    cv2.imencode('.png', foreground)[1].tofile(path)
    dataset = replace(dataset, views=tuple(replace(v, foreground_mask_path=path) for v in dataset.views))
    points = np.array([[0, 0, 3], [.1, 0, 3], [0, .1, 3], [-.1, 0, 3],
                       [1.8, 0, 3], [-1.8, 0, 3], [0, 1.8, 3], [0, -1.8, 3]], np.float32)
    selected, quality = foreground_point_selection(points, dataset)
    assert selected.all() and quality['foreground_kind'] == 'plant_and_pot'
    splats = {'means': torch.from_numpy(points), 'scales': torch.zeros((8, 3)), 'quats': torch.ones((8, 4)),
              'opacities': torch.zeros(8), 'sh0': torch.zeros((8, 1, 3)), 'shN': torch.zeros((8, 3, 3))}
    training = trainer.GsplatTrainingResult(dataset, splats, np.zeros(3), 1,
                                          500, 500, 0, {'foreground_only': True, 'foreground_kind': 'plant_and_pot'}, None)
    plant = _plant_splat_selection(GsplatRoundResult(training, {}))
    assert plant.tolist() == [True] * 4 + [False] * 4


def test_multiview_plant_filter_rejects_background_in_relative_coordinates(tmp_path):
    dataset = _dataset(tmp_path)
    points = np.array([[0, 0, 3], [.1, 0, 3], [0, .1, 3], [-.1, 0, 3],
                       [2, 0, 3], [0, 2, 3], [0, 0, -3]], dtype=float)
    selection, quality = foreground_point_selection(points, dataset)
    assert selection.tolist() == [True, True, True, True, False, False, False]
    assert quality["plant_point_count"] == 4 and quality["background_point_count"] == 3
    with pytest.raises(ValueError, match="植物遮罩內的三維點不足"):
        foreground_point_selection(points[-3:], dataset)


def test_real_cuda_training_exports_only_multiview_plant_geometry(tmp_path, monkeypatch):
    torch = pytest.importorskip("torch")
    if not torch.cuda.is_available():
        pytest.skip("CUDA is unavailable")
    pytest.importorskip("gsplat")
    from app.analysis.reconstruction.native_build import configure_native_build
    configure_native_build()
    dataset = _dataset(tmp_path)
    random = np.random.default_rng(21)
    plant = random.uniform(-.7, .7, (64, 3)).astype(np.float32)
    plant[:, 2] = 3
    background = np.array([[2, 0, 3], [-2, 0, 3], [0, 2, 3], [0, -2, 3]], np.float32)
    points = np.concatenate((plant, background))
    colors = np.tile([.3, .7, .2], (len(points), 1)).astype(np.float32)
    monkeypatch.setattr(trainer, "_load_sparse_points", lambda _: (points, colors))
    monkeypatch.setattr(trainer, "_initial_scales", lambda values: np.tile(
        np.log(np.array([.08, .10, .12], np.float32)), (len(values), 1)))
    result = trainer.train_gsplat_model(dataset, {
        "quality_preset": "preview", "training_iterations": 500, "image_factor": 1,
        "use_plant_mask": True,
    }, tmp_path / "trained")
    assert result.completed_steps == 500 and result.metrics["foreground_only"]
    assert result.metrics["initial_foreground_selection"]["background_point_count"] == 4
    exported = trainer.world_space_splats(result)["means"].detach().cpu().numpy()
    selected, _ = foreground_point_selection(exported, dataset)
    assert selected.all()
    assert len(exported) == result.metrics["foreground_selection"]["exported_gaussian_count"]
    assert result.metrics['densification_gradient_normalized']
    from app.analysis.reconstruction.backends.gsplat_backend import GsplatBackend, GsplatRoundResult
    path = GsplatBackend().export_gaussians(GsplatRoundResult(result, {}), tmp_path / "model.ply")
    header = path.read_bytes().split(b"end_header\n", 1)[0]
    assert f'element vertex {len(exported)}\n'.encode() in header
