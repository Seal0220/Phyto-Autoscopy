from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np

from app.analysis.export.json_export import write_json_atomic
from app.analysis.reconstruction.backend import CancelCheck, ProgressCallback
from app.analysis.reconstruction.dataset_adapter import (
    PreparedRoundDataset,
    PreparedRoundView,
)


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
    camera_matrix: np.ndarray
    world_to_camera: np.ndarray


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
    encoded = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(encoded, flags)
    if image is None:
        raise GsplatTrainingError(f"模型訓練影像無法解碼：{path.name}")
    return image


def _load_training_views(
    dataset: PreparedRoundDataset,
    *,
    image_factor: int,
    center_world_mm: np.ndarray,
    world_scale_mm: float,
) -> tuple[_TrainingView, ...]:
    views: list[_TrainingView] = []
    for source in dataset.views:
        image = _read_image(source.image_path, cv2.IMREAD_COLOR)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        width = max(1, source.image_width // image_factor)
        height = max(1, source.image_height // image_factor)
        if (image.shape[1], image.shape[0]) != (width, height):
            image = cv2.resize(
                image,
                (width, height),
                interpolation=cv2.INTER_AREA,
            )
        image_float = image.astype(np.float32) / 255.0

        valid_mask = None
        if source.valid_mask_path is not None:
            mask = _read_image(source.valid_mask_path, cv2.IMREAD_GRAYSCALE)
            if (mask.shape[1], mask.shape[0]) != (width, height):
                mask = cv2.resize(
                    mask,
                    (width, height),
                    interpolation=cv2.INTER_NEAREST,
                )
            valid_mask = mask > 0

        camera_matrix = source.camera_matrix.copy()
        camera_matrix[0, :] /= image_factor
        camera_matrix[1, :] /= image_factor
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
                camera_matrix=camera_matrix.astype(np.float32),
                world_to_camera=normalized_pose,
            )
        )
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


def _ssim_loss(prediction: Any, target: Any, torch: Any) -> Any:
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
    return 1.0 - score.mean()


