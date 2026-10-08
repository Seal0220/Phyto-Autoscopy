from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import Barrier, Event, RLock
from collections import Counter
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from app.analysis.analysis_runner import AnalysisJobManager
from app.analysis.checkpoints import StepJournal, checkpoint_summary
from app.analysis.gpu_operations import binary_morphology, cuda_hamming_matches, cuda_projection_support
from app.analysis.intrinsics.undistortion import FisheyeRemapCache
from app.analysis.intrinsics.undistortion_pipeline import (
    UndistortionProcessor, ParallelUndistortionProcessor, automatic_image_workers, ImageConcurrencyTuner,
)
from app.analysis.intrinsics import undistortion_pipeline
from app.core.exceptions import AnalysisPausedError
from app.models.analysis_models import AnalysisRound, AnalysisRun, AnalysisView
from app.services.analysis_service import AnalysisService


def _fixture(tmp_path, count=2):
    width, height = 160, 120
    matrix = [[130, 0, 80], [0, 130, 60], [0, 0, 1]]
    snapshot = {
        "camera_id": "top", "intrinsics_version": "test", "camera_model": "opencv",
        "analysis_image_width": width, "analysis_image_height": height,
        "adapted_camera_matrix": matrix, "undistorted_camera_matrix": matrix,
        "distortion_coefficients": [.2, -.05, .001, -.002, 0],
    }
    views = []
    for index in range(count):
        path = tmp_path / f"來源-{index}.png"
        image = np.random.default_rng(index).integers(0, 256, (height, width, 3), dtype=np.uint8)
        cv2.imencode(".png", image)[1].tofile(path)
        views.append(AnalysisView(
            analysis_id="analysis-test", round_key="record:mode:round.01", view_id=f"view-{index}",
            capture_id=index, camera_id="top", timestamp="2026-10-05T00:00:00+00:00",
            relative_path=path.name, absolute_path=str(path), image_width=width, image_height=height,
            image_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        ))
    return views, {"top": snapshot}


def test_fused_processing_reads_png_once_and_resumes_each_finished_image(tmp_path, monkeypatch):
    views, snapshots = _fixture(tmp_path)
    root = tmp_path / "analysis-test"
    original_read = np.fromfile
    reads = []

    def read(path, *args, **kwargs):
        reads.append(str(path))
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(np, "fromfile", read)
    with UndistortionProcessor(views, snapshots, root) as processor:
        assert processor(Path(views[0].absolute_path)) == (160, 120)
        first = dict(processor.results[views[0].view_id])
    assert reads == [views[0].absolute_path]
    before = (root / first["undistorted_path"]).stat().st_mtime_ns
    with UndistortionProcessor(views, snapshots, root) as processor:
        for view in views:
            processor(Path(view.absolute_path))
        results = processor.manifest(views)
        assert processor.reused == 1
    assert reads == [view.absolute_path for view in views]
    assert (root / first["undistorted_path"]).stat().st_mtime_ns == before
    assert all(Path(item["undistorted_path"]).suffix == ".tiff" for item in results)
    assert all((root / item["preview_path"]).is_file() for item in results)
    with StepJournal(root) as journal:
        assert journal.get("undistorting_images", views[0].view_id)["resolution"] == [160, 120]
    assert checkpoint_summary(root)["completed_steps"] >= 6


def test_source_changes_and_missing_outputs_cannot_reuse_results(tmp_path):
    views, snapshots = _fixture(tmp_path, 1)
    source = Path(views[0].absolute_path)
    root = tmp_path / "analysis-test"
    with UndistortionProcessor(views, snapshots, root) as processor:
        processor(source)
        output = root / processor.results[views[0].view_id]["undistorted_path"]
    output.unlink()
    with UndistortionProcessor(views, snapshots, root) as processor:
        processor(source)
        assert processor.reused == 0
    source.write_bytes(b"changed")
    with UndistortionProcessor(views, snapshots, root) as processor:
        with pytest.raises(ValueError, match="內容在建立後已變更"):
            processor(source)


