from __future__ import annotations

import os


def configure_native_build() -> dict[str, str]:
    """Configure the MSVC flags used by gsplat's PyTorch JIT build."""
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

    # gsplat 1.5.3 calls PyTorch's JIT extension builder. Its generated Ninja
    # rules use this list for both C++ and NVCC host-compiler invocations.
    # Put the option in those rules explicitly instead of relying on inherited
    # environment variables, which are invisible in the reported command.
    from torch.utils import cpp_extension

    compiler_flags = cpp_extension.COMMON_MSVC_FLAGS
    if "/Zc:preprocessor" not in compiler_flags:
        compiler_flags.append("/Zc:preprocessor")

    return {
        **{name: os.environ[name] for name in flags},
        "pytorch_msvc_flags": " ".join(compiler_flags),
    }
