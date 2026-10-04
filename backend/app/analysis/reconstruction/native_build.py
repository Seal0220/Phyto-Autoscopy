from __future__ import annotations

import os
from functools import wraps


def _msvc_gsplat_flags(extra_cflags: list[str] | None) -> list[str]:
    """Translate gsplat's Unix-only host flags for the Windows compiler."""
    replacements = {"-O0": "/Od", "-O3": "/O2"}
    return [
        replacements.get(flag, flag)
        for flag in extra_cflags or []
        if flag != "-Wno-attributes"
    ]


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

    # gsplat 1.5.3 passes -O3 and -Wno-attributes to PyTorch's JIT C++
    # compiler even on Windows. cl.exe rejects -Wno-attributes (D8021).
    # Patch only gsplat_cuda, leaving all other extensions untouched.
    original_compile = cpp_extension._jit_compile
    if not getattr(original_compile, "_phyto_gsplat_msvc_compatible", False):
        @wraps(original_compile)
        def compile_with_msvc_flags(
            name: str,
            sources: list[str],
            extra_cflags: list[str] | None,
            extra_cuda_cflags: list[str] | None,
            *args: object,
            **kwargs: object,
        ) -> object:
            if name == "gsplat_cuda":
                extra_cflags = _msvc_gsplat_flags(extra_cflags)
            return original_compile(
                name,
                sources,
                extra_cflags,
                extra_cuda_cflags,
                *args,
                **kwargs,
            )

        compile_with_msvc_flags._phyto_gsplat_msvc_compatible = True
        cpp_extension._jit_compile = compile_with_msvc_flags

    return {
        **{name: os.environ[name] for name in flags},
        "pytorch_msvc_flags": " ".join(compiler_flags),
        "gsplat_msvc_host_flags": "enabled",
    }
