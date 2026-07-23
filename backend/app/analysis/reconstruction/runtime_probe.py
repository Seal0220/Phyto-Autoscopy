from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from app.analysis.export.json_export import write_json_atomic


def _probe_payload() -> dict[str, Any]:
    import torch
    from gsplat.rendering import rasterization

    if not torch.cuda.is_available():
        raise RuntimeError("目前沒有可用的 CUDA GPU。")
    device = torch.device("cuda:0")
    means = torch.tensor([[0.0, 0.0, 3.0]], device=device, requires_grad=True)
    quats = torch.tensor(
        [[1.0, 0.0, 0.0, 0.0]],
        device=device,
        requires_grad=True,
    )
    scales = torch.tensor(
        [[0.1, 0.1, 0.1]],
        device=device,
        requires_grad=True,
    )
    opacities = torch.tensor([0.8], device=device, requires_grad=True)
    colors = torch.tensor(
        [[0.2, 0.8, 0.3]],
        device=device,
        requires_grad=True,
    )
    viewmats = torch.eye(4, device=device)[None]
    camera_matrix = torch.tensor(
        [[8.0, 0.0, 4.0], [0.0, 8.0, 4.0], [0.0, 0.0, 1.0]],
        device=device,
    )[None]
    rendered, alpha, _ = rasterization(
        means=means,
        quats=quats,
        scales=scales,
        opacities=opacities,
        colors=colors,
        viewmats=viewmats,
        Ks=camera_matrix,
        width=8,
        height=8,
        sh_degree=None,
        packed=False,
    )
    loss = rendered.sum() + alpha.sum()
    loss.backward()
    if not bool(torch.isfinite(rendered).all()):
        raise RuntimeError("gsplat CUDA 擴充套件產生了無效輸出。")
    return {
        "available": True,
        "cuda_extension_loadable": True,
        "gpu_name": torch.cuda.get_device_name(0),
        "torch_version": torch.__version__,
        "cuda_runtime_version": torch.version.cuda,
    }


def run_probe(result_path: Path) -> int:
    try:
        payload = _probe_payload()
        write_json_atomic(result_path, payload)
        return 0
    except BaseException as error:
        write_json_atomic(
            result_path,
            {
                "available": False,
                "cuda_extension_loadable": False,
                "errors": [
                    "gsplat 的 CUDA 擴充套件載入失敗："
                    + (str(error).strip() or type(error).__name__)
                ],
            },
        )
        return 1


def probe_gsplat_runtime(*, timeout_seconds: float = 300.0) -> dict[str, Any]:
    backend_root = Path(__file__).resolve().parents[3]
    with tempfile.TemporaryDirectory(prefix="phyto_gsplat_probe_") as directory:
        result_path = Path(directory) / "result.json"
        environment = os.environ.copy()
        existing = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = os.pathsep.join(
            item for item in (str(backend_root), existing) if item
        )
        try:
            process = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "app.analysis.reconstruction.runtime_probe",
                    "--result",
                    str(result_path),
                ],
                cwd=backend_root,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "available": False,
                "cuda_extension_loadable": False,
                "errors": ["gsplat CUDA 擴充套件檢查逾時。"],
            }
        if not result_path.is_file():
            return {
                "available": False,
                "cuda_extension_loadable": False,
                "errors": [
                    f"gsplat CUDA 擴充套件檢查異常結束（{process.returncode}）。"
                ],
            }
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {
            "available": False,
            "cuda_extension_loadable": False,
            "errors": ["gsplat CUDA 擴充套件檢查結果格式無效。"],
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, required=True)
    arguments = parser.parse_args()
    return run_probe(arguments.result)


if __name__ == "__main__":
    raise SystemExit(main())
