from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Protocol


ProgressCallback = Callable[[str, float, str | None], None]
CancelCheck = Callable[[], None]


class ReconstructionBackend(Protocol):
    name: str
    version: str
    repository_url: str
    repository_commit: str | None
    license: str

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
