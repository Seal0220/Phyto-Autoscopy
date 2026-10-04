from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import RLock
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.analysis.pose_alignment import markerless_pose
from app.analysis.rounds.paths import round_artifact_directory, safe_artifact_name
from app.core.exceptions import AnalysisError
from app.models.analysis_models import AnalysisRun, AnalysisView
from app.services.analysis_service import AnalysisService
from app.api.analysis_routes import router
from app.core.state import get_context
from app.services import analysis_service


def _service():
    service = AnalysisService.__new__(AnalysisService)
    service._preview_lock = RLock()
    service._processing_previews = {}
    return service


def _view(camera_id="top"):
    return AnalysisView(
        analysis_id="analysis-test", round_key="record:mode:round.01",
        view_id=f"view-{camera_id}", capture_id=1, camera_id=camera_id,
        snapshot_id="snapshot.01", timestamp="2026-10-04T00:00:00+00:00",
        relative_path=f"{camera_id}.png", absolute_path=f"{camera_id}.png",
        image_width=64, image_height=64, image_sha256="test",
    )


def _run():
    return AnalysisRun(
        analysis_id="analysis-test", record_id="record", method_name="rotating",
        method_version="1", git_commit="test", parameters={},
        created_at="2026-10-04T00:00:00+00:00", updated_at="2026-10-04T00:00:00+00:00",
        created_by="test", output_path="analysis-test", status="failed",
        stage="estimating_stereo_pose", last_error="test failure",
    )


def test_failed_processing_preview_survives_service_reload(tmp_path):
    service = _service()
    service._artifacts = lambda run: SimpleNamespace(root=tmp_path)
    run = _run()
    service._write_processing_preview(
        run, [_view(), _view("side")],
        diagnostics={"matched_features": 3, "required_inliers": 24},
        artifact_path="pose_debug/stereo/pair_001.jpg",
    )
    reloaded = _service()
    reloaded._artifacts = service._artifacts
    preview = reloaded._progress_for_run(run).processing_preview
    assert preview.round_key == "record:mode:round.01"
    assert [view.camera_id for view in preview.views] == ["top", "side"]
    assert preview.diagnostics["matched_features"] == 3
    assert preview.artifact_path == "pose_debug/stereo/pair_001.jpg"
    assert reloaded._progress_for_run(run).status == "failed"


def test_old_or_corrupt_preview_does_not_break_progress(tmp_path):
    service = _service()
    service._artifacts = lambda run: SimpleNamespace(root=tmp_path)
    assert service._progress_for_run(_run()).processing_preview is None
    (tmp_path / "processing_preview.json").write_text("broken", encoding="utf-8")
    assert service._progress_for_run(_run()).processing_preview is None


def test_undistorted_image_is_readable_before_complete_manifest(tmp_path):
    service = _service()
    run, view = _run(), _view()
    service._require_run = lambda _: run
    service.repository = SimpleNamespace(list_views=lambda _: [view])

    def missing_manifest():
        raise FileNotFoundError()

    service._artifacts = lambda _: SimpleNamespace(root=tmp_path, read_undistortion_manifest=missing_manifest)
    path = (
        round_artifact_directory(tmp_path, view.round_key)
        / "undistortion" / "images" / f"{safe_artifact_name(view.view_id)}.png"
    )
    path.parent.mkdir(parents=True)
    path.write_bytes(b"test")
    assert service.get_view_image_path(run.analysis_id, view.view_id) == path.resolve()
    path.unlink()
    with pytest.raises(AnalysisError, match="找不到指定的分析影像"):
        service.get_view_image_path(run.analysis_id, view.view_id)


