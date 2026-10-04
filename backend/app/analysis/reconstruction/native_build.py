from __future__ import annotations

import os


def configure_native_build() -> dict[str, str]:
    """Configure both NVCC and direct MSVC invocations before loading gsplat."""
    if os.name != "nt":
        return {}

    # _CL_ is read by cl.exe itself, including NVCC's preprocessing passes.
    # Appending makes the choice effective even with an inherited disabling flag.
    flags = {
        "_CL_": "/Zc:preprocessor",
        "NVCC_APPEND_FLAGS": "-Xcompiler=/Zc:preprocessor",
    }
    for name, flag in flags.items():
        existing = os.environ.get(name, "").strip()
        if not existing.endswith(flag):
            os.environ[name] = f"{existing} {flag}".strip()
    return {name: os.environ[name] for name in flags}
