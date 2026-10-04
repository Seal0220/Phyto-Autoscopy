from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from app.analysis.reconstruction import native_build

from app.analysis.reconstruction.native_build import (
    _msvc_gsplat_flags,
    _msvc_gsplat_sources,
)


@pytest.mark.parametrize(
    ("filename", "outputs"),
    [
        ("RasterizeToPixels2DGSBwd.cu", (
            "v_means2d", "v_ray_transforms", "v_colors", "v_opacities",
            "v_normals", "v_densify",
        )),
        ("RasterizeToPixelsFromWorld3DGSFwd.cu", ("renders", "alphas", "last_ids")),
    ],
)
def test_cuda_template_outputs_match_mutable_declaration(
    tmp_path: Path, filename: str, outputs: tuple[str, ...],
) -> None:
    original = tmp_path / "installed" / filename
    original.parent.mkdir()
    body = "void kernel(const at::Tensor colors) {}\n"
    macro_lines = [
        '#define __INS__(CDIM)',
        '    template void launch<CDIM>(const at::Tensor colors,',
        *(f'    const at::Tensor {name},' for name in outputs[:-1]),
        f'    const at::Tensor {outputs[-1]}',
        '    );',
    ]
    instantiation = (' ' + chr(92) + '\n').join(macro_lines) + '\n'
    original.write_text(body + instantiation, encoding="utf-8")
    sources, includes = _msvc_gsplat_sources([str(original)], str(tmp_path / "cache"))
    patched = Path(sources[0])
    content = patched.read_text(encoding="utf-8")
    assert content.startswith(body)
    assert "const at::Tensor colors," in content
    for name in outputs:
        assert f"const at::Tensor {name}" not in content
        assert f"at::Tensor {name}" in content
    assert original.read_text(encoding="utf-8") == body + instantiation
    assert includes == [str(original.parent)]
    modified = patched.stat().st_mtime_ns
    assert _msvc_gsplat_sources([str(original)], str(tmp_path / "cache")) == (sources, includes)
    assert patched.stat().st_mtime_ns == modified


def test_already_correct_cuda_source_is_used_directly(tmp_path: Path) -> None:
    source = tmp_path / "RasterizeToPixelsFromWorld3DGSFwd.cu"
    source.write_text("#define __INS__(CDIM) template void launch(at::Tensor renders);", encoding="utf-8")
    assert _msvc_gsplat_sources([str(source)], str(tmp_path / "cache")) == ([str(source)], [])
    assert not (tmp_path / "cache").exists()


def test_unrelated_extensions_are_not_read_or_copied(tmp_path: Path) -> None:
    sources = [str(tmp_path / "Other.cu"), str(tmp_path / "ext.cpp")]
    assert _msvc_gsplat_sources(sources, str(tmp_path / "cache")) == (sources, [])


def test_unix_host_flags_are_translated_for_msvc() -> None:
    assert _msvc_gsplat_flags(["-O3", "-Wno-attributes", "-DFOO=1"]) == ["/O2", "-DFOO=1"]
    assert _msvc_gsplat_flags(["-O0"]) == ["/Od"]


def test_jit_wrapper_preserves_sycl_arguments_and_other_extensions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    from torch.utils import cpp_extension

    calls = []

    def compiler(
        name, sources, extra_cflags, extra_cuda_cflags, extra_sycl_cflags,
        extra_ldflags, extra_include_paths, build_directory, verbose,
        *, with_cuda, with_sycl, is_python_module, is_standalone, keep_intermediates,
    ):
        calls.append((name, extra_cflags, extra_sycl_cflags, build_directory, with_sycl))
        return "compiled"

    monkeypatch.setattr(cpp_extension, "_jit_compile", compiler)
    monkeypatch.setattr(cpp_extension, "COMMON_MSVC_FLAGS", [])
    monkeypatch.setattr(native_build, "os", SimpleNamespace(name="nt", environ={}))
    native_build.configure_native_build()
    wrapper = cpp_extension._jit_compile
    native_build.configure_native_build()
    assert cpp_extension._jit_compile is wrapper
    arguments = ([], ["-O3", "-Wno-attributes"], [], None, [], [], str(tmp_path), False)
    options = dict(
        with_cuda=True, with_sycl=False, is_python_module=True,
        is_standalone=False, keep_intermediates=True,
    )
    assert wrapper("gsplat_cuda", *arguments, **options) == "compiled"
    assert calls[-1] == ("gsplat_cuda", ["/O2"], None, str(tmp_path), False)
    assert wrapper("another_extension", *arguments, **options) == "compiled"
    assert calls[-1][1] == ["-O3", "-Wno-attributes"]
