from pathlib import Path

import cv2
import numpy as np
import pytest

from app.analysis.segmentation.plant_mask import create_plant_mask
from app.analysis.reconstruction import gsplat_trainer as trainer
from app.analysis.reconstruction.dataset_adapter import PreparedRoundDataset, PreparedRoundView
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
