from __future__ import annotations

import numpy as np
import pytest

from app.analysis.reconstruction import gsplat_trainer as trainer
from app.analysis.reconstruction.dataset_adapter import PreparedRoundDataset, PreparedRoundView
from app.analysis.reconstruction.native_build import configure_native_build
from app.core.exceptions import AnalysisPausedError


@pytest.mark.parametrize("coordinate_unit", ["millimetre", "relative"])
@pytest.mark.parametrize("foreground_only", [False, True])
def test_real_cuda_training_resumes_optimizer_scheduler_and_iteration(tmp_path, monkeypatch, coordinate_unit, foreground_only):
    torch = pytest.importorskip("torch")
    if not torch.cuda.is_available():
        pytest.skip("CUDA is unavailable")
    pytest.importorskip("gsplat")
    configure_native_build()
    matrix = np.array([[16, 0, 8], [0, 16, 8], [0, 0, 1]], dtype=np.float32)
    source = PreparedRoundView(
        view_id="view", camera_id="top", image_name="image.tiff", image_path=tmp_path / "image.tiff",
        valid_mask_path=None, plant_mask_path=None, image_width=16, image_height=16,
        camera_matrix=matrix, world_to_camera_matrix=np.eye(4), source_sha256="fixed-test-pixels",
        angle_deg=None, pose_source="rig_stereo", aruco_reprojection_error_px=None,
    )
    dataset = PreparedRoundDataset(
        analysis_id="analysis-test", round_key="round", root=tmp_path, images_dir=tmp_path,
        masks_dir=tmp_path, database_path=tmp_path / "database.db", sparse_dir=tmp_path,
        metadata_path=tmp_path / "metadata.json", views=(source,),
        coordinate_unit=coordinate_unit,
    )
    random = np.random.default_rng(17)
    points = random.uniform(-10, 10, (64, 3)).astype(np.float32)
    points[:, 2] += 100
    colors = random.uniform(.2, .8, points.shape).astype(np.float32)
    monkeypatch.setattr(trainer, "_load_sparse_points", lambda _: (points, colors))
    monkeypatch.setattr(trainer, "foreground_point_selection", lambda values, _: (
        np.ones(len(values), dtype=bool), {"foreground_kind": "plant"}))
    # Avoid zero orientation gradients in perfectly isotropic test splats.
    # Atomic CUDA reductions otherwise amplify tiny roundoff through Adam.
    monkeypatch.setattr(trainer, "_initial_scales", lambda values: np.tile(
        np.log(np.array([.02, .03, .04], np.float32)), (len(values), 1),
    ))
    pose = np.eye(4, dtype=np.float32)
    pose[2, 3] = 3
    training_view = trainer._TrainingView(
        source=source, image=random.uniform(.2, .8, (16, 16, 3)).astype(np.float32), valid_mask=None,
        loss_weight=np.ones((16, 16), np.float32), camera_matrix=matrix, world_to_camera=pose,
        plant_mask=np.ones((16, 16), bool) if foreground_only else None,
    )
    monkeypatch.setattr(trainer, "_load_training_views", lambda *args, **kwargs: (training_view,))
    settings = {"quality_preset": "preview", "training_iterations": 500, "image_factor": 1, "save_checkpoint": False,
                "use_plant_mask": foreground_only}
    # Foreground recovery includes real MCMC relocation/growth and its random
    # position perturbations. The restored RNG must reproduce the same model.
    first_stop, last_stop = (150, 170) if foreground_only else (10, 20)

    def train_until(directory, stop):
        def progress(stage, fraction, message):
            if round(fraction * 500) >= stop:
                raise AnalysisPausedError("test pause")

        with pytest.raises(AnalysisPausedError):
            trainer.train_gsplat_model(dataset, settings, directory, progress_callback=progress)
        return torch.load(directory / "checkpoint" / "latest.pt", map_location="cpu", weights_only=False)

    paused = train_until(tmp_path / "resumed", first_stop)
    assert paused["step"] == first_stop
    assert paused["format_version"] == 2
    assert paused["coordinate_unit"] == coordinate_unit
    assert paused["coordinate_space"] == ("metric_world_mm" if coordinate_unit == "millimetre" else "model_world_relative")
    assert ("center_world_mm" in paused) is (coordinate_unit == "millimetre")
    assert paused["optimizers"] and paused["scheduler"] and paused["strategy_state"]
    assert "binoms" in paused["strategy_state"]
    assert paused["splats"]["shN"].shape[1:] == (15, 3)
    if foreground_only:
        assert paused["splats"]["means"].shape[0] > 64
    with (tmp_path / "resumed" / "training_steps.csv").open("a") as handle:
        handle.write(f"{first_stop + 1},0,cuda\n{first_stop + 2},0,cuda\n")
    resumed = train_until(tmp_path / "resumed", last_stop)
    reference = train_until(tmp_path / "reference", last_stop)
    assert resumed["step"] == reference["step"] == last_stop
    assert resumed["scheduler"] == reference["scheduler"]
    for name, parameter in reference["splats"].items():
        torch.testing.assert_close(resumed["splats"][name], parameter, rtol=1e-5, atol=1e-6)
        resumed_state = next(iter(resumed["optimizers"][name]["state"].values()))
        reference_state = next(iter(reference["optimizers"][name]["state"].values()))
        for key in ("step", "exp_avg", "exp_avg_sq"):
            torch.testing.assert_close(resumed_state[key], reference_state[key], rtol=1e-5, atol=1e-6)
    rows = (tmp_path / "resumed" / "training_steps.csv").read_text().splitlines()
    assert [int(row.split(",")[0]) for row in rows] == list(range(1, last_stop + 1))
