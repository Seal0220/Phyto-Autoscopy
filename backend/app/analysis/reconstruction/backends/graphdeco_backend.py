from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Any, Mapping

import numpy as np

from app.analysis.export.json_export import write_json_atomic
from app.analysis.reconstruction.backend import CancelCheck, ProgressCallback
from app.analysis.reconstruction.dataset_adapter import (
    PreparedRoundDataset,
    prepare_round_dataset,
)
from app.analysis.reconstruction.environment import reconstruction_environment
from app.analysis.reconstruction.plant_isolation import (
    classify_plant_points,
    plant_isolation_views_from_dataset,
)
from app.analysis.reconstruction.sparse_initializer import (
    initialize_sparse_geometry,
)


_ITERATIONS = {
    "preview": 3_000,
    "standard": 10_000,
    "high": 30_000,
}

_PLY_SCALAR_DTYPES = {
    "char": "i1",
    "int8": "i1",
    "uchar": "u1",
    "uint8": "u1",
    "short": "<i2",
    "int16": "<i2",
    "ushort": "<u2",
    "uint16": "<u2",
    "int": "<i4",
    "int32": "<i4",
    "uint": "<u4",
    "uint32": "<u4",
    "float": "<f4",
    "float32": "<f4",
    "double": "<f8",
    "float64": "<f8",
}


def _repository_commit(repository_root: Path | None) -> str | None:
    if repository_root is None:
        return None
    git_directory = repository_root / ".git"
    if git_directory.is_file():
        try:
            pointer = git_directory.read_text(
                encoding="utf-8"
            ).strip()
        except OSError:
            return None
        prefix = "gitdir:"
        if not pointer.lower().startswith(prefix):
            return None
        git_directory = Path(pointer[len(prefix):].strip())
        if not git_directory.is_absolute():
            git_directory = (repository_root / git_directory).resolve()
    if not git_directory.is_dir():
        return None
    try:
        head = (git_directory / "HEAD").read_text(
            encoding="ascii"
        ).strip()
    except OSError:
        return None
    if not head.startswith("ref:"):
        return head or None
    reference = head.removeprefix("ref:").strip()
    try:
        commit = (git_directory / reference).read_text(
            encoding="ascii"
        ).strip()
        if commit:
            return commit
    except OSError:
        pass
    try:
        packed_references = (
            git_directory / "packed-refs"
        ).read_text(
            encoding="ascii"
        ).splitlines()
    except OSError:
        return None
    for line in packed_references:
        if not line or line.startswith(("#", "^")):
            continue
        commit, _, candidate_reference = line.partition(" ")
        if candidate_reference == reference:
            return commit or None
    return None


@dataclass(slots=True)
class GraphdecoRoundResult:
    dataset: PreparedRoundDataset
    sparse: dict[str, Any]
    model_path: Path
    maximum_steps: int
    completed_steps: int
    duration_seconds: float
    metrics: dict[str, Any]
    plant_vertex_mask: np.ndarray | None = None
    plant_export_quality: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _GraphdecoPly:
    header_lines: tuple[str, ...]
    newline: str
    vertices: np.ndarray
    trailing_data: bytes


def _read_graphdeco_ply(path: Path) -> _GraphdecoPly:
    data = path.read_bytes()
    marker = b"end_header\n"
    header_end = data.find(marker)
    if header_end < 0:
        marker = b"end_header\r\n"
        header_end = data.find(marker)
    if header_end < 0:
        raise ValueError("Graphdeco Gaussian PLY 缺少有效標頭。")
    data_offset = header_end + len(marker)
    try:
        header_text = data[:data_offset].decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError("Graphdeco Gaussian PLY 標頭格式無效。") from error
    header_lines = tuple(header_text.splitlines())
    if "format binary_little_endian 1.0" not in header_lines:
        raise ValueError(
            "Graphdeco Gaussian 分類只支援正式的 binary_little_endian PLY。"
        )

    vertex_count = None
    in_vertex_element = False
    properties: list[tuple[str, str]] = []
    for line in header_lines:
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "element":
            in_vertex_element = parts[1] == "vertex"
            if in_vertex_element:
                try:
                    vertex_count = int(parts[2])
                except ValueError as error:
                    raise ValueError(
                        "Graphdeco Gaussian PLY 點數格式無效。"
                    ) from error
            continue
        if not in_vertex_element or not parts or parts[0] != "property":
            continue
        if len(parts) != 3 or parts[1] == "list":
            raise ValueError(
                "Graphdeco Gaussian PLY 的 vertex 欄位格式不受支援。"
            )
        scalar_type = _PLY_SCALAR_DTYPES.get(parts[1])
        if scalar_type is None:
            raise ValueError(
                f"Graphdeco Gaussian PLY 使用不支援的欄位型別：{parts[1]}"
            )
        properties.append((parts[2], scalar_type))

    if vertex_count is None or vertex_count < 0 or not properties:
        raise ValueError("Graphdeco Gaussian PLY 缺少 vertex 資料。")
    dtype = np.dtype(properties)
    vertex_data_end = data_offset + vertex_count * dtype.itemsize
    if vertex_data_end > len(data):
        raise ValueError("Graphdeco Gaussian PLY 的 vertex 資料不完整。")
    vertices = np.frombuffer(
        data,
        dtype=dtype,
        count=vertex_count,
        offset=data_offset,
    )
    if not {"x", "y", "z"}.issubset(vertices.dtype.names or ()):
        raise ValueError("Graphdeco Gaussian PLY 缺少世界座標欄位。")
    return _GraphdecoPly(
        header_lines=header_lines,
        newline="\r\n" if b"\r\n" in data[:data_offset] else "\n",
        vertices=vertices,
        trailing_data=data[vertex_data_end:],
    )