def _checkpoint(
    path: Path,
    *,
    torch: Any,
    step: int,
    splats: Any,
    center_world_mm: np.ndarray,
    world_scale_mm: float,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(
        {
            "step": step,
            "splats": splats.state_dict(),
            "center_world_mm": center_world_mm.tolist(),
            "world_scale_mm": world_scale_mm,
            "coordinate_space": "aruco_world_mm",
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
    """Train one Round with gsplat while keeping ArUco poses immutable.

    The optimizer structure follows gsplat's documented ``DefaultStrategy``
    public API. Camera poses are tensors without gradients, so training cannot
    change the ArUco world frame or its millimetre scale.
    """

    try:
        import torch
        from gsplat.rendering import rasterization
        from gsplat.strategy import DefaultStrategy
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
    maximum_steps = int(preset["maximum_steps"])
    image_factor = int(preset["image_factor"])
    output_dir.mkdir(parents=True, exist_ok=True)
    positions_world_mm, colors = _load_sparse_points(dataset)
    center_world_mm, world_scale_mm = _normalization(positions_world_mm)
    positions = (
        (positions_world_mm - center_world_mm) / world_scale_mm
    ).astype(np.float32)
    views = _load_training_views(
        dataset,
        image_factor=image_factor,
        center_world_mm=center_world_mm,
        world_scale_mm=world_scale_mm,
    )

    device = torch.device("cuda:0")
    torch.manual_seed(42)
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
            torch.zeros((point_count, 3, 3), dtype=torch.float32)
        ),
    }).to(device)
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
    strategy = DefaultStrategy(verbose=False)
    strategy.refine_start_iter = min(500, max(50, maximum_steps // 20))
    strategy.refine_stop_iter = int(maximum_steps * 0.75)
    strategy.refine_every = max(50, maximum_steps // 100)
    strategy.reset_every = max(500, maximum_steps // 10)
    strategy.check_sanity(splats, optimizers)
    strategy_state = strategy.initialize_state(scene_scale=1.0)

    tensors = []
    for view in views:
        tensors.append({
            "pixels": torch.from_numpy(view.image).to(device),
            "mask": (
                torch.from_numpy(view.valid_mask).to(device)
                if view.valid_mask is not None
                else None
            ),
            "K": torch.from_numpy(view.camera_matrix).to(device)[None],
            "viewmat": torch.from_numpy(view.world_to_camera).to(device)[None],
        })

    checkpoint_path = (
        output_dir / "checkpoint" / "latest.pt"
        if bool(parameters.get("save_checkpoint", True))
        else None
    )
    losses: list[float] = []
    started = time.monotonic()
    completed_steps = 0
    report_every = max(10, maximum_steps // 200)
    checkpoint_every = max(500, maximum_steps // 10)

    def check_cancellation_with_checkpoint() -> None:
        if cancel_check is None:
            return
        try:
            cancel_check()
        except BaseException:
            if checkpoint_path is not None and completed_steps > 0:
                _checkpoint(
                    checkpoint_path,
                    torch=torch,
                    step=completed_steps,
                    splats=splats,
                    center_world_mm=center_world_mm,
                    world_scale_mm=world_scale_mm,
                )
            raise

    for step in range(maximum_steps):
        check_cancellation_with_checkpoint()
        item = tensors[step % len(tensors)]
        pixels = item["pixels"][None]
        height, width = pixels.shape[1:3]
        renders, _, info = rasterization(
            means=splats["means"],
            quats=splats["quats"],
            scales=torch.exp(splats["scales"]),
            opacities=torch.sigmoid(splats["opacities"]),
            colors=torch.cat([splats["sh0"], splats["shN"]], dim=1),
            viewmats=item["viewmat"],
            Ks=item["K"],
            width=width,
            height=height,
            sh_degree=1,
            packed=False,
            absgrad=bool(strategy.absgrad),
            near_plane=0.01,
            far_plane=100.0,
        )
        colors_rendered = renders[..., :3]
        strategy.step_pre_backward(
            params=splats,
            optimizers=optimizers,
            state=strategy_state,
            step=step,
            info=info,
        )
        mask = item["mask"]
        if mask is not None and bool(mask.any()):
            l1_loss = torch.abs(
                colors_rendered[0][mask] - pixels[0][mask]
            ).mean()
            mask_float = mask[None, ..., None].float()
            ssim_prediction = colors_rendered * mask_float
            ssim_target = pixels * mask_float
        else:
            l1_loss = torch.abs(colors_rendered - pixels).mean()
            ssim_prediction = colors_rendered
            ssim_target = pixels
        ssim_loss = _ssim_loss(ssim_prediction, ssim_target, torch)
        loss = 0.8 * l1_loss + 0.2 * ssim_loss
        if not torch.isfinite(loss):
            raise GsplatTrainingError("模型損失出現非有限值，已停止該 Round。")
        loss.backward()
        for optimizer in optimizers.values():
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)
        scheduler.step()
        strategy.step_post_backward(
            params=splats,
            optimizers=optimizers,
            state=strategy_state,
            step=step,
            info=info,
            packed=False,
        )
        completed_steps = step + 1
        losses.append(float(loss.detach().cpu()))
        if len(losses) > 100:
            losses.pop(0)
        if checkpoint_path is not None and (
            completed_steps % checkpoint_every == 0
            or completed_steps == maximum_steps
        ):
            _checkpoint(
                checkpoint_path,
                torch=torch,
                step=completed_steps,
                splats=splats,
                center_world_mm=center_world_mm,
                world_scale_mm=world_scale_mm,
            )
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
                    _checkpoint(
                        checkpoint_path,
                        torch=torch,
                        step=completed_steps,
                        splats=splats,
                        center_world_mm=center_world_mm,
                        world_scale_mm=world_scale_mm,
                    )
                raise

    duration = time.monotonic() - started
    metrics = {
        "quality_preset": quality_name,
        "image_factor": image_factor,
        "mean_recent_training_loss": (
            float(np.mean(losses)) if losses else None
        ),
        "initial_sparse_point_count": point_count,
        "gaussian_count": int(splats["means"].shape[0]),
        "coordinate_space": "aruco_world_mm",
        "camera_poses_fixed": True,
        "world_center_mm": center_world_mm.tolist(),
        "internal_world_scale_mm": world_scale_mm,
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
