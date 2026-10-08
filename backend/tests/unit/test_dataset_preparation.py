from __future__ import annotations

import json
from threading import Barrier

import cv2
import numpy as np
import pytest

from app.analysis.checkpoints import StepJournal
from app.analysis.reconstruction import dataset_adapter
from app.core.exceptions import AnalysisPausedError


def _job(tmp_path):
    image = np.full((120, 160, 3), (12, 18, 14), np.uint8)
    cv2.ellipse(image, (80, 35), (24, 8), 0, 0, 360, (40, 180, 60), -1)
    cv2.rectangle(image, (60, 80), (100, 110), (5, 6, 5), -1)
    cv2.ellipse(image, (80, 80), (22, 6), 0, 0, 360, (40, 90, 190), 2)
    path, valid = tmp_path / "source.tiff", tmp_path / "valid.png"
    cv2.imencode(".tiff", image)[1].tofile(path)
    cv2.imencode(".png", np.full(image.shape[:2], 255, np.uint8))[1].tofile(valid)
    return {"analysis_id": "test", "round_key": "record:mode:round.01", "artifact_root": str(tmp_path),
            "selected_views": [{"view_id": camera, "camera_id": camera, "undistorted_path": str(path),
                                "valid_mask_path": str(valid)} for camera in ("top", "side", "rotating")],
            "camera_poses": [{"view_id": camera, "valid": True, "pose_source": "rig_stereo",
                              "rotation_matrix": np.eye(3).tolist(), "translation_vector_mm": [0, 0, 100]}
                             for camera in ("top", "side", "rotating")],
            "intrinsics_snapshot": {camera: {"analysis_image_width": 160, "analysis_image_height": 120,
                "undistorted_camera_matrix": [[100, 0, 80], [0, 100, 60], [0, 0, 1]]}
                for camera in ("top", "side", "rotating")}}


def test_parallel_masks_equal_serial_and_resume_without_decoding(tmp_path, monkeypatch):
    job = _job(tmp_path)
    monkeypatch.setattr(dataset_adapter, "automatic_dataset_workers", lambda *args: 8)
    serial = dataset_adapter.prepare_round_dataset(job, tmp_path / "serial", maximum_workers=1)
    original = dataset_adapter.create_plant_mask
    barrier = Barrier(3)

    def overlapping(*args, **kwargs):
        barrier.wait(10)
        return original(*args, **kwargs)

    monkeypatch.setattr(dataset_adapter, "create_plant_mask", overlapping)
    parallel = dataset_adapter.prepare_round_dataset(job, tmp_path / "parallel", maximum_workers=3)
    assert [item.view_id for item in parallel.views] == [item.view_id for item in serial.views]
    for first, second in zip(serial.views, parallel.views):
        assert first.plant_mask_path.read_bytes() == second.plant_mask_path.read_bytes()
        assert first.foreground_mask_path.read_bytes() == second.foreground_mask_path.read_bytes()
    timestamps = [item.foreground_mask_path.stat().st_mtime_ns for item in parallel.views]
    monkeypatch.setattr(dataset_adapter, "_read_image", lambda *args, **kwargs: pytest.fail("Finished masks were decoded again"))
    resumed = dataset_adapter.prepare_round_dataset(job, parallel.root, maximum_workers=3)
    stats = json.loads(resumed.metadata_path.read_text(encoding="utf-8"))["preparation"]
    assert stats["reused_masks"] == 3 and stats["generated_masks"] == 0
    assert [item.foreground_mask_path.stat().st_mtime_ns for item in resumed.views] == timestamps


def test_pause_keeps_each_finished_mask_and_missing_output_is_regenerated(tmp_path, monkeypatch):
    job = _job(tmp_path)
    original = dataset_adapter.create_plant_mask
    calls = 0

    def pause_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise AnalysisPausedError("pause")
        return original(*args, **kwargs)

    monkeypatch.setattr(dataset_adapter, "create_plant_mask", pause_second)
    root = tmp_path / "dataset"
    with pytest.raises(AnalysisPausedError):
        dataset_adapter.prepare_round_dataset(job, root, maximum_workers=1)
    with StepJournal(root) as journal:
        assert journal.get("preparing_model_images", "top") is not None
        assert journal.get("preparing_model_images", "side") is None
    monkeypatch.setattr(dataset_adapter, "create_plant_mask", original)
    resumed = dataset_adapter.prepare_round_dataset(job, root, maximum_workers=1)
    assert json.loads(resumed.metadata_path.read_text())["preparation"]["reused_masks"] == 1
    resumed.views[1].foreground_mask_path.unlink()
    repaired = dataset_adapter.prepare_round_dataset(job, root, maximum_workers=1)
    assert json.loads(repaired.metadata_path.read_text())["preparation"]["reused_masks"] == 2
    valid = cv2.imdecode(np.fromfile(tmp_path / "valid.png", np.uint8), 0)
    valid[:3] = 0
    cv2.imencode(".png", valid)[1].tofile(tmp_path / "valid.png")
    changed = dataset_adapter.prepare_round_dataset(job, root, maximum_workers=1)
    assert json.loads(changed.metadata_path.read_text())["preparation"]["reused_masks"] == 0


def test_worker_count_obeys_image_memory_budget():
    intrinsics = {"top": {"analysis_image_width": 1920, "analysis_image_height": 1080}}
    gib = 1024 ** 3
    assert dataset_adapter.automatic_dataset_workers(intrinsics, cpu_count=16, available_ram=32 * gib) == 8
    assert dataset_adapter.automatic_dataset_workers(intrinsics, cpu_count=2, available_ram=32 * gib) == 2
    assert dataset_adapter.automatic_dataset_workers(intrinsics, cpu_count=16, available_ram=128 * 1024 ** 2) == 1


def test_updated_segmentation_regenerates_saved_masks_and_keeps_sources(tmp_path, monkeypatch):
    job = _job(tmp_path)
    root = tmp_path / "dataset"
    original_source = (tmp_path / "source.tiff").read_bytes()
    current_version = dataset_adapter.MASK_PREPARATION_VERSION
    monkeypatch.setattr(dataset_adapter, "MASK_PREPARATION_VERSION", current_version - 1)
    old = dataset_adapter.prepare_round_dataset(job, root, maximum_workers=1)
    # Simulate an old side-view mask that included the overhead lamp.
    stale = np.full((120, 160), 255, np.uint8)
    cv2.imencode(".png", stale)[1].tofile(old.views[1].foreground_mask_path)
    monkeypatch.setattr(dataset_adapter, "MASK_PREPARATION_VERSION", current_version)
    updated = dataset_adapter.prepare_round_dataset(job, root, maximum_workers=1)
    stats = json.loads(updated.metadata_path.read_text(encoding="utf-8"))["preparation"]
    assert stats["generated_masks"] == 3 and stats["reused_masks"] == 0
    mask = cv2.imdecode(np.fromfile(updated.views[1].foreground_mask_path, np.uint8), 0)
    assert mask[0, 0] == 0 and mask[90, 80] == 255
    assert (tmp_path / "source.tiff").read_bytes() == original_source