def test_insufficient_matches_report_counts_before_geometry(monkeypatch, tmp_path):
    image = np.zeros((64, 64), dtype=np.uint8)
    keypoints = [cv2.KeyPoint(float(10 + i), float(10 + i), 3) for i in range(30)]
    descriptors = np.zeros((30, 32), dtype=np.uint8)
    monkeypatch.setattr(markerless_pose, "_features", lambda *args: (image, keypoints, descriptors))
    monkeypatch.setattr(markerless_pose, "_matches", lambda *args: [cv2.DMatch(i, i, 0) for i in range(3)])
    frames = [
        dict(camera_id=cam, snapshot_id="one", round_key="round.01")
        for cam in ("top", "side")
    ]
    events = []
    with pytest.raises(ValueError, match="共同特徵配對最多 3 組") as error:
        markerless_pose.estimate_fixed_stereo_pose(
            frames, {}, {"feature_count": 4000, "minimum_stereo_inliers": 24},
            debug_directory=tmp_path,
            progress_callback=lambda *args: events.append(dict(args[-1])),
        )
    assert "此階段尚未執行尖端偵測" in str(error.value)
    assert events[-1]["top_features"] == 30
    assert events[-1]["matched_features"] == 3
    assert events[-1]["rejection_reason"] == "共同特徵配對不足"
    assert Path(events[-1]["match_image_path"]).is_file()
    assert len(events) == 2


def test_progress_api_exposes_persisted_processing_images(tmp_path):
    service = _service()
    run = _run()
    service._artifacts = lambda _: SimpleNamespace(root=tmp_path)
    service._require_run = lambda _: run
    service._write_processing_preview(run, [_view(), _view("side")])
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_context] = lambda: SimpleNamespace(analysis_service=service)
    with TestClient(app) as client:
        response = client.get("/api/analysis/analysis-test/progress")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["processing_preview"]["round_key"] == "record:mode:round.01"
    assert [item["view_id"] for item in payload["processing_preview"]["views"]] == ["view-top", "view-side"]


def test_locked_preview_does_not_stop_processing_or_hide_latest_image(monkeypatch, tmp_path, caplog):
    service = _service()
    service._artifacts = lambda _: SimpleNamespace(root=tmp_path)
    run = _run()
    service._write_processing_preview(run, [_view("top")])

    def denied(*args):
        raise PermissionError("preview file is locked")

    monkeypatch.setattr(analysis_service, "write_json_atomic", denied)
    service._write_processing_preview(run, [_view("side")])
    preview = service._progress_for_run(run).processing_preview
    assert preview.views[0].camera_id == "side"
    assert "live preview remains available" in caplog.text
    # The last valid persisted preview is preserved if the application restarts.
    reloaded = _service()
    reloaded._artifacts = service._artifacts
    assert reloaded._progress_for_run(run).processing_preview.views[0].camera_id == "top"


def test_progress_polling_uses_memory_during_concurrent_preview_updates(monkeypatch, tmp_path):
    service = _service()
    service._artifacts = lambda _: SimpleNamespace(root=tmp_path)
    run = _run()
    service._write_processing_preview(run, [_view()])

    def unexpected_read(*args, **kwargs):
        raise AssertionError("Live progress must not reopen the preview JSON")

    monkeypatch.setattr(Path, "read_text", unexpected_read)

    def write_previews():
        for index in range(60):
            service._write_processing_preview(run, [_view()], diagnostics={"index": index})

    def poll_progress():
        for _ in range(200):
            assert service._progress_for_run(run).processing_preview.views[0].view_id == "view-top"

    with ThreadPoolExecutor(max_workers=3) as pool:
        tasks = [pool.submit(write_previews), pool.submit(poll_progress), pool.submit(poll_progress)]
        for task in tasks:
            task.result(timeout=10)
    assert service._progress_for_run(run).processing_preview.diagnostics["index"] == 59


def test_preview_reset_clears_memory_even_when_old_file_is_locked(monkeypatch, tmp_path):
    service = _service()
    service._artifacts = lambda _: SimpleNamespace(root=tmp_path)
    run = _run()
    service._write_processing_preview(run, [_view()])

    def denied(*args, **kwargs):
        raise PermissionError("preview file is locked")

    monkeypatch.setattr(Path, "unlink", denied)
    service._clear_processing_preview(run)
    assert service._progress_for_run(run).processing_preview is None
