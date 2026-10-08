from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError, wait, FIRST_COMPLETED
from pathlib import Path
from queue import Queue
from threading import RLock
from time import monotonic
from typing import Any
from uuid import uuid4

import cv2
import numpy as np

from app.analysis.checkpoints import StepJournal, step_signature
from app.analysis.gpu_operations import convert_color
from app.analysis.export.json_export import write_json_atomic
from app.analysis.image_probe import AnalysisImageProbe, read_analysis_image
from app.analysis.intrinsics.undistortion import FisheyeRemapCache
from app.analysis.rounds.paths import round_artifact_directory, safe_artifact_name
from app.models.analysis_models import AnalysisView


def _read_image(path: Path) -> np.ndarray:
    image = read_analysis_image(path, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"影像無法解碼：{path.name}")
    return image


def _write_image(path: Path, image: np.ndarray) -> None:
    options = [cv2.IMWRITE_TIFF_COMPRESSION, 5] if path.suffix == ".tiff" else []
    if path.suffix == ".jpg":
        options = [cv2.IMWRITE_JPEG_QUALITY, 90]
    success, encoded = cv2.imencode(path.suffix, image, options)
    if not success:
        raise ValueError(f"影像無法編碼：{path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        encoded.tofile(temporary)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class UndistortionProcessor:
    """One source read for hashing, PNG decoding, TIFF preparation and remapping."""

    def __init__(self, views, snapshots, root: Path, *, cancel_check=None, source_manifest=()) -> None:
        self.root = root
        self.views = {str(Path(view.absolute_path)): view for view in views}
        self.snapshots = snapshots
        self.cancel_check = cancel_check
        self.reader = AnalysisImageProbe(root / "image_cache", initialize_decoder=False)
        self.cache = FisheyeRemapCache()
        self.journal = StepJournal(root)
        self.expected = {item["absolute_path"]: item for item in source_manifest}
        self.hashes: dict[str, str] = {}
        self.results: dict[str, dict] = {}
        self.reused = 0
        self.reused_gpu = 0
        self.reused_cpu = 0
        self._mask_lock = RLock()

    def __call__(self, source: Path) -> tuple[int, int] | None:
        if self.cancel_check:
            self.cancel_check()
        stat = source.stat()
        expected = self.expected.get(str(source))
        if expected and (stat.st_size != expected["size_bytes"] or stat.st_mtime_ns != expected["modified_ns"]):
            raise ValueError(f"分析輸入在建立後已變更：{source.name}")
        view = self.views.get(str(source))
        snapshot = self.snapshots.get(view.camera_id) if view else None
        signature = step_signature({
            "version": 2, "source": str(source), "size": stat.st_size, "mtime": stat.st_mtime_ns,
            "sha256": expected.get("sha256") if expected else (view.image_sha256 if view else None),
            "intrinsics": snapshot,
        })
        stage = "undistorting_images" if view else "validating_images"
        item = view.view_id if view else str(source)
        completed = self.journal.get(stage, item, signature)
        if completed:
            self.hashes[str(source)] = completed["sha256"]
            if view:
                self.results[view.view_id] = completed["result"]
            self.reused += 1
            if view:
                if completed.get("backend") == "cuda":
                    self.reused_gpu += 1
                else:
                    self.reused_cpu += 1
            return tuple(completed["resolution"])
        encoded = np.fromfile(source, dtype=np.uint8)
        digest = hashlib.sha256(encoded).hexdigest()
        frozen_digest = expected.get("sha256") if expected else (view.image_sha256 if view else None)
        if frozen_digest and digest != frozen_digest:
            raise ValueError(f"分析輸入內容在建立後已變更：{source.name}")
        self.hashes[str(source)] = digest
        self.journal.save("verifying_input_files", item, signature, {"sha256": digest, "backend": "cpu"})
        if source.suffix.lower() in self.reader.GPU_EXTENSIONS:
            image = self.reader.read(source)
        else:
            original = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
            if original is None:
                return None
            prepared = self.reader.prepare(source, image=original)
            self.journal.save("converting_images", item, signature,
                              {"backend": "cpu", "path": str(prepared)}, outputs=[prepared])
            image = original
            if image.dtype == np.uint16:
                image = (image >> 8).astype(np.uint8)
            if image.ndim == 2:
                image = convert_color(image, cv2.COLOR_GRAY2BGR)
            elif image.shape[2] == 4:
                image = convert_color(image, cv2.COLOR_BGRA2BGR)
            self.reader.cpu_decoded += 1
        if image is None:
            return None
        resolution = (int(image.shape[1]), int(image.shape[0]))
        outputs = []
        payload = {"sha256": digest, "resolution": resolution, "backend": "cpu"}
        if view:
            if snapshot is None:
                raise ValueError(f"找不到 {view.camera_id} 的內參快照。")
            if resolution != (int(snapshot["analysis_image_width"]), int(snapshot["analysis_image_height"])):
                raise ValueError(f"{view.camera_id} 影像解析度在建立分析後發生變化。")
            before_gpu = self.cache.backend_counts["gpu"]
            undistorted, valid_mask = self.cache.undistort(image, snapshot)
            backend = "cuda" if self.cache.backend_counts["gpu"] > before_gpu else "cpu"
            round_root = round_artifact_directory(self.root, view.round_key) / "undistortion"
            image_path = round_root / "images" / f"{safe_artifact_name(view.view_id)}.tiff"
            preview_path = image_path.with_suffix(".jpg")
            mask_path = round_root / "valid_masks" / f"{view.camera_id}.png"
            _write_image(image_path, undistorted)
            _write_image(preview_path, undistorted)
            mask_signature = step_signature(snapshot)
            mask_key = f"{view.round_key}:{view.camera_id}"
            with self._mask_lock:
                if self.journal.get("valid_pixel_masks", mask_key, mask_signature) is None:
                    _write_image(mask_path, valid_mask)
                    self.journal.save("valid_pixel_masks", mask_key, mask_signature, {"backend": "cpu"}, outputs=[mask_path])
            result = {
                "view_id": view.view_id, "round_key": view.round_key, "camera_id": view.camera_id,
                "source_relative_path": view.relative_path, "source_sha256": digest,
                "undistorted_path": str(image_path.relative_to(self.root)),
                "preview_path": str(preview_path.relative_to(self.root)),
                "valid_pixel_mask_path": str(mask_path.relative_to(self.root)),
                "coordinate_space": "undistorted", "intrinsics_version": snapshot["intrinsics_version"],
                "image_width": resolution[0], "image_height": resolution[1], "backend": backend,
            }
            self.results[view.view_id] = result
            outputs = [image_path, preview_path, mask_path]
            payload.update(result=result, backend=backend)
        self.journal.save(stage, item, signature, payload, outputs=outputs)
        return resolution

    @property
    def backend_counts(self):
        return {**self.reader.backend_counts, "remap_gpu": self.cache.backend_counts["gpu"],
                "remap_cpu": self.cache.backend_counts["cpu"], "reused": self.reused,
                "reused_gpu": self.reused_gpu, "reused_cpu": self.reused_cpu}

    def manifest(self, views, *, manifest_path: Path | None = None):
        results = [self.results[view.view_id] for view in views]
        write_json_atomic(manifest_path or self.root / "undistortion_manifest.json",
                          {"coordinate_space": "undistorted", "views": results})
        return results

    def close(self):
        try:
            self.reader.close()
        finally:
            self.cache.close()
            self.journal.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def automatic_image_workers(
    snapshots: Mapping, *, available_ram=None, available_vram=None,
    cpu_count=None, maximum_workers: int = 128,
) -> int:
    """Overlap image I/O beyond core count, within host and CUDA memory budgets."""
    cores = cpu_count if cpu_count is not None else (os.cpu_count() or 1)
    if available_ram is None:
        try:
            import psutil

            available_ram = psutil.virtual_memory().available
        except ImportError:
            available_ram = 1024 ** 3
    if available_vram is None:
        try:
            import torch

            available_vram = torch.cuda.mem_get_info()[0] if torch.cuda.is_available() else 0
        except Exception:
            available_vram = 0
    pixels = [int(value["analysis_image_width"]) * int(value["analysis_image_height"]) for value in snapshots.values()]
    largest = max(pixels, default=1920 * 1080)
    # Immutable camera maps are shared; only active image buffers scale with threads.
    host_bytes = max(largest * 32, 32 * 1024 ** 2)
    gpu_bytes = max(largest * 32, 32 * 1024 ** 2)
    workers = min(maximum_workers, cores * 8,
                  max(1, (int(available_ram * .6) - sum(pixels) * 12) // host_bytes))
    if available_vram:
        workers = min(workers, max(1, (int(available_vram * .7) - sum(pixels) * 16) // gpu_bytes))
    return max(1, workers)


class ImageConcurrencyTuner:
    """Try increasing windows on actual images, then keep the fastest window."""

    def __init__(self, limit: int, initial: int, *, clock=monotonic) -> None:
        self.clock = clock
        initial = min(max(1, initial), limit)
        self.candidates = sorted({min(limit, initial * factor) for factor in (1, 2, 4, 8)} | {limit})
        self.workers = self.candidates[0]
        self.rates: dict[int, float] = {}
        self.samples = 0
        self.started = clock()
        self.finished = len(self.candidates) == 1

    def completed(self) -> int:
        if self.finished:
            return self.workers
        self.samples += 1
        now = self.clock()
        elapsed = now - self.started
        if self.samples < max(128, self.workers * 2) or elapsed < 1.0:
            return self.workers
        self.rates[self.workers] = self.samples / elapsed
        index = self.candidates.index(self.workers)
        if index + 1 < len(self.candidates):
            self.workers = self.candidates[index + 1]
        else:
            fastest = max(self.rates, key=self.rates.get)
            # Keep fewer threads when measured speeds differ by less than 10%.
            threshold = self.rates[fastest] / 1.1
            self.workers = min(workers for workers, rate in self.rates.items() if rate >= threshold)
            self.finished = True
        self.samples = 0
        self.started = now
        return self.workers


class ParallelUndistortionProcessor(UndistortionProcessor):
    """Bounded image pipeline with thread-owned CUDA caches and SQLite connections.

    Futures contain a resolution and reuse flag; decoded pixels stay in the worker. The
    coordinator consumes results in record order while subsequent images run.
    """

    def __init__(self, *args, maximum_workers: int | None = None, **kwargs) -> None:
        if maximum_workers is not None and maximum_workers < 1:
            raise ValueError("影像執行緒數至少為 1。")
        super().__init__(*args, **kwargs)
        self.worker_limit = min(
            automatic_image_workers(self.snapshots, maximum_workers=maximum_workers or 128),
            max(len(self.views), len(self.expected), 1),
        )
        self._tuner = ImageConcurrencyTuner(self.worker_limit, os.cpu_count() or 1) if maximum_workers is None else None
        self.worker_count = self._tuner.workers if self._tuner else self.worker_limit
        self._tuning_mode = None
        self._state_lock = RLock()
        self._workers = []
        self._pending: dict[str, Future] = {}
        self._resolved: dict[str, object] = {}
        self._sources = iter(())
        self._queue = Queue(maxsize=self.worker_limit)
        self._executor = ThreadPoolExecutor(max_workers=self.worker_limit, thread_name_prefix="analysis-image")
        self._closed = False
        self._loops = [self._executor.submit(self._worker_loop) for _ in range(self.worker_count)]

    def _new_worker(self):
        # Share immutable input indexes and result metadata, not native handles.
        worker = UndistortionProcessor.__new__(UndistortionProcessor)
        for name in ("root", "views", "snapshots", "cancel_check", "expected", "hashes", "results", "_mask_lock"):
            setattr(worker, name, getattr(self, name))
        worker.reader = AnalysisImageProbe(self.root / "image_cache", initialize_decoder=False)
        worker.cache = FisheyeRemapCache(shared_maps=self.cache.shared_maps)
        try:
            worker.journal = StepJournal(self.root)
        except Exception:
            worker.reader.close()
            raise
        worker.reused = 0
        worker.reused_gpu = 0
        worker.reused_cpu = 0
        with self._state_lock:
            self._workers.append(worker)
        return worker

    def _worker_loop(self):
        worker = None
        try:
            while True:
                task = self._queue.get()
                if task is None:
                    return
                source, future = task
                if not future.set_running_or_notify_cancel():
                    continue
                try:
                    if worker is None:
                        worker = self._new_worker()
                    previous_reused = worker.reused
                    resolution = worker(source)
                    future.set_result((resolution, worker.reused > previous_reused))
                except Exception as error:
                    future.set_exception(error)
        finally:
            if worker is not None:
                worker.close()

    def _check_cancel(self):
        if self.cancel_check is not None:
            self.cancel_check()

    def _submit(self, source: Path):
        future = Future()
        self._pending[str(source)] = future
        self._queue.put((source, future))
        return future

    def _collect_finished(self):
        for key, future in list(self._pending.items()):
            if future.done():
                try:
                    self._resolved[key] = future.result()
                except Exception as error:
                    self._resolved[key] = error
                del self._pending[key]

    def _fill(self):
        # Completed out-of-order results also occupy the lookahead window.
        while len(self._pending) + len(self._resolved) < self.worker_count:
            self._check_cancel()
            source = next(self._sources, None)
            if source is None:
                return
            source = Path(source)
            if str(source) not in self._pending and str(source) not in self._resolved:
                self._submit(source)

    def prefetch(self, sources):
        self._sources = iter(sources)
        self._fill()

    def __call__(self, source: Path):
        self._check_cancel()
        key = str(source)
        self._collect_finished()
        if key not in self._pending and key not in self._resolved:
            # The validator can skip invalid entries or encounter a new file.
            # Make room without decoding an unbounded number of images.
            while len(self._pending) >= self.worker_count:
                wait(tuple(self._pending.values()), timeout=.1, return_when=FIRST_COMPLETED)
                self._check_cancel()
                self._collect_finished()
            # Skipped validator entries are already checkpointed. Their tiny
            # resolutions must not stall lookahead for subsequent valid files.
            self._resolved.clear()
            self._submit(source)
        if key in self._pending:
            future = self._pending[key]
            while not future.done():
                try:
                    future.result(timeout=.1)
                except TimeoutError:
                    self._check_cancel()
                except Exception:
                    break
            self._collect_finished()
        outcome = self._resolved.pop(key)
        if isinstance(outcome, Exception):
            raise outcome
        resolution, reused = outcome
        if self._tuner is not None:
            if self._tuning_mode != reused:
                # Restored results and fresh GPU work have different costs.
                self._tuner = ImageConcurrencyTuner(self.worker_limit, os.cpu_count() or 1)
                self._tuning_mode = reused
            self.worker_count = self._tuner.completed()
            while len(self._loops) < self.worker_count:
                self._loops.append(self._executor.submit(self._worker_loop))
        self._fill()
        return resolution

    @property
    def backend_counts(self):
        counts = {"gpu": 0, "cpu": 0, "converted": 0, "conversion_failed": 0,
                  "remap_gpu": 0, "remap_cpu": 0, "reused": 0, "reused_gpu": 0,
                  "reused_cpu": 0, "workers": self.worker_count, "worker_limit": self.worker_limit,
                  "tuning": int(self._tuner is not None and not self._tuner.finished)}
        with self._state_lock:
            for worker in self._workers:
                for key, value in worker.backend_counts.items():
                    counts[key] += value
        return counts

    def close(self):
        if self._closed:
            return
        self._closed = True
        for future in self._pending.values():
            future.cancel()
        for _ in self._loops:
            self._queue.put(None)
        self._executor.shutdown(wait=True)
        try:
            for loop in self._loops:
                loop.result()
        finally:
            super().close()


def undistort_analysis_views(
    views: Sequence[AnalysisView],
    intrinsics_snapshot: Mapping[str, Mapping[str, Any]],
    output_root: Path,
    *,
    cancel_check: Callable[[], None] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    source_manifest: Sequence[dict] = (),
    maximum_workers: int | None = None,
    backend_callback: Callable[[dict[str, int]], None] | None = None,
    manifest_path: Path | None = None,
) -> list[dict[str, Any]]:
    with ParallelUndistortionProcessor(views, intrinsics_snapshot, output_root,
                                      cancel_check=cancel_check, source_manifest=source_manifest,
                                      maximum_workers=maximum_workers) as processor:
        if backend_callback:
            backend_callback(processor.backend_counts)
        processor.prefetch(Path(view.absolute_path) for view in views)
        for index, view in enumerate(views, start=1):
            if processor(Path(view.absolute_path)) is None:
                raise ValueError(f"影像無法解碼：{view.relative_path}")
            if backend_callback:
                backend_callback(processor.backend_counts)
            if progress_callback:
                progress_callback(index, len(views))
        return processor.manifest(views, manifest_path=manifest_path)
