from __future__ import annotations

import importlib.metadata
import importlib.util
import os
import platform
from typing import Any


def _package_version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def reconstruction_environment() -> dict[str, Any]:
    torch_version = _package_version("torch")
    cuda_available = False
    cuda_runtime_version = None
    gpu_name = None
    gpu_memory_bytes = None
    gpu_free_memory_bytes = None
    gpu_allocated_memory_bytes = None
    cuda_error = None

    if torch_version is not None:
        try:
            import torch

            cuda_available = bool(torch.cuda.is_available())
            cuda_runtime_version = getattr(torch.version, "cuda", None)
            if cuda_available:
                gpu_name = torch.cuda.get_device_name(0)
                properties = torch.cuda.get_device_properties(0)
                gpu_memory_bytes = int(properties.total_memory)
                free_memory, _ = torch.cuda.mem_get_info(0)
                gpu_free_memory_bytes = int(free_memory)
                gpu_allocated_memory_bytes = int(
                    torch.cuda.memory_allocated(0)
                )
        except Exception as error:
            cuda_error = str(error)

    return {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "pytorch_version": torch_version,
        "cuda_available": cuda_available,
        "cuda_runtime_version": cuda_runtime_version,
        "cuda_toolkit_path": os.environ.get("CUDA_PATH") or os.environ.get("CUDA_HOME"),
        "gpu_name": gpu_name,
        "gpu_memory_bytes": gpu_memory_bytes,
        "gpu_free_memory_bytes": gpu_free_memory_bytes,
        "gpu_allocated_memory_bytes": gpu_allocated_memory_bytes,
        "cuda_error": cuda_error,
        "gsplat_version": _package_version("gsplat"),
        "pycolmap_version": _package_version("pycolmap"),
        "open3d_version": _package_version("open3d"),
        "scipy_version": _package_version("scipy"),
        "networkx_version": _package_version("networkx"),
        "gsplat_importable": importlib.util.find_spec("gsplat") is not None,
        "pycolmap_importable": importlib.util.find_spec("pycolmap") is not None,
        "open3d_importable": importlib.util.find_spec("open3d") is not None,
    }
