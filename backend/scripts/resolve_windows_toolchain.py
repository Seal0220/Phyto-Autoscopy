"""Locate Windows build tools for the backend launcher without modifying files."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path


def _program_files_roots() -> list[Path]:
    roots = []
    for name in ("ProgramFiles", "ProgramFiles(x86)"):
        value = os.environ.get(name)
        if value:
            root = Path(value)
            if root not in roots:
                roots.append(root)
    return roots


def _visual_cpp_setup() -> Path | None:
    if os.environ.get("VSCMD_VER") and shutil.which("cl.exe"):
        return None

    for root in _program_files_roots():
        vswhere = root / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
        if not vswhere.is_file():
            continue
        try:
            result = subprocess.run(
                [
                    str(vswhere),
                    "-latest",
                    "-products",
                    "*",
                    "-requires",
                    "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                    "-property",
                    "installationPath",
                ],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and result.stdout.strip():
            setup = (
                Path(result.stdout.strip().splitlines()[0])
                / "VC"
                / "Auxiliary"
                / "Build"
                / "vcvars64.bat"
            )
            if setup.is_file():
                return setup

    for version in ("18", "2026", "2022", "2019"):
        for root in _program_files_roots():
            for edition in ("Community", "Professional", "Enterprise", "BuildTools"):
                setup = (
                    root
                    / "Microsoft Visual Studio"
                    / version
                    / edition
                    / "VC"
                    / "Auxiliary"
                    / "Build"
                    / "vcvars64.bat"
                )
                if setup.is_file():
                    return setup
    return None


def _cuda_candidates() -> list[Path]:
    candidates = []
    for name in ("CUDA_HOME", "CUDA_PATH"):
        value = os.environ.get(name)
        if value:
            candidates.append(Path(value))

    current_nvcc = shutil.which("nvcc.exe")
    if current_nvcc:
        candidates.append(Path(current_nvcc).parent.parent)

    for root in _program_files_roots():
        cuda_root = root / "NVIDIA GPU Computing Toolkit" / "CUDA"
        if cuda_root.is_dir():
            candidates.extend(cuda_root.glob("v*"))

    unique = {}
    for candidate in candidates:
        if candidate.is_dir() and (candidate / "bin" / "nvcc.exe").is_file():
            unique[str(candidate.resolve()).casefold()] = candidate.resolve()
    return list(unique.values())


def _cuda_version(path: Path) -> tuple[int, int] | None:
    try:
        result = subprocess.run(
            [str(path / "bin" / "nvcc.exe"), "--version"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"release\s+(\d+)\.(\d+)", result.stdout)
    if result.returncode != 0 or match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def _cuda_toolkit() -> Path | None:
    try:
        import torch
    except ImportError:
        return None

    match = re.fullmatch(r"(\d+)\.(\d+)", torch.version.cuda or "")
    if match is None:
        return None
    target = int(match.group(1)), int(match.group(2))

    compatible = []
    for candidate in _cuda_candidates():
        version = _cuda_version(candidate)
        if version is not None and version[0] == target[0]:
            compatible.append((version, candidate))
    if not compatible:
        return None
    compatible.sort(key=lambda item: (item[0] == target, item[0]), reverse=True)
    return compatible[0][1]


def main() -> None:
    visual_cpp = _visual_cpp_setup()
    if visual_cpp is not None:
        print(f"VCVARS_SCRIPT={visual_cpp}")

    cuda_toolkit = _cuda_toolkit()
    if cuda_toolkit is not None:
        print(f"CUDA_TOOLKIT_PATH={cuda_toolkit}")


if __name__ == "__main__":
    main()
