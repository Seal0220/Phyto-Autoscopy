from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from threading import Event
from typing import Any

from app.analysis.export.json_export import write_json_atomic
from app.core.exceptions import AnalysisError, OperationCancelledError


WorkerProgressCallback = Callable[[str, float, str | None], None]


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise AnalysisError(f"工作輸出格式無效：{path.name}")
    return payload


def _assert_output_path(root: Path, value: object) -> str | None:
    if value is None:
        return None
    path = Path(str(value)).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise AnalysisError("模型工作回傳了輸出目錄外的路徑。") from error
    if not path.is_file():
        raise AnalysisError(f"模型工作缺少預期輸出：{path.name}")
    return str(path)


def run_reconstruction_worker(
    job: Mapping[str, Any],
    output_dir: Path,
    cancel_event: Event,
    *,
    progress_callback: WorkerProgressCallback | None = None,
    cancellation_grace_seconds: float = 8.0,
) -> dict[str, Any]:
    """Run one GPU-heavy Round in an isolated, cancellable interpreter."""

    root = output_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    control_dir = root / "worker"
    control_dir.mkdir(parents=True, exist_ok=True)
    job_path = control_dir / "job.json"
    result_path = control_dir / "result.json"
    progress_path = control_dir / "progress.json"
    cancel_path = control_dir / "cancel.request"
    stdout_path = control_dir / "stdout.log"
    stderr_path = control_dir / "stderr.log"
    for stale in (result_path, progress_path, cancel_path):
        stale.unlink(missing_ok=True)
    write_json_atomic(job_path, dict(job))

    backend_root = Path(__file__).resolve().parents[3]
    environment = os.environ.copy()
    existing_python_path = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = os.pathsep.join(
        item
        for item in (str(backend_root), existing_python_path)
        if item
    )
    command = [
        sys.executable,
        "-m",
        "app.analysis.reconstruction.worker_process",
        "--job",
        str(job_path),
        "--output",
        str(root),
        "--result",
        str(result_path),
        "--progress",
        str(progress_path),
        "--cancel",
        str(cancel_path),
    ]
    last_progress_timestamp = None
    cancellation_started_at = None
    with (
        stdout_path.open("w", encoding="utf-8", errors="replace") as stdout,
        stderr_path.open("w", encoding="utf-8", errors="replace") as stderr,
    ):
        process = subprocess.Popen(
            command,
            cwd=backend_root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            shell=False,
        )
        try:
            while process.poll() is None:
                if cancel_event.is_set() and cancellation_started_at is None:
                    cancel_path.touch(exist_ok=True)
                    cancellation_started_at = time.monotonic()
                if (
                    cancellation_started_at is not None
                    and time.monotonic() - cancellation_started_at
                    > cancellation_grace_seconds
                ):
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
                    break
                if progress_path.is_file():
                    try:
                        modified = progress_path.stat().st_mtime_ns
                        if modified != last_progress_timestamp:
                            progress = _read_json(progress_path)
                            last_progress_timestamp = modified
                            if (
                                progress_callback is not None
                                and not cancel_event.is_set()
                            ):
                                progress_callback(
                                    str(progress.get("stage") or "reconstructing_round_model"),
                                    float(progress.get("progress") or 0.0),
                                    (
                                        str(progress["message"])
                                        if progress.get("message")
                                        else None
                                    ),
                                )
                    except (OSError, ValueError, json.JSONDecodeError):
                        # Atomic replacement can still race with antivirus or
                        # networked filesystems; the next poll retries it.
                        pass
                time.sleep(0.1)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
        return_code = process.returncode

    payload = _read_json(result_path) if result_path.is_file() else {}
    if cancel_event.is_set() or payload.get("status") == "cancelled":
        raise OperationCancelledError(
            str(payload.get("error") or "分析已由使用者取消。")
        )
    if return_code != 0 or payload.get("status") != "completed":
        message = str(payload.get("error") or "模型工作異常結束。")
        raise AnalysisError(message)

    payload["gaussian_model_path"] = _assert_output_path(
        root,
        payload.get("gaussian_model_path"),
    )
    payload["point_cloud_path"] = _assert_output_path(
        root,
        payload.get("point_cloud_path"),
    )
    payload["checkpoint_path"] = _assert_output_path(
        root,
        payload.get("checkpoint_path"),
    )
    previews = payload.get("preview_paths") or []
    if not isinstance(previews, list):
        raise AnalysisError("模型預覽輸出格式無效。")
    payload["preview_paths"] = [
        checked
        for item in previews
        if (checked := _assert_output_path(root, item)) is not None
    ]
    return payload