def test_cuda_remapping_matches_cpu_interpolation_and_cpu_fallback(tmp_path, monkeypatch):
    import torch

    views, snapshots = _fixture(tmp_path, 1)
    image = cv2.imdecode(np.fromfile(views[0].absolute_path, np.uint8), cv2.IMREAD_COLOR)
    cache = FisheyeRemapCache()
    snapshot = snapshots["top"]
    entry = cache.get(snapshot)
    expected = cv2.remap(image, entry.map_x, entry.map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    actual, mask = cache.undistort(image, snapshot)
    assert np.max(np.abs(actual.astype(np.int16) - expected.astype(np.int16))) <= 1
    assert np.array_equal(mask, entry.valid_pixel_mask)
    if torch.cuda.is_available():
        assert cache.backend_counts == {"gpu": 1, "cpu": 0}
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    cpu = FisheyeRemapCache()
    cpu._opencv_cuda_available = False
    actual, _ = cpu.undistort(image, snapshot)
    assert np.array_equal(actual, expected)
    assert cpu.backend_counts == {"gpu": 0, "cpu": 1}


def test_cuda_matching_and_binary_morphology_preserve_cpu_results(monkeypatch):
    from app.analysis.pose_alignment.markerless_pose import _matches
    import torch

    if not torch.cuda.is_available():
        pytest.skip("CUDA is unavailable")
    rng = np.random.default_rng(42)
    first = rng.integers(0, 256, (90, 32), dtype=np.uint8)
    second = np.vstack((first.copy(), first[0:2], rng.integers(0, 256, (20, 32), dtype=np.uint8)))
    actual = cuda_hamming_matches(first, second)
    assert actual is not None
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    expected = _matches(first, second)
    assert [(item.queryIdx, item.trainIdx, item.distance) for item in actual] == [
        (item.queryIdx, item.trainIdx, item.distance) for item in expected
    ]
    monkeypatch.undo()
    mask = (rng.random((100, 120)) > .35).astype(np.uint8) * 255
    opening = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    closing = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    expected = cv2.morphologyEx(cv2.morphologyEx(mask, cv2.MORPH_OPEN, opening), cv2.MORPH_CLOSE, closing)
    assert np.array_equal(binary_morphology(mask, opening, closing), expected)


def test_cuda_point_projection_preserves_visibility_and_support():
    import torch

    if not torch.cuda.is_available():
        pytest.skip("CUDA is unavailable")
    points = np.array([[1, 1, 1], [2, 3, 1], [100, 20, 1], [1, 1, -1]], dtype=np.float64)
    mask = np.zeros((8, 8), dtype=bool)
    mask[1, 1] = True
    projection = np.eye(3, 4)
    actual = cuda_projection_support(points, [(projection, mask)] * 2)
    assert actual is not None
    assert np.array_equal(actual[0], [2, 0, 0, 0])
    assert np.array_equal(actual[1], [2, 2, 0, 0])


def _service(tmp_path, status="processing"):
    service = AnalysisService.__new__(AnalysisService)
    run = AnalysisRun(
        analysis_id="analysis-test", record_id="record", method_name="fixed", method_version="1",
        git_commit="test", parameters={}, created_by="test", created_at="2026-10-05T00:00:00+00:00",
        updated_at="2026-10-05T00:00:00+00:00", output_path=str(tmp_path), status=status,
    )
    state = {"run": run, "loads": 0}
    service._lock = service._preview_lock = RLock()
    service._processing_previews = {}
    service._validation_progress = {}
    service._validation_progress_times = {}
    service._live_progress = {}
    service.progress_callback = None
    service._log = lambda *args: None
    service._artifacts = lambda _: SimpleNamespace(root=tmp_path, write_run=lambda _: None)

    def get(_):
        state["loads"] += 1
        return state["run"]

    def update(_, **kwargs):
        changes = {key: value for key, value in kwargs.items() if value is not None and key != "clear_error"}
        if kwargs.get("clear_error"):
            changes["last_error"] = None
        state["run"] = state["run"].model_copy(update=changes)

    service._require_run = get
    service.repository = SimpleNamespace(
        update_state=update,
        list_rounds=lambda _: [AnalysisRound(analysis_id="analysis-test", round_key="record:mode:round.01",
                                            record_id="record", mode_id="mode", round_id="round.01", status="ready_tip_only")],
        list_views=lambda *args: [],
        list_tip_landmarks=lambda _: [],
    )
    service._runner = AnalysisJobManager(service._run_job)
    return service, state


def test_live_state_updates_do_not_load_large_manifests(tmp_path):
    service, state = _service(tmp_path)
    try:
        for index in range(30):
            service._set_state(state["run"], stage="undistorting_images", current_frame=index, total_frames=30)
        assert state["loads"] == 0
        assert service.get_progress("analysis-test").current_frame == 29
        assert state["loads"] == 0
    finally:
        service._runner.close()


def test_paused_round_progress_restores_once_after_backend_restart(tmp_path, monkeypatch):
    service, state = _service(tmp_path, status="paused")
    saved = {
        "analysis_id": "analysis-test", "round_key": "record:mode:round.02",
        "round_id": "round.02", "current_round": 2, "total_rounds": 3, "round_progress": .4,
    }
    (tmp_path / "progress.json").write_text(json.dumps(saved), encoding="utf-8")
    try:
        assert service._progress_for_run(state["run"]).current_round == 2

        def no_disk_reads(*args, **kwargs):
            pytest.fail("restored progress must be cached")

        monkeypatch.setattr(Path, "read_text", no_disk_reads)
        progress = service._progress_for_run(state["run"])
        assert progress.round_progress == .4 and progress.total_rounds == 3
    finally:
        service._runner.close()


def test_automatic_workers_overlap_io_and_respect_memory_limits():
    snapshots = {"top": {"analysis_image_width": 1920, "analysis_image_height": 1080}}
    gib = 1024 ** 3
    assert automatic_image_workers(snapshots, cpu_count=16, available_ram=32*gib, available_vram=8*gib) == 90
    assert automatic_image_workers(snapshots, cpu_count=16, available_ram=32*gib, available_vram=24*gib) == 128
    assert automatic_image_workers(snapshots, cpu_count=16, available_ram=32*gib, available_vram=24*gib, maximum_workers=32) == 32
    assert automatic_image_workers(snapshots, cpu_count=16, available_ram=256*1024**2, available_vram=8*gib) == 2
    assert automatic_image_workers(snapshots, cpu_count=16, available_ram=32*gib, available_vram=64*1024**2) == 1
    assert automatic_image_workers(snapshots, cpu_count=16, available_ram=32*gib, available_vram=0) == 128


def test_image_concurrency_tries_128_and_selects_measured_throughput():
    now = [0.0]
    tuner = ImageConcurrencyTuner(128, 16, clock=lambda: now[0])
    # Simulate this machine's benchmark: additional threads reduce throughput.
    for workers, rate in [(16, 36.9), (32, 33.8), (64, 30.9), (128, 33.4)]:
        assert tuner.workers == workers
        for _ in range(max(128, workers * 2)):
            now[0] += 1 / rate
            tuner.completed()
    assert tuner.finished and tuner.workers == 16
    # More concurrency is retained when it actually increases throughput.
    now = [0.0]
    tuner = ImageConcurrencyTuner(128, 16, clock=lambda: now[0])
    for workers, rate in [(16, 20), (32, 30), (64, 50), (128, 90)]:
        for _ in range(max(128, workers * 2)):
            now[0] += 1 / rate
            tuner.completed()
    assert tuner.finished and tuner.workers == 128


def test_checkpoint_progress_reads_release_windows_file_handles(tmp_path):
    with StepJournal(tmp_path) as journal:
        journal.save("undistorting_images", "view", "signature", {"backend": "cuda"})
        path = journal.path
    for _ in range(20):
        assert checkpoint_summary(tmp_path)["completed_steps"] == 1
    # SQLite's transaction context does not close its connection. Windows
    # refuses this rename if a progress read left the database open.
    path.replace(path.with_name("moved.sqlite3"))


def test_parallel_images_overlap_decode_write_and_preserve_mask_checkpoints(tmp_path, monkeypatch):
    views, snapshots = _fixture(tmp_path, 9)
    root = tmp_path / "analysis-parallel"
    first_writes = Barrier(3)
    lock = RLock()
    writes = []
    reads = []
    original_write, original_read = undistortion_pipeline._write_image, np.fromfile

    def write(path, image):
        if path.suffix == ".tiff":
            with lock:
                writes.append(path)
                initial = len(writes) <= 3
            if initial:
                first_writes.wait(timeout=10)
        original_write(path, image)

    def read(path, *args, **kwargs):
        with lock:
            reads.append(str(path))
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(undistortion_pipeline, "_write_image", write)
    monkeypatch.setattr(np, "fromfile", read)
    with ParallelUndistortionProcessor(views, snapshots, root, maximum_workers=3) as processor:
        processor.prefetch(Path(view.absolute_path) for view in views)
        for view in views:
            assert processor(Path(view.absolute_path)) == (160, 120)
            assert len(processor._pending) + len(processor._resolved) <= 3
        results = processor.manifest(views)
        assert processor.backend_counts["workers"] == 3
        assert processor.backend_counts["remap_gpu"] + processor.backend_counts["remap_cpu"] == 9
        assert len(processor._workers) == 3
        assert len(processor.cache.shared_maps.entries) == 1
        assert all(worker.cache.shared_maps is processor.cache.shared_maps for worker in processor._workers)
        if cv2.cuda.getCudaEnabledDeviceCount() > 0:
            assert processor.backend_counts["remap_gpu"] == 9
            assert all(worker.cache._opencv_cuda_available for worker in processor._workers)
            assert len({id(worker.cache._opencv_cuda_stream) for worker in processor._workers}) == 3
    assert all(loop.done() for loop in processor._loops)
    assert Counter(reads) == Counter(view.absolute_path for view in views)
    assert [item["view_id"] for item in results] == [view.view_id for view in views]
    timestamps = [(root / item["undistorted_path"]).stat().st_mtime_ns for item in results]
    # Shared masks must never be rewritten by competing workers, which would
    # invalidate the output witnesses recorded by the other images.
    with ParallelUndistortionProcessor(views, snapshots, root, maximum_workers=3) as resumed:
        resumed.prefetch(Path(view.absolute_path) for view in views)
        for view in views:
            resumed(Path(view.absolute_path))
        assert resumed.backend_counts["reused"] == 9
        assert resumed.backend_counts["remap_gpu"] == 0
        if cv2.cuda.getCudaEnabledDeviceCount() > 0:
            assert resumed.backend_counts["reused_gpu"] == 9
            assert resumed.backend_counts["reused_cpu"] == 0
    assert len(writes) == 9
    assert timestamps == [(root / item["undistorted_path"]).stat().st_mtime_ns for item in results]


def test_worker_closing_does_not_release_shared_maps_used_by_other_workers(tmp_path):
    views, snapshots = _fixture(tmp_path, 1)
    owner = FisheyeRemapCache()
    first = FisheyeRemapCache(shared_maps=owner.shared_maps)
    second = FisheyeRemapCache(shared_maps=owner.shared_maps)
    try:
        entry = first.get(snapshots["top"])
        first.close()
        assert second.get(snapshots["top"]) is entry
        image = cv2.imdecode(np.fromfile(views[0].absolute_path, np.uint8), cv2.IMREAD_COLOR)
        result, mask = second.undistort(image, snapshots["top"])
        assert result.shape == image.shape and mask.shape == image.shape[:2]
    finally:
        first.close()
        second.close()
        owner.close()
    assert not owner.shared_maps.entries


def test_automatic_pool_grows_and_shrinks_without_losing_images_or_leaving_threads(tmp_path, monkeypatch):
    views, snapshots = _fixture(tmp_path, 9)

    class Tuner:
        def __init__(self, *args):
            self.workers = 1
            self.finished = False
            self.changes = iter([3, 2, 4, 1])

        def completed(self):
            self.workers = next(self.changes, 1)
            return self.workers

    monkeypatch.setattr(undistortion_pipeline, "automatic_image_workers", lambda *args, **kwargs: 4)
    monkeypatch.setattr(undistortion_pipeline, "ImageConcurrencyTuner", Tuner)
    root = tmp_path / "automatic-analysis"
    with ParallelUndistortionProcessor(views, snapshots, root) as processor:
        assert processor.worker_count == 1
        processor.prefetch(Path(view.absolute_path) for view in views)
        history = []
        for view in views:
            assert processor(Path(view.absolute_path)) == (160, 120)
            history.append(processor.worker_count)
            assert len(processor._pending) + len(processor._resolved) <= processor.worker_limit
        results = processor.manifest(views)
        assert history[:4] == [3, 2, 4, 1]
        assert len(processor._loops) == 4
        assert processor.backend_counts["worker_limit"] == 4
        assert processor.backend_counts["tuning"] == 1
        assert len(results) == len(views)
        if cv2.cuda.getCudaEnabledDeviceCount() > 0:
            assert processor.backend_counts["remap_gpu"] == 9
            assert processor.backend_counts["remap_cpu"] == 0
    assert all(loop.done() for loop in processor._loops)


def test_parallel_pause_stops_dispatch_and_reuses_completed_images(tmp_path, monkeypatch):
    views, snapshots = _fixture(tmp_path, 12)
    root = tmp_path / "analysis-paused"
    cancellation = Event()
    finished = []
    original = UndistortionProcessor.__call__
    lock = RLock()
    def check():
        if cancellation.is_set():
            raise AnalysisPausedError("pause")
    def process(self, path):
        value = original(self, path)
        with lock:
            finished.append(path)
            if len(finished) == 2:
                cancellation.set()
        return value
    monkeypatch.setattr(UndistortionProcessor, "__call__", process)
    with ParallelUndistortionProcessor(views, snapshots, root, maximum_workers=3, cancel_check=check) as processor:
        processor.prefetch(Path(view.absolute_path) for view in views)
        with pytest.raises(AnalysisPausedError):
            for view in views:
                processor(Path(view.absolute_path))
    assert 2 <= len(finished) <= 4
    assert len(finished) < len(views)
    assert all(loop.done() for loop in processor._loops)
    monkeypatch.setattr(UndistortionProcessor, "__call__", original)
    with ParallelUndistortionProcessor(views, snapshots, root, maximum_workers=3) as resumed:
        resumed.prefetch(Path(view.absolute_path) for view in views)
        for view in views:
            resumed(Path(view.absolute_path))
        assert resumed.backend_counts["reused"] == len(finished)
        assert len(resumed.manifest(views)) == len(views)


def test_parallel_tiff_inputs_initialize_decoders_in_the_worker(tmp_path):
    views, snapshots = _fixture(tmp_path, 4)
    tiff_views = []
    for view in views:
        source = Path(view.absolute_path)
        image = cv2.imdecode(np.fromfile(source, np.uint8), cv2.IMREAD_UNCHANGED)
        destination = source.with_suffix(".tiff")
        cv2.imencode(".tiff", image, [cv2.IMWRITE_TIFF_COMPRESSION, 5])[1].tofile(destination)
        tiff_views.append(view.model_copy(update={
            "absolute_path": str(destination), "relative_path": destination.name,
            "image_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        }))
    with ParallelUndistortionProcessor(tiff_views, snapshots, tmp_path / "analysis-tiff", maximum_workers=2) as processor:
        assert not processor.reader._gpu_initialized
        processor.prefetch(Path(view.absolute_path) for view in tiff_views)
        for view in tiff_views:
            assert processor(Path(view.absolute_path)) == (160, 120)
        assert all(worker.reader._gpu_initialized for worker in processor._workers)
        assert processor.backend_counts["gpu"] + processor.backend_counts["cpu"] == 4


def test_parallel_missing_input_propagates_and_releases_workers(tmp_path):
    views, snapshots = _fixture(tmp_path, 4)
    Path(views[0].absolute_path).unlink()
    with ParallelUndistortionProcessor(views, snapshots, tmp_path / "analysis-invalid", maximum_workers=2) as processor:
        processor.prefetch(Path(view.absolute_path) for view in views)
        with pytest.raises(FileNotFoundError):
            processor(Path(views[0].absolute_path))
    assert all(loop.done() for loop in processor._loops)


def test_live_progress_preserves_and_emits_automatic_worker_counts(tmp_path):
    service, state = _service(tmp_path)
    events = []
    service.progress_callback = events.append
    counts = {"workers": 16, "remap_gpu": 32, "remap_cpu": 0, "cpu": 32}
    try:
        service._set_state(state["run"], stage="undistorting_images", image_probe_backends=counts)
        service._set_state(state["run"], current_frame=32, total_frames=100)
        assert service.get_progress("analysis-test").image_probe_backends == counts
        assert events[-1].image_probe_backends == counts
        assert state["loads"] == 0
    finally:
        service._runner.close()
