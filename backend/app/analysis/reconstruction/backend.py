from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Protocol


ProgressCallback = Callable[[str, float, str | None], None]
CancelCheck = Callable[[], None]


RECONSTRUCTION_CAPABILITY_LABELS = {
    "scene_gaussian_export": "完整場景 Gaussian 模型",
    "plant_gaussian_export": "純植物 Gaussian 模型",
    "background_gaussian_export": "背景 Gaussian 模型",
    "scene_point_cloud_export": "完整場景點雲",
    "render_preview_export": "模型預覽",
}


def unsupported_reconstruction_outputs(
    capabilities: Mapping[str, bool],
    requested: Mapping[str, bool],
) -> list[str]:
    return [
        RECONSTRUCTION_CAPABILITY_LABELS.get(name, name)
        for name, enabled in requested.items()
        if enabled and not capabilities.get(name, False)
    ]


class ReconstructionBackend(Protocol):
    name: str
    version: str
    repository_url: str
    repository_commit: str | None
    license: str
    capabilities: Mapping[str, bool]

    def check_availability(self) -> dict[str, Any]:
        ...

    def prepare_dataset(
        self,
        job: Mapping[str, Any],
        output_dir: Path,
    ) -> object:
        ...

    def train(
        self,
        dataset: object,
        parameters: Mapping[str, Any],
        output_dir: Path,
        *,
        progress_callback: ProgressCallback | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> object:
        ...

    def export_gaussians(self, result: object, output_path: Path) -> Path:
        ...

    def export_plant_gaussians(
        self,
        result: object,
        output_path: Path,
    ) -> Path:
        ...

    def export_background_gaussians(
        self,
        result: object,
        output_path: Path,
    ) -> Path:
        ...

    def export_point_cloud(self, result: object, output_path: Path) -> Path:
        ...

    def render_views(
        self,
        result: object,
        cameras: list[object],
        output_dir: Path,
    ) -> list[Path]:
        ...

    def cancel(self) -> None:
        ...
