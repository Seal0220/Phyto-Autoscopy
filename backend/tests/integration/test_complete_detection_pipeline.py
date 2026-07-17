from __future__ import annotations

import os
import time
from math import hypot
from threading import Event

import pytest

from tests.fixtures.analysis_baseline import FRAME_COUNT
from tests.integration.analysis_test_support import (
    assert_raw_unchanged,
    create_analysis_service,
    create_validated_run,
    wait_for_status,
)


def test_complete_classical_detection_pipeline_runs_in_background(
    tmp_path,
    monkeypatch,
) -> None:
    service, dataset = create_analysis_service(tmp_path, monkeypatch)
    try:
        run = create_validated_run(service, manual_review_required=True)
        started_at = time.monotonic()
        started = service.start(run.analysis_id)
        elapsed = time.monotonic() - started_at

        assert started.status == "processing"
        assert elapsed < 0.5
        finished = wait_for_status(
            service,
            run.analysis_id,
            {"needs_review", "failed"},
        )
        assert finished.status == "needs_review", finished.last_error
        assert finished.stage == "waiting_for_review"
        assert finished.current_frame == FRAME_COUNT

        top = service.repository.list_detections(run.analysis_id, "top")
        side = service.repository.list_detections(run.analysis_id, "side")
        assert len(top) == FRAME_COUNT
        assert len(side) == FRAME_COUNT
        assert all(
            item.automatic_detection is not None
            for item in top + side
        )
        assert any(
            item.automatic_detection.valid
            for item in top
            if item.automatic_detection is not None
        )
        assert any(
            item.automatic_detection.minimum_path
            for item in side
            if item.automatic_detection is not None
        )
        labels = {
            (item["frame_id"], item["camera_id"]): item
            for item in dataset["manifest"]["manual_tip_labels"]
        }
        for stored in top + side:
            label = labels.get((stored.frame_id, stored.camera_id))
            if label is None:
                continue
            detected = stored.automatic_detection
            assert detected is not None
            assert detected.valid is True
            assert detected.selected_point is not None
            assert hypot(
                detected.selected_point.x_px - label["x_px"],
                detected.selected_point.y_px - label["y_px"],
            ) <= 6.0

        output = service.settings.paths.analysis_dir / run.record_id / run.analysis_id
        assert len(list((output / "overlays" / "top").glob("*.jpg"))) == FRAME_COUNT
        assert len(list((output / "overlays" / "side").glob("*.jpg"))) == FRAME_COUNT
        assert (output / "top_detections.csv").is_file()
        assert (output / "detections" / "side_automatic.csv").is_file()
        assert_raw_unchanged(dataset)
    finally:
        service.close()
        dataset["database"].close()


def test_cancel_is_cooperative_not_reported_as_error_and_can_reset(
    tmp_path,
    monkeypatch,
) -> None:
    service, dataset = create_analysis_service(tmp_path, monkeypatch)
    worker_started = Event()
    reported_errors = []
    service.error_reporter = reported_errors.append

    def blocking_detection(_run, cancel_event):
        worker_started.set()
        while not cancel_event.wait(0.01):
            pass
        service._check_cancel(cancel_event)

    service._run_detection = blocking_detection
    try:
        run = create_validated_run(service, manual_review_required=True)
        service.start(run.analysis_id)
        assert worker_started.wait(2.0)
        service.cancel(run.analysis_id)
        cancelled = wait_for_status(service, run.analysis_id, {"cancelled", "failed"})
        assert cancelled.status == "cancelled"
        assert reported_errors == []
        deadline = time.monotonic() + 2.0
        while service._runner.is_active(run.analysis_id) and time.monotonic() < deadline:
            time.sleep(0.01)

        reset = service.reset(run.analysis_id)
        assert reset.status == "draft"
        assert reset.current_frame == 0
        assert reset.total_frames == 0
        assert reset.last_error is None
        assert service.list_frame_pairs(run.analysis_id) == []
        assert_raw_unchanged(dataset)
    finally:
        service.close()
        dataset["database"].close()


def test_worker_failure_is_reported_once_and_retry_clears_error(
    tmp_path,
    monkeypatch,
) -> None:
    service, dataset = create_analysis_service(tmp_path, monkeypatch)
    reported_errors = []
    service.error_reporter = reported_errors.append
    try:
        run = create_validated_run(service, manual_review_required=True)
        path = next(dataset["record_path"].rglob("*.png"))
        original = path.read_bytes()
        original_stat = path.stat()
        damaged = bytearray(original)
        damaged[-20] ^= 1
        path.write_bytes(damaged)
        os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

        service.start(run.analysis_id)
        failed = wait_for_status(service, run.analysis_id, {"failed"})
        assert "SHA-256" in failed.last_error
        assert len(reported_errors) == 1
        assert "分析" in reported_errors[0]

        path.write_bytes(original)
        os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        service.retry(run.analysis_id)
        retried = wait_for_status(
            service,
            run.analysis_id,
            {"needs_review", "failed"},
        )
        assert retried.status == "needs_review", retried.last_error
        assert retried.last_error is None
        assert len(reported_errors) == 1
        assert_raw_unchanged(dataset)
    finally:
        if "original" in locals() and path.read_bytes() != original:
            path.write_bytes(original)
        service.close()
        dataset["database"].close()


@pytest.mark.parametrize(
    ("interrupted_status", "stage"),
    [
        ("processing", "detecting_side_tip"),
        ("reconstructing", "triangulating"),
    ],
)
def test_interrupted_analysis_is_recovered_as_failed_and_retryable(
    tmp_path,
    monkeypatch,
    interrupted_status: str,
    stage: str,
) -> None:
    service, dataset = create_analysis_service(tmp_path, monkeypatch)
    try:
        run = create_validated_run(service, manual_review_required=True)
        service.repository.update_state(
            run.analysis_id,
            updated_at=run.updated_at,
            status=interrupted_status,
            stage=stage,
            current_frame=4,
            total_frames=8,
            progress=0.5,
        )

        service.recover_interrupted_runs()

        recovered = service.get_run(run.analysis_id)
        progress = service.get_progress(run.analysis_id)
        assert recovered.status == "failed"
        assert recovered.stage == stage
        assert recovered.current_frame == 4
        assert recovered.total_frames == 8
        assert recovered.progress == 0.5
        assert "非正常中止" in recovered.last_error
        assert progress.status == "failed"
        assert progress.last_error == recovered.last_error

        ready = service.validate(run.analysis_id)
        assert ready.status == "ready"
        assert ready.last_error is None
        assert_raw_unchanged(dataset)
    finally:
        service.close()
        dataset["database"].close()
