from __future__ import annotations

import cv2
import json
import numpy as np
import pytest

from app.analysis.reconstruction.render_registration import select_render_pose, validate_render_pose


def _observations():
    rng = np.random.default_rng(34)
    xyz = rng.uniform([-1, -1, 4], [1, 1, 6], (48, 3))
    matrix = np.array([[800., 0, 640], [0, 800., 480], [0, 0, 1]])
    pixels = cv2.projectPoints(xyz, np.zeros(3), np.zeros(3), matrix, None)[0].reshape(-1, 2)
    captures = [{"view_id": str(i), "xyz": xyz, "pixels": pixels + rng.normal(0, .1, pixels.shape)} for i in range(3)]
    return captures, matrix


def test_shared_pose_is_checked_on_heldout_images_without_refitting():
    captures, matrix = _observations()
    quality = validate_render_pose(np.eye(4), captures, matrix, [0, 0, 1])
    assert [item["inlier_count"] for item in quality["captures"]] == [48] * 3
    assert max(item["rmse_px"] for item in quality["captures"]) < .3
    captures[-1]["pixels"] += [15., -10.]
    with pytest.raises(ValueError, match="其他擷取"):
        validate_render_pose(np.eye(4), captures, matrix, [0, 0, 1])


@pytest.mark.parametrize("problem", ["duplicate", "below", "inclination", "cluster", "nonfinite"])
def test_invalid_or_weak_top_geometry_is_rejected(problem):
    captures, matrix = _observations()
    pose = np.eye(4)
    if problem == "duplicate":
        captures[-1]["view_id"] = captures[0]["view_id"]
    elif problem == "below":
        pose[:3, :3] = np.diag([1., -1., -1.])
    elif problem == "inclination":
        pose[:3, :3] = cv2.Rodrigues(np.array([np.deg2rad(30), 0., 0.]))[0]
    elif problem == "cluster":
        for item in captures:
            item["xyz"] = item["xyz"].copy()
            item["xyz"][:, :2] *= .005
            item["pixels"] = cv2.projectPoints(item["xyz"], np.zeros(3), np.zeros(3), matrix, None)[0].reshape(-1, 2)
    else:
        captures[0]["pixels"][0, 0] = np.nan
    with pytest.raises(ValueError):
        validate_render_pose(pose, captures, matrix, [0, 0, 1])


def test_opposite_orientation_requires_clear_support_advantage():
    def candidate(angle, support):
        pose = np.eye(4)
        pose[:3, :3] = cv2.Rodrigues(np.array([0., 0., np.deg2rad(angle)]))[0]
        return {"pose": pose.tolist(), "quality": {"captures": [{"inlier_count": support}] * 3}}
    with pytest.raises(ValueError, match="歧義"):
        select_render_pose([candidate(0, 40), candidate(180, 38)])
    best = candidate(0, 60)
    assert select_render_pose([candidate(180, 30), best]) is best


@pytest.mark.parametrize("cancelled", [False, True])
def test_localization_worker_publishes_only_completed_or_cancelled_results(tmp_path, monkeypatch, cancelled):
    from app.analysis.reconstruction import render_registration, worker_process
    job = tmp_path / "job.json"
    job.write_text(json.dumps({"kind": "reference_localization"}), encoding="utf-8")
    cancel = tmp_path / "cancel"
    if cancelled:
        cancel.touch()
    calls = []
    monkeypatch.setattr(worker_process, "configure_native_build", lambda: calls.append("configure"))

    def localize(job, root, *, progress, cancel_check):
        cancel_check()
        progress("aligning_model_cameras", 1, "checked")
        return {"status": "completed", "poses": {"top": np.eye(4).tolist()}}

    monkeypatch.setattr(render_registration, "localize_reference_top", localize)
    result = tmp_path / "result.json"
    code = worker_process.execute_job(job, tmp_path / "output", result, tmp_path / "progress.json", cancel)
    assert code == int(cancelled)
    assert json.loads(result.read_text(encoding="utf-8"))["status"] == ("cancelled" if cancelled else "completed")
    assert calls == ["configure"]


def test_cancelling_render_features_stops_its_child_process(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from app.analysis.reconstruction import render_registration
    stopped = []
    process = SimpleNamespace(poll=lambda: 0 if stopped else None,
                             terminate=lambda: stopped.append("terminate"),
                             wait=lambda **kwargs: stopped.append("wait"))
    monkeypatch.setattr(render_registration.subprocess, "Popen", lambda *args, **kwargs: process)

    def cancelled():
        raise RuntimeError("cancel requested")

    with pytest.raises(RuntimeError, match="cancel requested"):
        render_registration._run_feature_worker(tmp_path, tmp_path / "job.json", cancel_check=cancelled)
    assert stopped == ["terminate", "wait"]
