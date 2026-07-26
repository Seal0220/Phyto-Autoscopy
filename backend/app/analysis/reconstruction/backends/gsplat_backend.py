from __future__ import annotations

import importlib.metadata
import json
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Any, Mapping

import cv2
import numpy as np

from app.analysis.reconstruction.backend import CancelCheck, ProgressCallback
from app.analysis.reconstruction.dataset_adapter import (
    PreparedRoundDataset,
    prepare_round_dataset,
)
from app.analysis.reconstruction.environment import reconstruction_environment
from app.analysis.reconstruction.gsplat_trainer import (
    GsplatTrainingResult,
    train_gsplat_model,
    world_space_splats,
)
from app.analysis.reconstruction.plant_isolation import (
    classify_plant_points,
    plant_isolation_views_from_dataset,
)
from app.analysis.reconstruction.sparse_initializer import (
    initialize_sparse_geometry,
)
from app.analysis.reconstruction.runtime_probe import probe_gsplat_runtime


def _installed_gsplat_metadata() -> tuple[str, str | None]:
    try:
        distribution = importlib.metadata.distribution("gsplat")
    except importlib.metadata.PackageNotFoundError:
        return "unknown", None

    commit = None
    try:
        direct_url = json.loads(
            distribution.read_text("direct_url.json") or "{}"
        )
        vcs_info = (
            direct_url.get("vcs_info")
            if isinstance(direct_url, dict)
            else None
        )
        if isinstance(vcs_info, dict):
            candidate = str(vcs_info.get("commit_id") or "").strip()
            commit = candidate or None
    except (
        OSError,
        TypeError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
    ):
        commit = None
    return distribution.version, commit


@dataclass(slots=True)
class GsplatRoundResult:
    training: GsplatTrainingResult
    sparse: dict[str, Any]
    plant_splat_mask: np.ndarray | None = None
    plant_export_quality: dict[str, Any] = field(default_factory=dict)


def _write_point_cloud(
    path: Path,
    points: np.ndarray,
    colors: np.ndarray,
) -> Path:
    if len(points) == 0:
        raise ValueError("三維模型沒有可輸出的有效點。")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="ascii", newline="\n") as handle:
        handle.write("ply\n")
        handle.write("format ascii 1.0\n")
        handle.write(f"element vertex {len(points)}\n")
        handle.write("property float x\nproperty float y\nproperty float z\n")
        handle.write("property uchar red\nproperty uchar green\nproperty uchar blue\n")
        handle.write("end_header\n")
        for point, color in zip(points, colors):
            handle.write(
                f"{point[0]:.7g} {point[1]:.7g} {point[2]:.7g} "
                f"{int(color[0])} {int(color[1])} {int(color[2])}\n"
            )
    temporary.replace(path)
    return path


def _export_splats(
    output_path: Path,
    splats: Mapping[str, Any],
    selection: Any | None = None,
) -> Path:
    try:
        from gsplat import export_splats
    except ImportError as error:
        raise RuntimeError("gsplat 不支援模型匯出。") from error

    selected = {
        name: value if selection is None else value[selection]
        for name, value in splats.items()
    }
    if int(selected["means"].shape[0]) == 0:
        raise ValueError("選取的 Gaussian 模型沒有可輸出的有效點。")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    export_splats(
        means=selected["means"],
        scales=selected["scales"],
        quats=selected["quats"],
        opacities=selected["opacities"],
        sh0=selected["sh0"],
        shN=selected["shN"],
        format="ply",
        save_to=str(output_path),
    )
    return output_path


def _plant_splat_selection(
    result: GsplatRoundResult,
) -> np.ndarray:
    if result.plant_splat_mask is not None:
        return result.plant_splat_mask

    splats = world_space_splats(result.training)
    points = splats["means"].detach().cpu().numpy()
    classification = classify_plant_points(
        points,
        plant_isolation_views_from_dataset(
            result.training.dataset
        ),
    )
    result.plant_splat_mask = classification.plant_mask
    result.plant_export_quality = dict(classification.quality)
    return result.plant_splat_mask


