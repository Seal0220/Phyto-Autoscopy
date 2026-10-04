from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from app.analysis.image_probe import AnalysisImageProbe


def _probe(tmp_path, decoder=None):
    probe = AnalysisImageProbe.__new__(AnalysisImageProbe)
    probe.cache_root = tmp_path / "derived"
    probe._temporary_cache = None
    probe._gpu_decoder = decoder
    probe._decode_params = None
    probe._gpu_failures = {}
    probe.gpu_decoded = probe.cpu_decoded = probe.converted = probe.conversion_failed = 0
    return probe


@pytest.mark.parametrize(("dtype", "channels"), [(np.uint8, 1), (np.uint8, 3), (np.uint8, 4), (np.uint16, 1), (np.uint16, 3)])
def test_tiff_conversion_preserves_pixels_depth_source_and_reuses_cache(tmp_path, dtype, channels):
    shape = (20, 30) if channels == 1 else (20, 30, channels)
    image = np.random.default_rng(4).integers(0, np.iinfo(dtype).max, shape, dtype=dtype)
    source = tmp_path / "來源.png"
    cv2.imencode(".png", image)[1].tofile(source)
    original = source.read_bytes()
    probe = _probe(tmp_path)
    prepared = probe.prepare(source)
    assert prepared.suffix == ".tiff"
    assert prepared.is_relative_to(probe.cache_root)
    assert np.array_equal(cv2.imdecode(np.fromfile(prepared, dtype=np.uint8), -1), image)
    modified = prepared.stat().st_mtime_ns
    assert probe.prepare(source) == prepared
    assert prepared.stat().st_mtime_ns == modified
    assert probe.converted == 1
    assert source.read_bytes() == original
    assert np.array_equal(probe.read(source, cv2.IMREAD_UNCHANGED), image)


def test_png_is_converted_before_gpu_validation_and_gpu_failure_falls_back(tmp_path):
    source = tmp_path / "source.png"
    cv2.imencode(".png", np.zeros((20, 30, 3), np.uint8))[1].tofile(source)
    calls = []

    def decode(path, **kwargs):
        calls.append(Path(path))
        return SimpleNamespace(width=30, height=20)

    probe = _probe(tmp_path, SimpleNamespace(read=decode))
    assert probe(source) == (30, 20)
    assert calls[0].suffix == ".tiff"
    assert probe.backend_counts == {"gpu": 1, "cpu": 0, "converted": 1, "conversion_failed": 0}
    probe._gpu_decoder.read = lambda *args, **kwargs: None
    assert probe(source) == (30, 20)
    assert probe.cpu_decoded == 1


def test_conversion_failure_and_corrupt_source_are_not_accepted(tmp_path, monkeypatch):
    source = tmp_path / "source.png"
    cv2.imencode(".png", np.zeros((20, 30, 3), np.uint8))[1].tofile(source)
    probe = _probe(tmp_path)
    monkeypatch.setattr(probe, "prepare", lambda _: (_ for _ in ()).throw(PermissionError("locked cache")))
    assert probe(source) == (30, 20)
    assert probe.conversion_failed == 1
    assert probe.cpu_decoded == 1
    source.write_bytes(b"corrupt PNG")
    assert probe(source) is None
    assert probe.read(source) is None


def test_modified_source_does_not_reuse_old_tiff(tmp_path):
    source = tmp_path / "source.png"
    cv2.imencode(".png", np.zeros((20, 30, 3), np.uint8))[1].tofile(source)
    probe = _probe(tmp_path)
    previous = probe.prepare(source)
    cv2.imencode(".png", np.ones((21, 31, 3), np.uint8))[1].tofile(source)
    assert probe.prepare(source) != previous
    assert probe(source) == (31, 21)
