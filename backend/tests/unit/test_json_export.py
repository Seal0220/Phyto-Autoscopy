from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
from threading import Timer

import pytest

from app.analysis.export import json_export


@pytest.mark.parametrize("winerror", [5, 32, 33])
def test_atomic_json_retries_windows_lock_without_exposing_partial_json(monkeypatch, tmp_path, winerror):
    path = tmp_path / "result.json"
    path.write_text('{"old": true}', encoding="utf-8")
    replace = Path.replace
    attempts = []
    delays = []

    def locked_then_replace(source, target):
        attempts.append(source)
        if len(attempts) <= 2:
            assert json.loads(path.read_text(encoding="utf-8")) == {"old": True}
            error = PermissionError("temporarily locked")
            error.winerror = winerror
            raise error
        return replace(source, target)

    monkeypatch.setattr(Path, "replace", locked_then_replace)
    monkeypatch.setattr(json_export, "sleep", delays.append)
    json_export.write_json_atomic(path, {"new": True})
    assert json.loads(path.read_text(encoding="utf-8")) == {"new": True}
    assert len(attempts) == 3
    assert delays == [0.01, 0.02]
    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.parametrize(("winerror", "attempt_count"), [(5, 6), (32, 6), (33, 6), (None, 1), (112, 1)])
def test_atomic_json_still_reports_permanent_failures(monkeypatch, tmp_path, winerror, attempt_count):
    path = tmp_path / "result.json"
    path.write_text('{"old": true}', encoding="utf-8")
    attempts = []

    def denied(source, target):
        attempts.append(source)
        error = PermissionError("persistently denied")
        if winerror is not None:
            error.winerror = winerror
        raise error

    monkeypatch.setattr(Path, "replace", denied)
    monkeypatch.setattr(json_export, "sleep", lambda _: None)
    with pytest.raises(PermissionError, match="persistently denied"):
        json_export.write_json_atomic(path, {"new": True})
    assert len(attempts) == attempt_count
    assert json.loads(path.read_text(encoding="utf-8")) == {"old": True}
    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.skipif(os.name != "nt", reason="Requires Windows file sharing semantics")
def test_atomic_json_recovers_from_real_windows_reader_lock(tmp_path):
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = (
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    )
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    path = tmp_path / "processing_preview.json"
    path.write_text('{"old": true}', encoding="utf-8")
    # Allow reading/writing, but deny FILE_SHARE_DELETE as an ordinary reader can.
    handle = kernel32.CreateFileW(str(path), 0x80000000, 0x3, None, 3, 0, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    timer = None
    try:
        probe = tmp_path / "probe.tmp"
        probe.write_text("{}", encoding="utf-8")
        with pytest.raises(PermissionError) as error:
            probe.replace(path)
        assert error.value.winerror in {5, 32, 33}
        probe.unlink()
        timer = Timer(0.05, kernel32.CloseHandle, args=(handle,))
        timer.start()
        json_export.write_json_atomic(path, {"new": True})
        assert json.loads(path.read_text(encoding="utf-8")) == {"new": True}
        assert list(tmp_path.glob("*.tmp")) == []
    finally:
        if timer is None:
            kernel32.CloseHandle(handle)
        else:
            timer.join()