class GsplatBackend:
    name = "gsplat_3dgs"
    repository_url = "https://github.com/nerfstudio-project/gsplat"
    license = "Apache-2.0"
    capabilities = {
        "scene_gaussian_export": True,
        "plant_gaussian_export": True,
        "background_gaussian_export": True,
        "scene_point_cloud_export": True,
        "render_preview_export": True,
    }

    def __init__(self) -> None:
        self.version, self.repository_commit = (
            _installed_gsplat_metadata()
        )
        self._cancel_event = Event()
        self._runtime_readiness: dict[str, Any] | None = None

    def check_availability(self) -> dict:
        environment = reconstruction_environment()
        errors = []
        warnings = []
        if not environment["gsplat_importable"]:
            errors.append("尚未安裝 gsplat，無法建立三維 Gaussian 模型。")
        if not environment["pytorch_version"]:
            errors.append("尚未安裝 PyTorch，無法執行三維模型訓練。")
        elif not environment["cuda_available"]:
            errors.append("目前沒有可用的 CUDA GPU。")
        if not environment["pycolmap_importable"]:
            errors.append("尚未安裝 PyCOLMAP，無法建立稀疏初始化點。")
        if not environment["scipy_version"]:
            errors.append("尚未安裝 SciPy，無法估計模型初始尺度。")
        if not environment["open3d_importable"]:
            errors.append(
                "Open3D 無法載入，無法輸出植物點雲。"
            )
        return {
            "backend": self.name,
            "backend_version": self.version,
            "repository_url": self.repository_url,
            "repository_commit": self.repository_commit,
            "license": self.license,
            "capabilities": dict(self.capabilities),
            "available": not errors,
            "errors": errors,
            "warnings": warnings,
            "environment": environment,
        }

    def probe_runtime(self) -> dict[str, Any]:
        readiness = self.check_availability()
        if not readiness["available"]:
            return readiness
        if self._runtime_readiness is None:
            self._runtime_readiness = probe_gsplat_runtime()
        runtime = dict(self._runtime_readiness)
        errors = list(runtime.get("errors") or [])
        return {
            **readiness,
            "available": bool(runtime.get("available")) and not errors,
            "errors": errors,
            "runtime_probe": runtime,
        }

    def prepare_dataset(
        self,
        job: Mapping[str, Any],
        output_dir: Path,
    ) -> PreparedRoundDataset:
        self._cancel_event.clear()
        return prepare_round_dataset(job, output_dir)

    def train(
        self,
        dataset: PreparedRoundDataset,
        parameters: Mapping[str, Any],
        output_dir: Path,
        *,
        progress_callback: ProgressCallback | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> GsplatRoundResult:
        def check_cancel() -> None:
            if self._cancel_event.is_set():
                raise InterruptedError("三維模型工作已取消。")
            if cancel_check is not None:
                cancel_check()

        def sparse_progress(stage: str, value: float) -> None:
            if progress_callback is not None:
                progress_callback(stage, value * 0.2, None)

        sparse = initialize_sparse_geometry(
            dataset,
            requested_device="cuda",
            use_constrained_bundle_adjustment=bool(
                parameters.get(
                    "use_constrained_bundle_adjustment",
                    True,
                )
            ),
            progress_callback=sparse_progress,
            cancel_check=check_cancel,
        )

        def training_progress(
            stage: str,
            value: float,
            message: str | None,
        ) -> None:
            if progress_callback is not None:
                progress_callback(stage, 0.2 + value * 0.7, message)

        training = train_gsplat_model(
            dataset,
            parameters,
            output_dir,
            progress_callback=training_progress,
            cancel_check=check_cancel,
        )
        return GsplatRoundResult(training=training, sparse=sparse)

    def export_gaussians(
        self,
        result: GsplatRoundResult,
        output_path: Path,
    ) -> Path:
        return _export_splats(
            output_path,
            world_space_splats(result.training),
        )

    def export_plant_gaussians(
        self,
        result: GsplatRoundResult,
        output_path: Path,
    ) -> Path:
        import torch

        selection = torch.from_numpy(
            _plant_splat_selection(result)
        ).to(result.training.splats["means"].device)
        return _export_splats(
            output_path,
            world_space_splats(result.training),
            selection,
        )

    def export_background_gaussians(
        self,
        result: GsplatRoundResult,
        output_path: Path,
    ) -> Path:
        import torch

        selection = torch.from_numpy(
            ~_plant_splat_selection(result)
        ).to(result.training.splats["means"].device)
        return _export_splats(
            output_path,
            world_space_splats(result.training),
            selection,
        )

    def export_point_cloud(
        self,
        result: GsplatRoundResult,
        output_path: Path,
    ) -> Path:
        import torch

        splats = world_space_splats(result.training)
        opacity = torch.sigmoid(splats["opacities"])
        valid = opacity >= 0.01
        means = splats["means"][valid].detach().cpu().numpy()
        colors = (
            (splats["sh0"][valid, 0] * 0.28209479177387814 + 0.5)
            .clamp(0, 1)
            .detach()
            .cpu()
            .numpy()
        )
        return _write_point_cloud(
            output_path,
            means,
            np.rint(colors * 255).astype(np.uint8),
        )

    def render_views(
        self,
        result: GsplatRoundResult,
        cameras: list[object],
        output_dir: Path,
    ) -> list[Path]:
        import torch
        from gsplat.rendering import rasterization

        output_dir.mkdir(parents=True, exist_ok=True)
        training = result.training
        device = training.splats["means"].device
        paths: list[Path] = []
        for view in training.dataset.views:
            width = max(1, view.image_width // 2)
            height = max(1, view.image_height // 2)
            camera_matrix = view.camera_matrix.copy()
            camera_matrix[0, :] /= 2
            camera_matrix[1, :] /= 2
            rotation = view.world_to_camera_matrix[:3, :3]
            translation = view.world_to_camera_matrix[:3, 3]
            viewmat = np.eye(4, dtype=np.float32)
            viewmat[:3, :3] = rotation
            viewmat[:3, 3] = (
                (
                    rotation @ training.center_world_mm
                    + translation
                )
                / training.world_scale_mm
            )
            with torch.no_grad():
                rendered, _, _ = rasterization(
                    means=training.splats["means"],
                    quats=training.splats["quats"],
                    scales=torch.exp(training.splats["scales"]),
                    opacities=torch.sigmoid(training.splats["opacities"]),
                    colors=torch.cat(
                        [training.splats["sh0"], training.splats["shN"]],
                        dim=1,
                    ),
                    viewmats=torch.from_numpy(viewmat).to(device)[None],
                    Ks=torch.from_numpy(
                        camera_matrix.astype(np.float32)
                    ).to(device)[None],
                    width=width,
                    height=height,
                    sh_degree=1,
                    packed=False,
                    near_plane=0.01,
                    far_plane=100.0,
                )
            image = (
                rendered[0, ..., :3]
                .clamp(0, 1)
                .mul(255)
                .byte()
                .cpu()
                .numpy()
            )
            destination = output_dir / f"{Path(view.image_name).stem}.jpg"
            encoded_ok, encoded = cv2.imencode(
                ".jpg",
                cv2.cvtColor(image, cv2.COLOR_RGB2BGR),
            )
            if not encoded_ok:
                raise RuntimeError(f"模型預覽無法編碼：{destination.name}")
            encoded.tofile(destination)
            paths.append(destination)
        return paths

    def cancel(self) -> None:
        self._cancel_event.set()
