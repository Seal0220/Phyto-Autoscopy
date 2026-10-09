from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np

from app.analysis.image_probe import read_analysis_image
from app.analysis.checkpoints import step_signature

from app.analysis.export.json_export import write_json_atomic
from app.analysis.reconstruction.backend import CancelCheck, ProgressCallback
from app.analysis.reconstruction.dataset_adapter import (
    PreparedRoundDataset,
    PreparedRoundView,
)
from app.analysis.reconstruction.dataset_adapter import _sha256
from app.analysis.reconstruction.plant_isolation import foreground_point_selection


PLANT_TRAINING_VERSION = "mcmc_sh3_v4"


_SH_C0 = 0.28209479177387814
_QUALITY_PRESETS = {
    "preview": {"maximum_steps": 3_000, "image_factor": 4},
    "standard": {"maximum_steps": 10_000, "image_factor": 2},
    "high": {"maximum_steps": 30_000, "image_factor": 1},
}


class GsplatTrainingError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _TrainingView:
    source: PreparedRoundView
    image: np.ndarray
    valid_mask: np.ndarray | None
    loss_weight: np.ndarray | None
    camera_matrix: np.ndarray
    world_to_camera: np.ndarray
    plant_mask: np.ndarray | None = None
    crop_box: tuple[int, int, int, int] | None = None


@dataclass(slots=True)
class GsplatTrainingResult:
    dataset: PreparedRoundDataset
    splats: Any
    center_world_mm: np.ndarray
    world_scale_mm: float
    maximum_steps: int
    completed_steps: int
    duration_seconds: float
    metrics: dict[str, Any]
    checkpoint_path: Path | None


def _read_image(path: Path, flags: int) -> np.ndarray:
    image = read_analysis_image(path, flags)
    if image is None:
        raise GsplatTrainingError(f"模型訓練影像無法解碼：{path.name}")
    return image


