"""Install pinned Windows CUDA vision wheels into this project's venv.

The overlay avoids replacing DLLs held by an already running application.
Only a successful CUDA smoke test activates it for subsequent Python processes.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ASSETS = (
    {
        "name": "opencv_python_cuda-4.13.0+f2c1edd-cp37-abi3-win_amd64.whl",
        "url": "https://github.com/Breakthrough/opencv-python-cuda/releases/download/4.13.0-dev1/opencv_python_cuda-4.13.0%2Bf2c1edd-cp37-abi3-win_amd64.whl",
        "sha256": "4363df06d189329f8c0deae1d891ff317c1040cc0ef94760d2d8e8cefc25482e",
        "size": 1984632503,
    },
    {
        "name": "pycolmap-4.2.0+cuda.cudss-cp312-cp312-win_amd64.whl",
        "url": "https://github.com/lyehe/build_gpu_colmap/releases/download/v4.2.0-3/pycolmap-4.2.0%2Bcuda.cudss-cp312-cp312-win_amd64.whl",
        "sha256": "21b07b0ce1a5310a8176bfe9b683c35440eff69f0e29624cb62eeb26b725d734",
        "size": 1213276310,
    },
)


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def download(asset: dict, directory: Path) -> Path:
    destination = directory / asset["name"]
    if destination.is_file() and digest(destination) == asset["sha256"]:
        return destination
    partial = destination.with_suffix(".whl.part")
    offset = partial.stat().st_size if partial.exists() else 0
    request = urllib.request.Request(asset["url"], headers={
        "User-Agent": "Phyto-Autoscopy-CUDA-Setup", "Range": f"bytes={offset}-",
    })
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 206:
            offset = 0
        last_report = time.monotonic()
        with partial.open("ab" if offset else "wb") as handle:
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)
                offset += len(chunk)
                if time.monotonic() - last_report >= 30:
                    print(f"{asset['name']}: {offset / asset['size']:.1%} ({offset // 1048576} MiB)", flush=True)
                    last_report = time.monotonic()
    if partial.stat().st_size != asset["size"] or digest(partial) != asset["sha256"]:
        raise RuntimeError(f"Download integrity check failed: {asset['name']}")
    partial.replace(destination)
    print(f"SHA256 verified: {destination.name}", flush=True)
    return destination


def main() -> None:
    if sys.platform != "win32" or sys.version_info[:2] != (3, 12):
        raise RuntimeError("These pinned wheels require Windows x64 / Python 3.12.")
    root = Path(__file__).resolve().parents[2]
    prefix = Path(sys.prefix).resolve()
    if prefix != root / ".venv":
        raise RuntimeError("Run with this project's .venv/Scripts/python.exe.")
    directory = root / "data" / "temp" / "cuda-vision-wheels"
    directory.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=2) as executor:
        wheels = list(executor.map(lambda asset: download(asset, directory), ASSETS))
    site_packages = prefix / "Lib" / "site-packages"
    overlay = site_packages / "phyto_cuda_vision"
    subprocess.run([
        sys.executable, "-m", "pip", "install", "--no-deps", "--no-compile",
        "--disable-pip-version-check", "--target", str(overlay), *map(str, wheels),
    ], check=True)
    smoke = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "import cv2, pycolmap, numpy as np; "
        "assert cv2.cuda.getCudaEnabledDeviceCount() > 0; assert pycolmap.has_cuda; "
        "a=cv2.cuda_GpuMat(); a.upload(np.full((16,16), 37, np.uint8)); "
        "assert np.array_equal(a.download(), np.full((16,16),37,np.uint8)); "
        "print('CUDA OpenCV', cv2.__version__, 'PyCOLMAP', pycolmap.__version__, flush=True)"
    )
    subprocess.run([sys.executable, "-c", smoke, str(overlay)], check=True)
    activation = site_packages / "phyto_cuda_vision.pth"
    line = f"import sys; sys.path.insert(0, {str(overlay)!r})\n"
    if activation.exists() and activation.read_text(encoding="utf-8") != line:
        raise RuntimeError("Existing CUDA activation file differs; refusing to overwrite it.")
    activation.write_text(line, encoding="utf-8")
    (directory / "installed.json").write_text(json.dumps({
        "assets": ASSETS, "overlay": str(overlay), "activation": str(activation),
    }, indent=2), encoding="utf-8")
    print("Activated CUDA vision packages for subsequent project Python processes.", flush=True)


if __name__ == "__main__":
    main()
