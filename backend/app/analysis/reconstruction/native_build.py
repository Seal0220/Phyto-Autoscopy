from __future__ import annotations

import inspect
import locale
import os
from functools import wraps
from pathlib import Path


_TEMPLATE_OUTPUTS = {
    "RasterizeToPixels2DGSBwd.cu": (
        "v_means2d", "v_ray_transforms", "v_colors", "v_opacities",
        "v_normals", "v_densify",
    ),
    "RasterizeToPixelsFromWorld3DGSFwd.cu": ("renders", "alphas", "last_ids"),
}


def _msvc_gsplat_sources(
    sources: list[str], build_directory: str,
) -> tuple[list[str], list[str]]:
    """Match template output qualifiers without editing the installed package.

    gsplat 1.5.3 declares mutable output tensors but explicitly instantiates
    two CUDA templates with const outputs. NVCC and MSVC encode those template
    signatures differently on Windows, causing 38 unresolved symbols.
    """
    patched_sources = []
    include_paths = []
    for source in sources:
        path = Path(source)
        outputs = _TEMPLATE_OUTPUTS.get(path.name)
        if outputs is None:
            patched_sources.append(source)
            continue
        content = path.read_text(encoding="utf-8")
        prefix, separator, instantiations = content.partition("#define __INS__(CDIM)")
        patched = instantiations
        for output in outputs:
            patched = patched.replace(f"const at::Tensor {output},", f"at::Tensor {output},")
            patched = patched.replace(f"const at::Tensor {output} ", f"at::Tensor {output} ")
        if not separator or patched == instantiations:
            patched_sources.append(source)
            continue
        destination = Path(build_directory) / "phyto_sources" / path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        updated = prefix + separator + patched
        if not destination.exists() or destination.read_text(encoding="utf-8") != updated:
            destination.write_text(updated, encoding="utf-8")
        patched_sources.append(str(destination))
        if str(path.parent) not in include_paths:
            include_paths.append(str(path.parent))
    return patched_sources, include_paths


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

    # The OEM codec can fail in a Windows process without a console. Preserve
    # localized diagnostics using the Windows locale with tolerant decoding.
    cpp_extension.SUBPROCESS_DECODE_ARGS = (locale.getencoding(), "replace")

    compiler_flags = cpp_extension.COMMON_MSVC_FLAGS
    if "/Zc:preprocessor" not in compiler_flags:
        compiler_flags.append("/Zc:preprocessor")

    # gsplat 1.5.3 passes -O3 and -Wno-attributes to PyTorch's JIT C++
    # compiler even on Windows. cl.exe rejects -Wno-attributes (D8021).
    # Patch only gsplat_cuda, leaving all other extensions untouched.
    original_compile = cpp_extension._jit_compile
    if not getattr(original_compile, "_phyto_gsplat_msvc_compatible", False):
        signature = inspect.signature(original_compile)

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
                try:
                    bound = signature.bind(
                        name, sources, extra_cflags, extra_cuda_cflags, *args, **kwargs,
                    )
                except TypeError:
                    # Let PyTorch report its own signature error so gsplat can
                    # retry with the additional SYCL argument in torch >= 2.7.
                    pass
                else:
                    sources, include_paths = _msvc_gsplat_sources(
                        sources, bound.arguments["build_directory"],
                    )
                    bound.arguments["sources"] = sources
                    bound.arguments["extra_include_paths"] = [
                        *(bound.arguments.get("extra_include_paths") or []),
                        *include_paths,
                    ]
                    return original_compile(*bound.args, **bound.kwargs)
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
        "gsplat_msvc_template_outputs": "enabled",
    }
