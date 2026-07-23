from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any, Mapping

from app.analysis.export.json_export import write_json_atomic
from app.analysis.reconstruction.backend import CancelCheck, ProgressCallback
from app.analysis.reconstruction.dataset_adapter import (
    PreparedRoundDataset,
    prepare_round_dataset,
)
from app.analysis.reconstruction.environment import reconstruction_environment
from app.analysis.reconstruction.sparse_initializer import (
    initialize_sparse_geometry,
)


_ITERATIONS = {
    "preview": 3_000,
    "standard": 10_000,
    "high": 30_000,
}


@dataclass(frozen=True, slots=True)
class GraphdecoRoundResult:
    dataset: PreparedRoundDataset
    sparse: dict[str, Any]
    model_path: Path
    maximum_steps: int
    completed_steps: int
    duration_seconds: float
    metrics: dict[str, Any]


class GraphdecoBackend:
    name = "graphdeco_3dgs"
    version = "reference"
    repository_url = "https://github.com/graphdeco-inria/gaussian-splatting"
    license = "Inria research/evaluation license"

    def __init__(self) -> None:
        self._cancel_event = Event()
        configured = os.environ.get("PHYTO_GRAPHDECO_ROOT", "").strip()
        self.repository_root = Path(configured).resolve() if configured else None
        self.repository_commit = None

    def check_availability(self) -> dict:
        environment = reconstruction_environment()
        root = self.repository_root
        errors = []
        if root is None or not (root / "train.py").is_file():
            errors.append("尚未設定可用的 Graphdeco 研究版模型目錄。")
        if not environment["cuda_available"]:
            errors.append("目前沒有可用的 CUDA GPU。")
        if not environment["pycolmap_importable"]:
            errors.append("尚未安裝 PyCOLMAP，無法建立稀疏初始化點。")
        if not environment["open3d_importable"]:
            errors.append("Open3D 無法載入，無法輸出植物點雲。")
        return {
            "backend": self.name,
            "backend_version": self.version,
            "repository_url": self.repository_url,
            "repository_commit": self.repository_commit,
            "license": self.license,
            "available": not errors,
            "errors": errors,
            "warnings": [
                "Graphdeco Backend 僅供研究與評估，部署前必須重新審查授權。"
            ],
            "environment": environment,
        }

    def prepare_dataset(
        self,
        job: Mapping[str, Any],
        output_dir: Path,
    ) -> PreparedRoundDataset:
        self._cancel_event.clear()
        return prepare_round_dataset(job, output_dir)

    def probe_runtime(self) -> dict[str, Any]:
        return self.check_availability()

    def train(
        self,
        dataset: PreparedRoundDataset,
        parameters: Mapping[str, Any],
        output_dir: Path,
        *,
        progress_callback: ProgressCallback | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> GraphdecoRoundResult:
        root = self.repository_root
        if root is None:
            raise RuntimeError("尚未設定 Graphdeco 研究版模型目錄。")

        def check_cancel() -> None:
            if self._cancel_event.is_set():
                raise InterruptedError("Graphdeco 模型工作已取消。")
            if cancel_check is not None:
                cancel_check()

        def sparse_progress(stage: str, value: float) -> None:
            if progress_callback is not None:
                progress_callback(stage, value * 0.2, None)

        sparse = initialize_sparse_geometry(
            dataset,
            requested_device="cuda",
            progress_callback=sparse_progress,
            cancel_check=check_cancel,
        )
        quality = str(parameters.get("quality_preset") or "standard")
        maximum_steps = _ITERATIONS.get(quality)
        if maximum_steps is None:
            raise ValueError("模型品質只能使用預覽、標準或高品質。")
        output_dir.mkdir(parents=True, exist_ok=True)
        log_path = output_dir / "graphdeco.log"
        python_executable = (
            os.environ.get("PHYTO_GRAPHDECO_PYTHON", "").strip()
            or sys.executable
        )
        command = [
            python_executable,
            str(root / "train.py"),
            "-s",
            str(dataset.root),
            "-m",
            str(output_dir),
            "--iterations",
            str(maximum_steps),
            "--save_iterations",
            str(maximum_steps),
            "--test_iterations",
            str(maximum_steps),
            "--quiet",
        ]
        started = time.monotonic()
        with log_path.open("w", encoding="utf-8", errors="replace") as log:
            process = subprocess.Popen(
                command,
                cwd=root,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                shell=False,
            )
            if progress_callback is not None:
                progress_callback(
                    "reconstructing_round_model",
                    0.2,
                    "Graphdeco 正在訓練本輪模型。",
                )
            try:
                while process.poll() is None:
                    try:
                        check_cancel()
                    except BaseException:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=5)
                        raise
                    time.sleep(0.25)
            finally:
                if process.poll() is None:
                    process.terminate()
            return_code = process.wait()
        if return_code != 0:
            tail = ""
            try:
                tail = "\n".join(
                    log_path.read_text(
                        encoding="utf-8",
                        errors="replace",
                    ).splitlines()[-20:]
                )
            except OSError:
                pass
            raise RuntimeError(
                "Graphdeco 模型工作失敗。"
                + (f" 最後輸出：{tail}" if tail else "")
            )
        model_path = (
            output_dir
            / "point_cloud"
            / f"iteration_{maximum_steps}"
            / "point_cloud.ply"
        )
        if not model_path.is_file():
            raise RuntimeError("Graphdeco 完成後沒有產生 Gaussian 模型檔。")
        duration = time.monotonic() - started
        metrics = {
            "quality_preset": quality,
            "training_iterations": maximum_steps,
            "coordinate_space": "aruco_world_mm",
            "camera_poses_fixed": True,
            "reference_backend": True,
            "log_path": str(log_path),
        }
        write_json_atomic(output_dir / "training_metrics.json", metrics)
        if progress_callback is not None:
            progress_callback(
                "reconstructing_round_model",
                0.9,
                "Graphdeco 本輪模型已完成。",
            )
        return GraphdecoRoundResult(
            dataset=dataset,
            sparse=sparse,
            model_path=model_path,
            maximum_steps=maximum_steps,
            completed_steps=maximum_steps,
            duration_seconds=duration,
            metrics=metrics,
        )

    def export_gaussians(
        self,
        result: GraphdecoRoundResult,
        output_path: Path,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if result.model_path.resolve() != output_path.resolve():
            shutil.copy2(result.model_path, output_path)
        return output_path

    def export_point_cloud(
        self,
        result: GraphdecoRoundResult,
        output_path: Path,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(result.sparse["point_cloud_path"], output_path)
        return output_path

    def render_views(
        self,
        result: GraphdecoRoundResult,
        cameras: list[object],
        output_dir: Path,
    ) -> list[Path]:
        # Graphdeco's renderer is intentionally not launched here: the official
        # script starts another CUDA process and has no cooperative cancellation
        # contract. The trained model remains renderable by that reference tool.
        return []

    def cancel(self) -> None:
        self._cancel_event.set()