def _write_filtered_graphdeco_ply(
    source: _GraphdecoPly,
    output_path: Path,
    selection: np.ndarray,
) -> Path:
    mask = np.asarray(selection, dtype=bool)
    if mask.shape != (len(source.vertices),):
        raise ValueError("Graphdeco Gaussian 分類遮罩尺寸不相符。")
    selected = source.vertices[mask]
    if len(selected) == 0:
        raise ValueError("選取的 Graphdeco Gaussian 模型沒有有效點。")
    header_lines = [
        (
            f"element vertex {len(selected)}"
            if line.startswith("element vertex ")
            else line
        )
        for line in source.header_lines
    ]
    header = (
        source.newline.join(header_lines)
        + source.newline
    ).encode("ascii")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(header)
            handle.write(selected.tobytes(order="C"))
            handle.write(source.trailing_data)
        temporary.replace(output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return output_path


def _plant_vertex_selection(
    result: GraphdecoRoundResult,
) -> tuple[_GraphdecoPly, np.ndarray]:
    source = _read_graphdeco_ply(result.model_path)
    if (
        result.plant_vertex_mask is not None
        and len(result.plant_vertex_mask) == len(source.vertices)
    ):
        return source, result.plant_vertex_mask
    points = np.column_stack((
        source.vertices["x"],
        source.vertices["y"],
        source.vertices["z"],
    )).astype(np.float64)
    classification = classify_plant_points(
        points,
        plant_isolation_views_from_dataset(result.dataset),
    )
    result.plant_vertex_mask = classification.plant_mask
    result.plant_export_quality = dict(classification.quality)
    return source, result.plant_vertex_mask


class GraphdecoBackend:
    name = "graphdeco_3dgs"
    version = "reference"
    repository_url = "https://github.com/graphdeco-inria/gaussian-splatting"
    license = "Inria research/evaluation license"
    capabilities = {
        "scene_gaussian_export": True,
        "plant_gaussian_export": True,
        "background_gaussian_export": True,
        "scene_point_cloud_export": True,
        "render_preview_export": False,
    }

    def __init__(self) -> None:
        self._cancel_event = Event()
        configured = os.environ.get("PHYTO_GRAPHDECO_ROOT", "").strip()
        self.repository_root = Path(configured).resolve() if configured else None
        self.repository_commit = _repository_commit(
            self.repository_root
        )

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
            "capabilities": dict(self.capabilities),
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
            use_constrained_bundle_adjustment=bool(
                parameters.get(
                    "use_constrained_bundle_adjustment",
                    True,
                )
            ),
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
            "fixed_camera_poses_constant": True,
            "camera_intrinsics_constant": True,
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

    def export_plant_gaussians(
        self,
        result: GraphdecoRoundResult,
        output_path: Path,
    ) -> Path:
        source, selection = _plant_vertex_selection(result)
        return _write_filtered_graphdeco_ply(
            source,
            output_path,
            selection,
        )

    def export_background_gaussians(
        self,
        result: GraphdecoRoundResult,
        output_path: Path,
    ) -> Path:
        source, selection = _plant_vertex_selection(result)
        return _write_filtered_graphdeco_ply(
            source,
            output_path,
            ~selection,
        )

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