def _load_training_views(
    dataset: PreparedRoundDataset,
    *,
    image_factor: int,
    center_world_mm: np.ndarray,
    world_scale_mm: float,
    use_plant_mask_in_loss: bool,
) -> tuple[_TrainingView, ...]:
    views: list[_TrainingView] = []
    for source in dataset.views:
        image = _read_image(source.image_path, cv2.IMREAD_COLOR)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        if image.shape[:2] != (source.image_height, source.image_width):
            raise GsplatTrainingError("模型訓練影像尺寸與相機內參不一致。")
        valid_mask = None
        if source.valid_mask_path is not None:
            mask = _read_image(source.valid_mask_path, cv2.IMREAD_GRAYSCALE)
            if mask.shape != image.shape[:2]:
                raise GsplatTrainingError("有效像素遮罩尺寸與訓練影像不一致。")
            valid_mask = mask > 0
        plant_pixels = None
        x0, y0, x1, y1 = 0, 0, source.image_width, source.image_height
        if use_plant_mask_in_loss:
            foreground_path = source.foreground_mask_path or source.plant_mask_path
            if foreground_path is None:
                raise GsplatTrainingError("植物模型訓練缺少前景遮罩。")
            plant_mask = _read_image(foreground_path, cv2.IMREAD_GRAYSCALE)
            if plant_mask.shape != image.shape[:2]:
                raise GsplatTrainingError("建模前景遮罩尺寸與訓練影像不一致。")
            plant_pixels = plant_mask > 0
            if valid_mask is not None:
                plant_pixels &= valid_mask
            if not plant_pixels.any():
                continue
            yy, xx = np.where(plant_pixels)
            padding = max(12, int(max(np.ptp(xx), np.ptp(yy)) * .15))
            x0, x1 = max(0, int(xx.min()) - padding), min(source.image_width, int(xx.max()) + padding + 1)
            y0, y1 = max(0, int(yy.min()) - padding), min(source.image_height, int(yy.max()) + padding + 1)
        # Spend the preset's pixel budget on the subject. Cropping shifts the
        # principal point; resizing scales both rows by the actual dimensions.
        image = image[y0:y1, x0:x1]
        crop_width, crop_height = x1 - x0, y1 - y0
        resize_scale = min(1., max(1, source.image_width // image_factor) / crop_width,
                           max(1, source.image_height // image_factor) / crop_height)
        width, height = max(1, round(crop_width * resize_scale)), max(1, round(crop_height * resize_scale))
        image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
        if valid_mask is not None:
            valid_mask = cv2.resize(valid_mask[y0:y1, x0:x1].astype(np.uint8), (width, height), interpolation=cv2.INTER_NEAREST) > 0
        if plant_pixels is not None:
            plant_pixels = cv2.resize(plant_pixels[y0:y1, x0:x1].astype(np.uint8), (width, height), interpolation=cv2.INTER_NEAREST) > 0
        image_float = image.astype(np.float32) / 255.0
        loss_weight = (plant_pixels.astype(np.float32) if plant_pixels is not None else
                       valid_mask.astype(np.float32) if valid_mask is not None else np.ones((height, width), np.float32))
        if plant_pixels is not None:
            image_float[~plant_pixels] = 0
        camera_matrix = source.camera_matrix.copy()
        camera_matrix[0, 2] -= x0
        camera_matrix[1, 2] -= y0
        camera_matrix[0, :] *= width / crop_width
        camera_matrix[1, :] *= height / crop_height
        rotation = source.world_to_camera_matrix[:3, :3]
        translation_mm = source.world_to_camera_matrix[:3, 3]
        normalized_pose = np.eye(4, dtype=np.float32)
        normalized_pose[:3, :3] = rotation.astype(np.float32)
        normalized_pose[:3, 3] = (
            (rotation @ center_world_mm + translation_mm)
            / world_scale_mm
        ).astype(np.float32)
        views.append(
            _TrainingView(
                source=source,
                image=image_float,
                valid_mask=valid_mask,
                loss_weight=loss_weight,
                camera_matrix=camera_matrix.astype(np.float32),
                world_to_camera=normalized_pose,
                plant_mask=plant_pixels,
                crop_box=(x0, y0, x1, y1),
            )
        )
    required_fixed = {source.camera_id for source in dataset.views} & {"top", "side"}
    missing_fixed = required_fixed - {view.source.camera_id for view in views}
    if missing_fixed:
        labels = "、".join("俯視" if camera == "top" else "側視" for camera in sorted(missing_fixed))
        raise GsplatTrainingError(f"{labels}固定鏡頭遮罩沒有有效前景，無法加入模型訓練。")
    if not views:
        raise GsplatTrainingError("模型訓練沒有可用的植物影像。")
    return tuple(views)


def _load_sparse_points(dataset: PreparedRoundDataset) -> tuple[np.ndarray, np.ndarray]:
    try:
        import pycolmap
    except ImportError as error:
        raise GsplatTrainingError(
            "尚未安裝 PyCOLMAP，無法載入稀疏初始化點。"
        ) from error
    reconstruction = pycolmap.Reconstruction(dataset.sparse_dir)
    points = list(reconstruction.points3D.values())
    if len(points) < 4:
        raise GsplatTrainingError("稀疏初始化點不足，無法建立三維模型。")
    positions = np.asarray([point.xyz for point in points], dtype=np.float32)
    colors = np.asarray([point.color for point in points], dtype=np.float32)
    return positions, colors / 255.0


def _normalization(points_world_mm: np.ndarray) -> tuple[np.ndarray, float]:
    center = np.median(points_world_mm, axis=0).astype(np.float64)
    radii = np.linalg.norm(points_world_mm - center, axis=1)
    scale = max(float(np.percentile(radii, 90)), 1.0)
    return center, scale


def _initial_scales(points: np.ndarray) -> np.ndarray:
    try:
        from scipy.spatial import cKDTree
    except ImportError as error:
        raise GsplatTrainingError(
            "尚未安裝 SciPy，無法估計 Gaussian 初始尺度。"
        ) from error
    neighbor_count = min(4, len(points))
    distances, _ = cKDTree(points).query(points, k=neighbor_count)
    if neighbor_count == 1:
        mean_distance = np.ones(len(points), dtype=np.float32) * 0.01
    else:
        mean_distance = np.mean(distances[:, 1:], axis=1)
    mean_distance = np.clip(mean_distance, 1e-4, None)
    return np.log(mean_distance)[:, None].repeat(3, axis=1).astype(np.float32)


def _ssim_loss(prediction: Any, target: Any, torch: Any, mask: Any = None) -> Any:
    functional = torch.nn.functional
    prediction = prediction.permute(0, 3, 1, 2)
    target = target.permute(0, 3, 1, 2)
    mu_prediction = functional.avg_pool2d(prediction, 11, 1, 5)
    mu_target = functional.avg_pool2d(target, 11, 1, 5)
    sigma_prediction = (
        functional.avg_pool2d(prediction * prediction, 11, 1, 5)
        - mu_prediction.square()
    )
    sigma_target = (
        functional.avg_pool2d(target * target, 11, 1, 5)
        - mu_target.square()
    )
    covariance = (
        functional.avg_pool2d(prediction * target, 11, 1, 5)
        - mu_prediction * mu_target
    )
    c1 = 0.01 ** 2
    c2 = 0.03 ** 2
    score = (
        (2 * mu_prediction * mu_target + c1)
        * (2 * covariance + c2)
        / (
            (mu_prediction.square() + mu_target.square() + c1)
            * (sigma_prediction + sigma_target + c2)
        )
    )
    if mask is None:
        return 1.0 - score.mean()
    # Empty enclosure pixels must not dilute the structural comparison. Include
    # windows intersecting the silhouette so its edges also contribute.
    weights = functional.max_pool2d(mask[None, None].float(), 11, 1, 5)
    return 1.0 - (score * weights).sum() / (weights.sum().clamp_min(1) * score.shape[1])


def _gaussian_shape_loss(log_scales: Any, torch: Any) -> Any:
    """Discourage needles without thickening naturally flat leaves.

    The covariance eigenvalues are the squared scales. Their effective rank
    distinguishes a disk (two substantial axes) from a needle (one), unlike a
    longest/shortest-axis limit. Based on arxiv.org/abs/2406.11672, Eq. 10.
    Log-space normalization keeps tiny and large Gaussians numerically stable.
    """
    log_probabilities = torch.log_softmax(2 * log_scales, dim=-1)
    entropy = -(log_probabilities.exp() * log_probabilities).sum(dim=-1)
    rank_penalty = torch.relu(-torch.log(torch.expm1(entropy) + 1e-5))
    return rank_penalty.mean()


def _bound_opacity_logits(opacities: Any, torch: Any) -> None:
    # Revised splitting computes logit(1 - sqrt(1 - sigmoid(parent))).
    # Float32 sigmoid rounds a saturated parent to exactly one (or zero),
    # yielding infinite child logits. Keep both endpoints representable before
    # topology changes; this does not impose a visible transparency threshold.
    limit = math.log((1 - 1e-6) / 1e-6)
    with torch.no_grad():
        opacities.clamp_(min=-limit, max=limit)


def _checkpoint(
    path: Path,
    *,
    torch: Any,
    step: int,
    splats: Any,
    center_world_mm: np.ndarray,
    world_scale_mm: float,
    optimizers: Any = None,
    scheduler: Any = None,
    strategy_state: Any = None,
    signature: str = "",
    losses: list[float] | None = None,
    coordinate_unit: str = "millimetre",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(
        {
            "step": step,
            "splats": splats.state_dict(),
            **({"center_world_mm": center_world_mm.tolist(), "world_scale_mm": world_scale_mm}
               if coordinate_unit == "millimetre" else {"center_world": center_world_mm.tolist(), "world_scale": world_scale_mm}),
            "coordinate_space": "metric_world_mm" if coordinate_unit == "millimetre" else "model_world_relative",
            "coordinate_unit": coordinate_unit,
            "format_version": 2,
            "signature": signature,
            "optimizers": {name: optimizer.state_dict() for name, optimizer in (optimizers or {}).items()},
            "scheduler": scheduler.state_dict() if scheduler is not None else None,
            "strategy_state": strategy_state,
            "torch_rng_state": torch.get_rng_state(),
            "cuda_rng_states": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else [],
            "losses": losses or [],
        },
        temporary,
    )
    temporary.replace(path)


def train_gsplat_model(
    dataset: PreparedRoundDataset,
    parameters: Mapping[str, Any],
    output_dir: Path,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> GsplatTrainingResult:
    """Train one Round with gsplat while keeping camera poses immutable.

    Gaussian relocation/growth follows gsplat's documented ``MCMCStrategy``
    public API. Camera poses are tensors without gradients, so training cannot
    change the established world frame or its millimetre scale.
    """

    try:
        import torch
        from gsplat.rendering import rasterization
        from gsplat.strategy import MCMCStrategy
    except ImportError as error:
        raise GsplatTrainingError(
            "尚未安裝可用的 PyTorch／gsplat，無法建立三維模型。"
        ) from error
    if not torch.cuda.is_available():
        raise GsplatTrainingError("目前沒有可用的 CUDA GPU。")

    quality_name = str(parameters.get("quality_preset") or "standard")
    preset = _QUALITY_PRESETS.get(quality_name)
    if preset is None:
        raise GsplatTrainingError("模型品質只能使用預覽、標準或高品質。")
    maximum_steps = int(parameters.get("training_iterations", preset["maximum_steps"]))
    image_factor = int(parameters.get("image_factor", preset["image_factor"]))
    if not 500 <= maximum_steps <= 100000 or image_factor not in {1, 2, 4, 8}:
        raise GsplatTrainingError("模型訓練步數或影像縮小倍率無效。")
    output_dir.mkdir(parents=True, exist_ok=True)
    positions_world_mm, colors = _load_sparse_points(dataset)
    foreground_only = bool(parameters.get("use_plant_mask", True))
    initial_foreground_quality = None
    if foreground_only:
        selection, initial_foreground_quality = foreground_point_selection(positions_world_mm, dataset)
        positions_world_mm, colors = positions_world_mm[selection], colors[selection]
    center_world_mm, world_scale_mm = _normalization(positions_world_mm)
    positions = (
        (positions_world_mm - center_world_mm) / world_scale_mm
    ).astype(np.float32)
    views = _load_training_views(
        dataset,
        image_factor=image_factor,
        center_world_mm=center_world_mm,
        world_scale_mm=world_scale_mm,
        use_plant_mask_in_loss=foreground_only,
    )

    device = torch.device("cuda:0")
    torch.manual_seed(42)
    # Recovery is always available, including when optional diagnostic export
    # was disabled. Legacy weights-only checkpoints cannot restore Adam state.
    checkpoint_path = output_dir / "checkpoint" / "latest.pt"
    signature = step_signature({
        "training_version": PLANT_TRAINING_VERSION,
        **({"geometry_signature": dataset.geometry_signature, "coordinate_unit": dataset.coordinate_unit}
           if dataset.geometry_signature is not None or dataset.coordinate_unit != "millimetre" else {}),
        "parameters": dict(parameters), "center": center_world_mm.tolist(), "scale": world_scale_mm,
        "views": [{"id": view.view_id, "hash": view.source_sha256,
                   "pose": view.world_to_camera_matrix.tolist(), "K": view.camera_matrix.tolist(),
                   "plant_mask": _sha256(view.plant_mask_path) if foreground_only and view.plant_mask_path else None,
                   "foreground_mask": _sha256(view.foreground_mask_path) if foreground_only and view.foreground_mask_path else None,
                   "valid_mask": _sha256(view.valid_mask_path) if view.valid_mask_path else None}
                  for view in dataset.views],
    })
    saved = None
    if checkpoint_path.is_file():
        candidate = torch.load(checkpoint_path, map_location=device, weights_only=False)
        if candidate.get("format_version") == 2 and candidate.get("signature") == signature:
            saved = candidate
    numpy_scales = _initial_scales(positions)
    point_count = len(positions)
    sh0 = ((colors - 0.5) / _SH_C0)[:, None, :]
    splats = torch.nn.ParameterDict({
        "means": torch.nn.Parameter(torch.from_numpy(positions)),
        "scales": torch.nn.Parameter(torch.from_numpy(numpy_scales)),
        "quats": torch.nn.Parameter(
            torch.tensor(
                [[1.0, 0.0, 0.0, 0.0]],
                dtype=torch.float32,
            ).repeat(point_count, 1)
        ),
        "opacities": torch.nn.Parameter(
            torch.full(
                (point_count,),
                float(torch.logit(torch.tensor(0.1))),
            )
        ),
        "sh0": torch.nn.Parameter(torch.from_numpy(sh0.astype(np.float32))),
        "shN": torch.nn.Parameter(
            torch.zeros((point_count, 15, 3), dtype=torch.float32)
        ),
    }).to(device)
    if saved is not None:
        splats = torch.nn.ParameterDict({
            name: torch.nn.Parameter(value.to(device)) for name, value in saved["splats"].items()
        })
    learning_rates = {
        "means": 1.6e-4,
        "scales": 5e-3,
        "quats": 1e-3,
        "opacities": 5e-2,
        "sh0": 2.5e-3,
        "shN": 2.5e-3 / 20,
    }
    optimizers = {
        name: torch.optim.Adam(
            [{"params": splats[name], "lr": learning_rates[name]}],
            eps=1e-15,
        )
        for name in splats.keys()
    }
    scheduler = torch.optim.lr_scheduler.ExponentialLR(
        optimizers["means"],
        gamma=0.01 ** (1.0 / maximum_steps),
    )
    # Published MCMC relocation replenishes dead splats without repeated
    # opacity resets or image-gradient thresholds starving small plant masks.
    strategy = MCMCStrategy(
        verbose=False,
        cap_max=max(point_count, 100_000 if foreground_only else 1_000_000),
        refine_start_iter=min(500, max(50, maximum_steps // 20)),
        refine_stop_iter=int(maximum_steps * 0.85),
        refine_every=100,
    )
    strategy.check_sanity(splats, optimizers)
    strategy_state = strategy.initialize_state()
    if saved is not None:
        for name, optimizer in optimizers.items():
            optimizer.load_state_dict(saved["optimizers"][name])
        scheduler.load_state_dict(saved["scheduler"])
        strategy_state = saved["strategy_state"]
        torch.set_rng_state(saved["torch_rng_state"].cpu())
        torch.cuda.set_rng_state_all([state.cpu() for state in saved["cuda_rng_states"]])

    tensors = []
    for view in views:
        tensors.append({
            "pixels": torch.from_numpy(view.image).to(device),
            "mask": (
                torch.from_numpy(view.valid_mask).to(device)
                if view.valid_mask is not None
                else None
            ),
            "loss_weight": torch.from_numpy(
                view.loss_weight,
            ).to(device),
            "plant_mask": torch.from_numpy(view.plant_mask).to(device) if view.plant_mask is not None else None,
            "densification_gradient_scale": float(np.mean(view.loss_weight > 0)),
            "K": torch.from_numpy(view.camera_matrix).to(device)[None],
            "viewmat": torch.from_numpy(view.world_to_camera).to(device)[None],
        })

    losses: list[float] = list(saved.get("losses", [])) if saved is not None else []
    started = time.monotonic()
    completed_steps = int(saved["step"]) if saved is not None else 0
    resumed_from_step = completed_steps
    iteration_path = output_dir / "training_steps.csv"
    if iteration_path.is_file():
        # A forced shutdown may leave iteration records newer than the latest
        # tensor snapshot. Discard those records before replaying those steps.
        retained = []
        if saved is not None:
            for row in iteration_path.read_text(encoding="utf-8").splitlines():
                try:
                    if int(row.split(",", 1)[0]) <= completed_steps:
                        retained.append(row)
                except ValueError:
                    continue
        iteration_path.write_text("".join(f"{row}\n" for row in retained), encoding="utf-8")
    report_every = max(10, maximum_steps // 200)
    checkpoint_every = max(500, maximum_steps // 10)

    def persist_checkpoint() -> None:
        _checkpoint(
            checkpoint_path, torch=torch, step=completed_steps, splats=splats,
            center_world_mm=center_world_mm, world_scale_mm=world_scale_mm,
            optimizers=optimizers, scheduler=scheduler, strategy_state=strategy_state,
            signature=signature, losses=losses, coordinate_unit=dataset.coordinate_unit,
        )

    def check_cancellation_with_checkpoint() -> None:
        if cancel_check is None:
            return
        try:
            cancel_check()
        except BaseException:
            if checkpoint_path is not None and completed_steps > 0:
                persist_checkpoint()
            raise

    for step in range(completed_steps, maximum_steps):
        check_cancellation_with_checkpoint()
        item = tensors[step % len(tensors)]
        pixels = item["pixels"][None]
        height, width = pixels.shape[1:3]
        renders, alphas, info = rasterization(
            means=splats["means"],
            quats=splats["quats"],
            scales=torch.exp(splats["scales"]),
            opacities=torch.sigmoid(splats["opacities"]),
            colors=torch.cat([splats["sh0"], splats["shN"]], dim=1),
            viewmats=item["viewmat"],
            Ks=item["K"],
            width=width,
            height=height,
            sh_degree=min(3, step // 1000),
            packed=False,
            absgrad=False,
            rasterize_mode="antialiased",
            near_plane=0.01,
            far_plane=100.0,
        )
        colors_rendered = renders[..., :3]
        mask = item["mask"]
        loss_weight = item["loss_weight"]
        if bool((loss_weight > 0).any()):
            per_pixel_l1 = torch.abs(
                colors_rendered[0] - pixels[0]
            ).mean(dim=-1)
            l1_loss = (
                per_pixel_l1 * loss_weight
            ).sum() / loss_weight.sum().clamp_min(1.0)
        else:
            raise GsplatTrainingError(
                "模型訓練遮罩沒有任何有效像素。"
            )
        plant_mask = item["plant_mask"]
        ssim_mask = plant_mask if plant_mask is not None else mask
        if ssim_mask is not None and bool(ssim_mask.any()):
            mask_float = ssim_mask[None, ..., None].float()
            ssim_prediction = colors_rendered * mask_float
            ssim_target = pixels * mask_float
        else:
            ssim_prediction = colors_rendered
            ssim_target = pixels
        ssim_loss = _ssim_loss(ssim_prediction, ssim_target, torch, ssim_mask)
        loss = 0.8 * l1_loss + 0.2 * ssim_loss
        if plant_mask is not None:
            # RGB alone cannot distinguish empty black space from opaque black
            # splats. Supervise opacity so the background stays empty geometry.
            alpha = alphas[0, ..., 0]
            foreground_alpha_loss = (1 - alpha[plant_mask]).mean()
            background_mask = ~plant_mask if mask is None else mask & ~plant_mask
            background_alpha_loss = alpha[background_mask].mean() if bool(background_mask.any()) else alpha.sum() * 0
            loss = loss + .1 * (foreground_alpha_loss + background_alpha_loss)
        # Regularizers specified by the MCMC paper; no imposed leaf shape.
        loss = loss + .01 * torch.sigmoid(splats["opacities"]).mean()
        loss = loss + .01 * torch.exp(splats["scales"]).mean()
        if not torch.isfinite(loss):
            raise GsplatTrainingError("模型損失出現非有限值，已停止該 Round。")
        loss.backward()
        for optimizer in optimizers.values():
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)
        scheduler.step()
        _bound_opacity_logits(splats["opacities"], torch)
        strategy.step_post_backward(
            params=splats,
            optimizers=optimizers,
            state=strategy_state,
            step=step,
            info=info,
            lr=optimizers["means"].param_groups[0]["lr"],
        )
        completed_steps = step + 1
        losses.append(float(loss.detach().cpu()))
        # One record per completed optimizer iteration. Large tensor snapshots
        # are periodic and also written immediately on cooperative pause.
        with iteration_path.open("a", encoding="utf-8") as iteration_log:
            iteration_log.write(f"{completed_steps},{losses[-1]:.9g},cuda\n")
        if len(losses) > 100:
            losses.pop(0)
        if checkpoint_path is not None and (
            completed_steps % checkpoint_every == 0
            or completed_steps == maximum_steps
        ):
            persist_checkpoint()
        if progress_callback is not None and (
            completed_steps % report_every == 0
            or completed_steps == maximum_steps
        ):
            try:
                progress_callback(
                    "reconstructing_round_model",
                    completed_steps / maximum_steps,
                    f"三維模型訓練 {completed_steps}/{maximum_steps}",
                )
            except BaseException:
                if checkpoint_path is not None:
                    persist_checkpoint()
                raise

    foreground_quality = None
    if foreground_only:
        check_cancellation_with_checkpoint()
        world_points = (splats["means"].detach() * world_scale_mm + torch.as_tensor(
            center_world_mm, dtype=splats["means"].dtype, device=device,
        )).cpu().numpy()
        selection, foreground_quality = foreground_point_selection(world_points, dataset)
        selection &= torch.sigmoid(splats["opacities"]).detach().cpu().numpy() >= .005
        if int(selection.sum()) < 4:
            raise GsplatTrainingError("植物 Gaussian 有效點不足，請檢查植物遮罩。")
        foreground_quality["exported_gaussian_count"] = int(selection.sum())
        selection_tensor = torch.from_numpy(selection).to(device)
        splats = torch.nn.ParameterDict({
            name: torch.nn.Parameter(value.detach()[selection_tensor]) for name, value in splats.items()
        })
    duration = time.monotonic() - started
    metrics = {
        "quality_preset": quality_name,
        "image_factor": image_factor,
        "mean_recent_training_loss": (
            float(np.mean(losses)) if losses else None
        ),
        "initial_sparse_point_count": point_count,
        "gaussian_count": int(splats["means"].shape[0]),
        "coordinate_space": "metric_world_mm" if dataset.coordinate_unit == "millimetre" else "model_world_relative",
        "coordinate_unit": dataset.coordinate_unit,
        "camera_poses_fixed": True,
        "plant_mask_in_training_loss": bool(
            parameters.get("use_plant_mask", True)
        ),
        "training_version": PLANT_TRAINING_VERSION,
        "foreground_only": foreground_only,
        "foreground_kind": "plant_and_pot" if foreground_only and any(view.foreground_mask_path is not None for view in dataset.views) else "plant" if foreground_only else "scene",
        "training_camera_counts": {camera: sum(view.source.camera_id == camera for view in views)
                                   for camera in ("top", "side", "rotating")},
        "training_views": [{"view_id": view.source.view_id, "camera_id": view.source.camera_id, "crop_box": view.crop_box,
                            "width": view.image.shape[1], "height": view.image.shape[0]} for view in views],
        "training_method": "3dgs_mcmc",
        "strategy": "MCMCStrategy",
        "strategy_repository_url": "https://github.com/ubc-vision/3dgs-mcmc",
        "gaussian_budget": strategy.cap_max,
        "spherical_harmonics_degree": min(3, (completed_steps - 1) // 1000),
        "rasterize_mode": "antialiased",
        "opacity_regularization": .01,
        "scale_regularization": .01,
        "initial_foreground_selection": initial_foreground_quality,
        "foreground_selection": foreground_quality,
        **({"world_center_mm": center_world_mm.tolist(), "internal_world_scale_mm": world_scale_mm}
           if dataset.coordinate_unit == "millimetre" else {"world_center": center_world_mm.tolist(), "internal_world_scale": world_scale_mm}),
        "resumed_from_step": resumed_from_step,
    }
    write_json_atomic(output_dir / "training_metrics.json", metrics)
    return GsplatTrainingResult(
        dataset=dataset,
        splats=splats,
        center_world_mm=center_world_mm,
        world_scale_mm=world_scale_mm,
        maximum_steps=maximum_steps,
        completed_steps=completed_steps,
        duration_seconds=duration,
        metrics=metrics,
        checkpoint_path=checkpoint_path,
    )


def world_space_splats(result: GsplatTrainingResult) -> dict[str, Any]:
    import torch

    scale = float(result.world_scale_mm)
    center = torch.as_tensor(
        result.center_world_mm,
        dtype=result.splats["means"].dtype,
        device=result.splats["means"].device,
    )
    return {
        "means": result.splats["means"] * scale + center,
        "scales": result.splats["scales"] + math.log(scale),
        "quats": result.splats["quats"],
        "opacities": result.splats["opacities"],
        "sh0": result.splats["sh0"],
        "shN": result.splats["shN"],
    }
