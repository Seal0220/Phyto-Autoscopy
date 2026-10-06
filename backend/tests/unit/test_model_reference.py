from __future__ import annotations

import json
from pathlib import Path
from threading import Event

import cv2
import numpy as np
import pytest
from pydantic import ValidationError

from app.analysis.pose_alignment.model_reference import (
    align_model_camera_poses, fit_motor_orbit, metric_model_registration, model_camera_pose,
    reference_space_fixed_poses,
)
from app.analysis.pose_alignment.model_review import model_review_reference, model_review_objects, prepare_reference_point_preview
from app.analysis.reconstruction.dataset_adapter import prepare_round_dataset
from app.models.analysis_models import AnalysisView, MarkerlessPoseSettings, ModelPoseReviewRequest
from test_analysis_checkpoint_resume import _service


def _look_at(center, target=(0, 0, .15)):
    center = np.asarray(center, dtype=float)
    direction = np.asarray(target) - center
    direction /= np.linalg.norm(direction)
    right = np.cross(direction, [0., 0., 1.])
    if np.linalg.norm(right) < 1e-8:
        right = np.array([1., 0., 0.])
    right /= np.linalg.norm(right)
    pose = np.eye(4)
    pose[:3, :3] = [right, np.cross(direction, right), direction]
    pose[:3, 3] = -pose[:3, :3] @ center
    return pose


def _reference():
    views = []
    for index, angle in enumerate(range(0, 360, 30)):
        theta = np.deg2rad(angle)
        pose = _look_at([.6 * np.cos(theta), .6 * np.sin(theta), .2])
        views.append({"camera_id": "rotating", "view_id": f"r-{index}", "angle_deg": angle, "pose": pose.tolist()})
    return {"signature": "reference-v1", "views": views, "orbit": fit_motor_orbit(views)}


def _rig():
    return {"top": _look_at([0., 0., 1.]), "side": _look_at([.6, 0., .2])}


def _project(points, pose, matrix):
    camera = points @ pose[:3, :3].T + pose[:3, 3]
    pixels = camera @ matrix.T
    return pixels[:, :2] / pixels[:, 2:]


def test_four_known_model_points_recover_camera_pose():
    points = np.array([[-.1, -.12, .1], [.09, -.1, .12], [-.08, .11, .2], [.12, .08, .04]])
    matrix = np.array([[800., 0, 640], [0, 800, 480], [0, 0, 1]])
    for expected in _rig().values():
        recovered, diagnostics = model_camera_pose(points, _project(points, expected, matrix), matrix, .5)
        assert np.allclose(recovered, expected, atol=1e-6)
        assert diagnostics["inlier_indices"] == [0, 1, 2, 3]
        assert diagnostics["rmse_px"] < 1e-5


def test_model_pnp_rejects_collinear_and_mismatched_positions():
    matrix = np.array([[800., 0, 640], [0, 800, 480], [0, 0, 1]])
    with pytest.raises(ValueError, match="同一直線"):
        model_camera_pose([[0, 0, i] for i in range(4)], [[10, i] for i in range(4)], matrix, 1)
    rng = np.random.default_rng(12)
    points = rng.uniform(-.1, .1, (10, 3))
    pixels = _project(points, _rig()["side"], matrix)
    with pytest.raises(ValueError, match="幾何檢查"):
        model_camera_pose(points, pixels[::-1], matrix, .1)


def test_metric_registration_preserves_model_projection_and_baseline():
    reference = _reference()
    registered = metric_model_registration(reference, _rig(), MarkerlessPoseSettings(baseline_mm=1000, top_height_mm=1000).model_dump())
    transform = registered["quality"]["model_to_world"]
    rotation = np.asarray(transform["rotation"])
    shift = np.asarray(transform["translation"])
    scale = transform["scale"]
    points = np.random.default_rng(3).uniform(-.1, .1, (8, 3))
    transformed_points = scale * points @ rotation.T + shift
    centers = {}
    for camera, old_pose in _rig().items():
        new_pose = np.asarray(registered["poses"][camera])
        centers[camera] = np.linalg.inv(new_pose)[:3, 3]
        assert np.allclose(_project(points, old_pose, np.eye(3)), _project(transformed_points, new_pose, np.eye(3)), atol=1e-7)
        np.testing.assert_allclose(reference_space_fixed_poses(registered)[camera], old_pose, atol=1e-12)
    assert np.linalg.norm(centers["top"] - centers["side"]) == pytest.approx(1000)
    assert centers["top"][2] == pytest.approx(1000)
    assert registered["orbit"]["coordinate_unit"] == "millimetre"
    assert reference["orbit"]["coordinate_unit"] == "relative"
    assert np.allclose(rotation.T @ rotation, np.eye(3))
    assert np.linalg.det(rotation) == pytest.approx(1)


def test_axis_fit_rejects_non_motor_motion_and_insufficient_angles():
    reference = _reference()
    assert reference["orbit"]["radius"] == pytest.approx(.6)
    assert reference["orbit"]["rotation_rmse_deg"] < 1e-5
    with pytest.raises(ValueError, match="六個"):
        fit_motor_orbit(reference["views"][:4])
    for view in reference["views"]:
        view["angle_deg"] = 0
    with pytest.raises(ValueError, match="角度分布不足"):
        fit_motor_orbit(reference["views"])


def test_model_orbit_gives_next_round_metric_rotating_poses_without_stereo_matching():
    reference = _reference()
    registration = metric_model_registration(reference, _rig(), MarkerlessPoseSettings(baseline_mm=1000, top_height_mm=1000).model_dump())
    frames = [{"view_id": camera, "camera_id": camera, "relative_path": camera, "capture_id": index, "angle_deg": 45}
              for index, camera in enumerate(("top", "side", "rotating"), 1)]
    result = align_model_camera_poses(frames, registration, required_camera_ids=["top", "side", "rotating"])
    rotating = result.camera_poses[-1]
    center = np.asarray(rotating.camera_to_world_matrix)[:3, 3]
    orbit = registration["orbit"]
    assert np.linalg.norm(center - np.asarray(orbit["center"])) == pytest.approx(orbit["radius"])
    assert rotating.source == "motor_prior"
    assert result.quality.status == "success"
    assert result.pose_estimation_version == "rotating_model_reference_v2"


def test_model_review_requires_four_distinct_known_reference_ids():
    body = {"top_view_id": "top", "side_view_id": "side", "reference_signature": "v1",
            "correspondences": [{"model_point_id": i, "top": {"x_px": i, "y_px": 10}, "side": {"x_px": i, "y_px": 12}} for i in range(4)]}
    assert len(ModelPoseReviewRequest.model_validate(body).correspondences) == 4
    with pytest.raises(ValidationError):
        ModelPoseReviewRequest.model_validate({**body, "correspondences": body["correspondences"][:3]})
    body["correspondences"][-1]["model_point_id"] = 0
    with pytest.raises(ValidationError, match="不同的模型參照點"):
        ModelPoseReviewRequest.model_validate(body)


def _reference_service_fixture(tmp_path):
    service, state = _service(tmp_path)
    reference = _reference()
    reference["quality"] = {"feature_backend": "cuda", "point_count": 30}
    reference["points"] = [{"id": i + 100, "xyz": xyz, "rgb": [0, 255, 0]}
                           for i, xyz in enumerate([[-.1, -.12, .1], [.09, -.1, .12], [-.08, .11, .2], [.12, .08, .04]])]
    views, manifest = [], {}
    for index, item in enumerate(reference["views"] + [{"camera_id": "top", "view_id": "top"}, {"camera_id": "side", "view_id": "side"}]):
        path = tmp_path / (item["view_id"] + ".tiff")
        path.write_bytes(b"fixture")
        view = AnalysisView(analysis_id="analysis-test", round_key="record:mode:round.01", view_id=item["view_id"],
            capture_id=index + 1, camera_id=item["camera_id"], relative_path=path.name, absolute_path=str(path),
            timestamp="2026-10-05T00:00:00+00:00",
            image_width=1280, image_height=960, image_sha256="fixture", snapshot_id="snapshot", angle_deg=item.get("angle_deg"))
        views.append(view)
        manifest[view.view_id] = {"undistorted_path": path.name, "valid_pixel_mask_path": path.name}
    state["run"] = state["run"].model_copy(update={"method_name": "rotating", "parameters": {
        "pose_strategy": MarkerlessPoseSettings(baseline_mm=1000, top_height_mm=1000).model_dump(), "reconstruction": {"training_iterations": 10}},
        "intrinsics_snapshot": {}})
    service._write_processing_preview = lambda *args, **kwargs: None
    return service, state, reference, views, manifest


def _reference_model_result(job, output):
    output.mkdir(parents=True, exist_ok=True)
    points = [{"id": i, "xyz": xyz, "rgb": [60, 220, 80]}
              for i, xyz in enumerate([[-.1, -.12, .1], [.09, -.1, .12], [-.08, .11, .2], [.12, .08, .04]])]
    preview = prepare_reference_point_preview({"points": points}, output)
    return {"gaussian_model_path": preview["gaussian_model_path"], "preview_paths": [], "model_quality": {
        "coordinate_unit": "relative",
        "training_camera_counts": {camera: sum(view["camera_id"] == camera for view in job["selected_views"])
                                   for camera in ("top", "side", "rotating")},
    }}


def test_reference_joint_training_adds_both_fixed_cameras_and_reuses_completed_model(tmp_path, monkeypatch):
    from app.services import analysis_service
    service, state, reference, views, manifest = _reference_service_fixture(tmp_path)
    calls = []

    def worker(job, output, event, **kwargs):
        calls.append(job.get("reference_action") or "3dgs")
        if job.get("reference_action") == "rotating":
            # Merge image metadata into the model's registered poses.
            reference["views"] = [{**payload, **pose} for payload, pose in zip(job["selected_views"], reference["views"])]
            reference["sparse_path"] = str(tmp_path / "sparse")
            return reference
        if job.get("reference_action") == "register_fixed":
            assert calls == ["rotating", "register_fixed"]
            return {"views": [{"camera_id": camera, "pose": pose.tolist()} for camera, pose in _rig().items()]}
        assert output.name == "model"
        assert {v["camera_id"] for v in job["selected_views"]} == {"top", "side", "rotating"}
        for view in job["selected_views"]:
            if view["camera_id"] in {"top", "side"}:
                np.testing.assert_allclose(view["pose"], _rig()[view["camera_id"]], atol=1e-12)
                assert view["pose_source"] == "model_reference"
        assert job["world_coordinate_unit"] == "relative"
        assert job["initial_sparse_path"] == reference["sparse_path"]
        return _reference_model_result(job, output)

    monkeypatch.setattr(analysis_service, "run_reconstruction_worker", worker)
    service._write_processing_preview = lambda *args, **kwargs: None
    try:
        first = service._prepare_model_reference(state["run"], views, manifest, Event())
        second = service._prepare_model_reference(state["run"], views, manifest, Event())
        assert calls == ["rotating", "register_fixed", "3dgs"]
        assert first["quality"] == second["quality"]
        assert first["quality"]["scale_source"] == "model_reference_and_measured_stereo_baseline"
        context = json.loads((tmp_path / "pose_debug/model_reference/context.json").read_text(encoding="utf-8"))
        assert context["training_camera_counts"] == {"top": 1, "side": 1, "rotating": 12}
        assert "bootstrap_model" not in context
        assert Path(context["model"]["gaussian_model_path"]).parent.name == "model"
    finally:
        service._runner.close()


def test_accepted_manual_reference_survives_joint_training_pause_and_publication(tmp_path, monkeypatch):
    from app.services import analysis_service
    from app.analysis.checkpoints import StepJournal
    from app.core.exceptions import AnalysisPausedError, AnalysisReviewRequiredError
    service, state, reference, views, manifest = _reference_service_fixture(tmp_path)
    calls = []
    pauses = [True]

    def worker(job, output, event, **kwargs):
        calls.append(job.get("reference_action") or output.name)
        if job.get("reference_action") == "rotating":
            reference["views"] = [{**payload, **pose} for payload, pose in zip(job["selected_views"], reference["views"])]
            reference["sparse_path"] = str(tmp_path / "sparse")
            return reference
        if job.get("reference_action") == "register_fixed":
            raise ValueError("manual alignment required")
        if output.name == "model":
            for view in job["selected_views"]:
                if view["camera_id"] in {"top", "side"}:
                    np.testing.assert_allclose(view["pose"], _rig()[view["camera_id"]], atol=1e-12)
            if pauses and pauses.pop():
                raise AnalysisPausedError("pause joint training")
        return _reference_model_result(job, output)

    monkeypatch.setattr(analysis_service, "run_reconstruction_worker", worker)
    try:
        with pytest.raises(AnalysisReviewRequiredError):
            service._prepare_model_reference(state["run"], views, manifest, Event())
        assert calls == ["rotating", "register_fixed", "alignment_preview"]
        context_path = tmp_path / "pose_debug/model_reference/context.json"
        original = context_path.read_bytes()
        assert json.loads(original)["model"]["model_quality"]["representation"] == "alignment_3dgs"
        registration = metric_model_registration(reference, _rig(), state["run"].parameters["pose_strategy"])
        registration["quality"]["estimation_source"] = "manual_model_reference"
        # Exercise legacy saved registrations that depended on the old PLY context.
        signature = service._stereo_pose_signature(state["run"])
        service._save_step(state["run"], "aligning_model_cameras", "registration", signature, registration,
                           outputs=[context_path])
        with pytest.raises(AnalysisPausedError):
            service._prepare_model_reference(state["run"], views, manifest, Event())
        assert context_path.read_bytes() == original
        with StepJournal(tmp_path) as journal:
            assert journal.get("aligning_model_cameras", "registration", signature) is not None
        result = service._prepare_model_reference(state["run"], views, manifest, Event())
        assert result["quality"]["estimation_source"] == "manual_model_reference"
        published = context_path.read_bytes()
        assert published != original
        with StepJournal(tmp_path) as journal:
            assert journal.get("aligning_model_cameras", "registration", signature) is not None
        service._prepare_model_reference(state["run"], views, manifest, Event())
        assert context_path.read_bytes() == published
        assert calls == ["rotating", "register_fixed", "alignment_preview", "model", "model"]
        assert json.loads(published)["alignment_preview"]["model_quality"]["representation"] == "alignment_3dgs"
    finally:
        service._runner.close()


@pytest.mark.parametrize("problem", ["missing_top", "invalid_geometry"])
def test_unresolved_fixed_camera_builds_dense_preview_without_starting_final_3dgs(tmp_path, monkeypatch, problem):
    from app.services import analysis_service
    from app.core.exceptions import AnalysisReviewRequiredError
    service, state, reference, views, manifest = _reference_service_fixture(tmp_path)
    calls = []

    def worker(job, output, event, **kwargs):
        action = job.get("reference_action")
        calls.append(action or output.name)
        if action is None:
            assert output.name == "alignment_preview", "Final 3DGS must wait for camera alignment"
            assert job["purpose"] == "camera_alignment_preview"
            assert all(view.get("pose") is not None for view in job["selected_views"])
            return _reference_model_result(job, output)
        if action == "rotating":
            reference["views"] = [{**payload, **pose} for payload, pose in zip(job["selected_views"], reference["views"])]
            reference["sparse_path"] = str(tmp_path / "sparse")
            if problem == "invalid_geometry":
                reference["views"].extend({**view, "pose": _rig()["side"].tolist()}
                                          for view in job["selected_views"] if view["camera_id"] in {"top", "side"})
            return reference
        if problem == "invalid_geometry":
            return {"views": reference["views"]}
        return {"views": [{"camera_id": "side", "pose": _rig()["side"].tolist()}]}

    monkeypatch.setattr(analysis_service, "run_reconstruction_worker", worker)
    try:
        with pytest.raises(AnalysisReviewRequiredError, match="俯視|尺度"):
            service._prepare_model_reference(state["run"], views, manifest, Event())
        assert calls == ["rotating", "register_fixed", "alignment_preview"]
        context = json.loads((tmp_path / "pose_debug/model_reference/context.json").read_text(encoding="utf-8"))
        assert context["model"]["status"] == "awaiting_camera_alignment"
        assert context["training_camera_counts"]["rotating"] == 12
        assert not (tmp_path / "pose_debug/model_reference/model").exists()
        payload = model_review_reference(context, tmp_path)
        ids = [payload["gaussian_point_offset"] + i for i in range(4)]
        np.testing.assert_allclose(model_review_objects(context, tmp_path, payload, ids),
                                   [p["xyz"] for p in reference["points"]], atol=1e-8)
        assert payload["model_quality"]["representation"] == "alignment_3dgs"
    finally:
        service._runner.close()


def test_alignment_pause_is_not_converted_into_manual_review(tmp_path, monkeypatch):
    from app.services import analysis_service
    from app.core.exceptions import AnalysisPausedError
    service, state, reference, views, manifest = _reference_service_fixture(tmp_path)
    calls = []

    def worker(job, output, event, **kwargs):
        calls.append(job["reference_action"])
        if job["reference_action"] == "register_fixed":
            raise AnalysisPausedError("pause alignment")
        reference["sparse_path"] = str(tmp_path / "sparse")
        return reference

    monkeypatch.setattr(analysis_service, "run_reconstruction_worker", worker)
    try:
        with pytest.raises(AnalysisPausedError):
            service._prepare_model_reference(state["run"], views, manifest, Event())
        assert calls == ["rotating", "register_fixed"]
        assert not (tmp_path / "pose_debug/model_reference/model").exists()
    finally:
        service._runner.close()


def test_legacy_trained_model_and_draft_survive_first_joint_training(tmp_path, monkeypatch):
    from app.services import analysis_service
    service, state, reference, views, manifest = _reference_service_fixture(tmp_path)
    reference["sparse_path"] = str(tmp_path / "sparse")
    reference["views"] = [{**view.model_dump(mode="json"), **pose}
                          for view, pose in zip(views, reference["views"])]
    previous = _reference_model_result({"selected_views": reference["views"]}, tmp_path / "legacy_model")
    original = Path(previous["gaussian_model_path"]).read_bytes()
    path = tmp_path / "pose_debug/model_reference/context.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"reference": reference, "model": previous, "model_signature": "rotating-only",
                                "fixed_view_ids": ["top", "side"]}), encoding="utf-8")
    draft = tmp_path / "pose_debug/stereo/manual_review.json"
    draft.parent.mkdir(parents=True)
    draft.write_bytes(b'{"request": {"model_point_id": 1234}}')
    registration = metric_model_registration(reference, _rig(), state["run"].parameters["pose_strategy"])
    service._store_model_registration(state["run"], registration)
    calls = []

    def worker(job, output, event, **kwargs):
        calls.append(output.name)
        assert job.get("reference_action") is None
        assert {v["camera_id"] for v in job["selected_views"]} == {"top", "side", "rotating"}
        return _reference_model_result(job, output)

    monkeypatch.setattr(analysis_service, "run_reconstruction_worker", worker)
    try:
        service._prepare_model_reference(state["run"], views, manifest, Event())
        service._prepare_model_reference(state["run"], views, manifest, Event())
        assert calls == ["joint_model"]
        context = json.loads(path.read_text(encoding="utf-8"))
        assert context["bootstrap_model"] == previous
        assert Path(previous["gaussian_model_path"]).read_bytes() == original
        assert draft.read_bytes() == b'{"request": {"model_point_id": 1234}}'
    finally:
        service._runner.close()


def test_reference_training_refuses_missing_camera(tmp_path):
    from app.core.exceptions import AnalysisError
    service, state, reference, _, _ = _reference_service_fixture(tmp_path)
    try:
        with pytest.raises(AnalysisError, match="初始 3DGS"):
            service._reference_model_job(state["run"], reference, reference["views"])
    finally:
        service._runner.close()


def test_dense_alignment_preview_upgrades_sparse_review_without_replacing_its_source_or_draft(tmp_path, monkeypatch):
    from app.services import analysis_service
    from app.core.exceptions import AnalysisReviewRequiredError
    service, state, reference, views, manifest = _reference_service_fixture(tmp_path)
    reference["sparse_path"] = str(tmp_path / "sparse")
    reference["views"] = [{**view.model_dump(mode="json"), **pose}
                          for view, pose in zip(views, reference["views"])]
    root = tmp_path / "pose_debug/model_reference"
    context = {"reference": reference, "model": prepare_reference_point_preview(reference, root),
               "fixed_view_ids": ["top", "side"]}
    path = root / "context.json"
    path.write_text(json.dumps(context), encoding="utf-8")
    original_signature = model_review_reference(context, tmp_path)["signature"]
    original_points = Path(context["model"]["gaussian_model_path"]).read_bytes()
    draft = tmp_path / "pose_debug/stereo/manual_review.json"
    draft.parent.mkdir(parents=True)
    draft.write_bytes(b'{"request": {"model_point_id": 107}}')
    calls = []

    def worker(job, output, event, **kwargs):
        calls.append(job.get("reference_action") or output.name)
        if job.get("reference_action") == "rotating":
            return reference
        if job.get("reference_action") == "register_fixed":
            raise ValueError("manual alignment required")
        assert job["purpose"] == "camera_alignment_preview"
        assert job["parameters"]["training_iterations"] == state["run"].parameters["reconstruction"]["training_iterations"]
        return _reference_model_result(job, output)

    monkeypatch.setattr(analysis_service, "run_reconstruction_worker", worker)
    try:
        for _ in range(2):
            with pytest.raises(AnalysisReviewRequiredError):
                service._prepare_model_reference(state["run"], views, manifest, Event())
        updated = json.loads(path.read_text(encoding="utf-8"))
        assert updated["model"]["model_quality"]["representation"] == "alignment_3dgs"
        assert updated["model"]["status"] == "awaiting_camera_alignment"
        assert model_review_reference(updated, tmp_path)["signature"] != original_signature
        assert updated["reference"] == reference
        assert Path(context["model"]["gaussian_model_path"]).read_bytes() == original_points
        assert draft.read_bytes() == b'{"request": {"model_point_id": 107}}'
        assert calls == ["rotating", "register_fixed", "alignment_preview", "rotating", "register_fixed"]
        assert not (root / "model").exists()
    finally:
        service._runner.close()


def test_dense_alignment_preview_pause_does_not_publish_incomplete_model(tmp_path, monkeypatch):
    from app.services import analysis_service
    from app.core.exceptions import AnalysisPausedError, AnalysisReviewRequiredError
    service, state, reference, views, manifest = _reference_service_fixture(tmp_path)
    reference["sparse_path"] = str(tmp_path / "sparse")
    reference["views"] = [{**view.model_dump(mode="json"), **pose}
                          for view, pose in zip(views, reference["views"])]
    root = tmp_path / "pose_debug/model_reference"
    context = {"reference": reference, "model": prepare_reference_point_preview(reference, root),
               "fixed_view_ids": ["top", "side"]}
    path = root / "context.json"
    path.write_text(json.dumps(context), encoding="utf-8")
    original = path.read_bytes()
    preview_calls = []

    def worker(job, output, event, **kwargs):
        if job.get("reference_action") == "rotating":
            return reference
        if job.get("reference_action") == "register_fixed":
            raise ValueError("manual alignment required")
        preview_calls.append(output.name)
        if len(preview_calls) == 1:
            raise AnalysisPausedError("pause preview")
        return _reference_model_result(job, output)

    monkeypatch.setattr(analysis_service, "run_reconstruction_worker", worker)
    try:
        with pytest.raises(AnalysisPausedError):
            service._prepare_model_reference(state["run"], views, manifest, Event())
        assert path.read_bytes() == original
        with pytest.raises(AnalysisReviewRequiredError):
            service._prepare_model_reference(state["run"], views, manifest, Event())
        assert json.loads(path.read_text(encoding="utf-8"))["model"]["model_quality"]["representation"] == "alignment_3dgs"
        assert preview_calls == ["alignment_preview", "alignment_preview"]
    finally:
        service._runner.close()


@pytest.mark.parametrize("stage,allowed", [("waiting_for_model_review", True), ("waiting_for_stereo_review", False),
                                           ("waiting_for_review", False), ("building_reference_model", False)])
def test_rebuild_preview_requires_explicit_retry_and_still_requires_camera_review(tmp_path, stage, allowed):
    from types import SimpleNamespace
    from app.core.exceptions import AnalysisError
    service, state, _, _, _ = _reference_service_fixture(tmp_path)
    state["run"] = state["run"].model_copy(update={"status": "needs_review", "stage": stage})
    service._runner.close()
    started = []
    service._runner = SimpleNamespace(is_active=lambda _: False, start=lambda analysis_id: started.append(analysis_id) or True)
    if not allowed:
        with pytest.raises(AnalysisError):
            service.retry(state["run"].analysis_id)
        assert started == []
        return
    with pytest.raises(AnalysisError, match="人工"):
        service.resume(state["run"].analysis_id)
    assert started == []
    resumed = service.retry(state["run"].analysis_id)
    assert started == ["analysis-test"]
    assert resumed.status == "processing"
    assert resumed.stage == "estimating_reference_poses"
    assert resumed.manual_review_completed is False


def test_reference_point_preview_preserves_coordinates_and_reuses_identical_file(tmp_path):
    points = [{"id": i, "xyz": [i * .1, i % 2 * .2, i * .03], "rgb": [5, 10, 15]} for i in range(4)]
    reference = {**_reference(), "points": points}
    model = prepare_reference_point_preview(reference, tmp_path)
    path = Path(model["gaussian_model_path"])
    modified = path.stat().st_mtime_ns
    assert prepare_reference_point_preview(reference, tmp_path) == model
    assert path.stat().st_mtime_ns == modified
    payload = model_review_reference({"reference": reference, "model": model}, tmp_path)
    ids = [payload["gaussian_point_offset"] + i for i in range(4)]
    np.testing.assert_allclose(model_review_objects({"reference": reference, "model": model}, tmp_path, payload, ids),
                               [p["xyz"] for p in points], atol=1e-8)
    with pytest.raises(ValueError, match="有效三維"):
        prepare_reference_point_preview({"points": [{"xyz": [float("nan"), 0, 0]}] * 4}, tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()


def test_old_rotating_stereo_review_migrates_to_paused_model_bootstrap_without_starting(tmp_path):
    service, state = _service(tmp_path, "needs_review")
    state["run"] = state["run"].model_copy(update={"method_name": "rotating", "stage": "waiting_for_stereo_review"})
    service.repository.list = lambda: [state["run"]]
    try:
        service.recover_interrupted_runs()
        assert (state["run"].status, state["run"].stage) == ("paused", "estimating_reference_poses")
        assert not service._runner.is_active("analysis-test")
    finally:
        service._runner.close()


@pytest.mark.parametrize("stale", [True, False])
def test_stale_reference_training_pauses_for_user_rebuild_without_starting(tmp_path, stale):
    from app.analysis.reconstruction.gsplat_trainer import PLANT_TRAINING_VERSION
    service, state = _service(tmp_path, "needs_review")
    state["run"] = state["run"].model_copy(update={"method_name": "rotating", "stage": "waiting_for_model_review"})
    service.repository.list = lambda: [state["run"]]
    context_path = tmp_path / "pose_debug/model_reference/context.json"
    context_path.parent.mkdir(parents=True)
    version = "plant_silhouette_v1" if stale else PLANT_TRAINING_VERSION
    text = json.dumps({"model": {"model_quality": {"training_version": version}}})
    context_path.write_text(text, encoding="utf-8")
    try:
        service.recover_interrupted_runs()
        assert state["run"].status == ("paused" if stale else "needs_review")
        assert not service._runner.is_active("analysis-test")
        assert context_path.read_text(encoding="utf-8") == text
    finally:
        service._runner.close()


def _manual_model_service(tmp_path, monkeypatch):
    from test_stereo_manual_review import _review_service
    service, state, _, starts = _review_service(tmp_path, monkeypatch)
    reference = _reference()
    objects = np.array([[-.1, -.12, .1], [.09, -.1, .12], [-.08, .11, .2], [.12, .08, .04]])
    reference["points"] = [{"id": i, "xyz": point.tolist(), "rgb": [0, 255, 0]} for i, point in enumerate(objects)]
    context_path = tmp_path / "pose_debug/model_reference/context.json"
    context_path.parent.mkdir(parents=True)
    context_path.write_text(json.dumps({"reference": reference, "model": {"model_quality": {"coordinate_unit": "relative"}},
                                       "fixed_view_ids": ["view-top", "view-side"]}), encoding="utf-8")
    state["run"] = state["run"].model_copy(update={"method_name": "rotating", "stage": "waiting_for_model_review"})
    matrix = np.array([[800., 0, 640], [0, 800, 480], [0, 0, 1]])
    pixels = {camera: _project(objects, pose, matrix) for camera, pose in _rig().items()}
    request = ModelPoseReviewRequest(top_view_id="view-top", side_view_id="view-side", reference_signature=reference["signature"],
        correspondences=[{"model_point_id": i, "top": dict(x_px=x, y_px=y), "side": dict(x_px=a, y_px=b)}
                         for i, ((x, y), (a, b)) in enumerate(zip(pixels["top"], pixels["side"]))])
    return service, state, request, starts


def test_manual_four_point_model_review_returns_reference_then_saves_metric_rig(tmp_path, monkeypatch):
    from app.analysis.checkpoints import StepJournal
    service, state, request, starts = _manual_model_service(tmp_path, monkeypatch)
    payload = service.get_stereo_review("analysis-test")
    assert payload["minimum_pairs"] == 4
    assert payload["mode"] == "model_reference"
    assert len(payload["reference"]["points"]) == 4
    result = service.submit_stereo_review("analysis-test", request, "reviewer")
    assert result.status == "processing" and starts == ["analysis-test"]
    with StepJournal(tmp_path) as journal:
        saved = journal.get("aligning_model_cameras", "registration", service._stereo_pose_signature(result))
        assert saved["quality"]["estimation_source"] == "manual_model_reference"
        assert saved["orbit"]["coordinate_unit"] == "millimetre"
    record = json.loads((tmp_path / "pose_debug/stereo/manual_review.json").read_text(encoding="utf-8"))
    assert record["accepted"]
    assert record["validation"]["inlier_indices"] == [0, 1, 2, 3]


@pytest.mark.parametrize("failure", ["unknown_point", "changed_reference"])
def test_model_review_refuses_unknown_or_stale_3d_anchors_and_preserves_draft(tmp_path, monkeypatch, failure):
    from app.core.exceptions import AnalysisError
    service, state, request, starts = _manual_model_service(tmp_path, monkeypatch)
    body = request.model_dump()
    if failure == "unknown_point":
        body["correspondences"][0]["model_point_id"] = 100000
    else:
        body["reference_signature"] = "outdated"
    request = ModelPoseReviewRequest.model_validate(body)
    with pytest.raises(AnalysisError, match="參照點|已變更"):
        service.submit_stereo_review("analysis-test", request, "reviewer")
    assert starts == []
    assert state["run"].stage == "waiting_for_model_review"
    record = json.loads((tmp_path / "pose_debug/stereo/manual_review.json").read_text(encoding="utf-8"))
    assert not record["accepted"] and record["request"] == request.model_dump(mode="json")


def test_relative_model_dataset_accepts_rotating_only_without_claiming_millimetres(tmp_path):
    matrix = np.array([[100., 0, 20], [0, 100, 20], [0, 0, 1]])
    views, poses = [], []
    for index in range(3):
        path = tmp_path / f"{index}.tiff"
        cv2.imencode(".tiff", np.full((40, 40, 3), 128, np.uint8))[1].tofile(path)
        views.append({"view_id": str(index), "camera_id": "rotating", "undistorted_path": str(path)})
        pose = np.eye(4)
        pose[0, 3] = index
        poses.append({"view_id": str(index), "valid": True, "pose_source": "sfm", "rotation_matrix": pose[:3, :3].tolist(), "translation_vector_mm": pose[:3, 3].tolist()})
    job = {"analysis_id": "test", "round_key": "round", "world_coordinate_unit": "relative", "artifact_root": str(tmp_path),
           "selected_views": views, "camera_poses": poses, "background": {"generate_plant_mask": False, "use_plant_mask_in_loss": False},
           "intrinsics_snapshot": {"rotating": {"undistorted_camera_matrix": matrix.tolist(), "analysis_image_width": 40, "analysis_image_height": 40}}}
    dataset = prepare_round_dataset(job, tmp_path / "model")
    assert dataset.coordinate_unit == "relative"
    metadata = json.loads(dataset.metadata_path.read_text(encoding="utf-8"))
    assert metadata["world_coordinate_unit"] == "relative"
    assert metadata["world_coordinate_source"] == "rotating_sfm_reference"
    with pytest.raises(ValueError, match="缺少必要視角"):
        prepare_round_dataset({**job, "world_coordinate_unit": "millimetre"}, tmp_path / "metric-model")


def _gaussian_review_model(tmp_path, context):
    names = ["x", "y", "z", "f_dc_0", "f_dc_1", "f_dc_2", "opacity"]
    positions = [p["xyz"] for p in context["reference"]["points"]]
    vertices = np.array([[*xyz, 0, 0, 0, 2] for xyz in positions] + [[99, 99, 99, 0, 0, 0, -80]], dtype="<f4")
    path = tmp_path / "model/gaussians.ply"
    path.parent.mkdir(exist_ok=True)
    header = "ply\nformat binary_little_endian 1.0\nelement vertex 5\n" + "".join(f"property float {name}\n" for name in names) + "end_header\n"
    path.write_bytes(header.encode() + vertices.tobytes())
    context["model"]["gaussian_model_path"] = str(path)
    return path, positions


def test_gaussian_render_points_recover_server_owned_world_coordinates(tmp_path, monkeypatch):
    service, _, request, starts = _manual_model_service(tmp_path, monkeypatch)
    context_path = tmp_path / "pose_debug/model_reference/context.json"
    context = json.loads(context_path.read_text(encoding="utf-8"))
    path, positions = _gaussian_review_model(tmp_path, context)
    context_path.write_text(json.dumps(context), encoding="utf-8")
    payload = service.get_stereo_review("analysis-test")["reference"]
    assert payload["gaussian_path"] == "model/gaussians.ply" and payload["gaussian_count"] == 5
    assert len(payload["points"]) == 4  # No huge JSON duplication of every Gaussian.
    assert np.linalg.norm(payload["center"]) < 1  # Faint distant floaters don't determine framing.
    ids = [payload["gaussian_point_offset"] + i for i in range(4)]
    np.testing.assert_allclose(model_review_objects(context, tmp_path, payload, ids), positions, atol=1e-8)
    for bad in (payload["gaussian_point_offset"] + 4, payload["gaussian_point_offset"] + 5):
        with pytest.raises(ValueError, match="參照點"):
            model_review_objects(context, tmp_path, payload, [bad])
    body = request.model_dump()
    body["reference_signature"] = payload["signature"]
    for pair, point_id in zip(body["correspondences"], ids):
        pair["model_point_id"] = point_id
    result = service.submit_stereo_review("analysis-test", ModelPoseReviewRequest.model_validate(body), "reviewer")
    assert result.status == "processing" and starts == ["analysis-test"]
    original = payload["signature"]
    data = path.read_bytes()
    path.write_bytes(data[:-4] + np.array([-79.], dtype="<f4").tobytes())
    assert model_review_reference(context, tmp_path)["signature"] != original


def test_existing_sparse_draft_is_retained_when_opening_full_gaussian_model(tmp_path, monkeypatch):
    service, _, request, _ = _manual_model_service(tmp_path, monkeypatch)
    context_path = tmp_path / "pose_debug/model_reference/context.json"
    context = json.loads(context_path.read_text(encoding="utf-8"))
    _gaussian_review_model(tmp_path, context)
    context_path.write_text(json.dumps(context), encoding="utf-8")
    saved_path = tmp_path / "pose_debug/stereo/manual_review.json"
    saved_path.parent.mkdir(exist_ok=True)
    saved_path.write_text(json.dumps({"request": request.model_dump(), "validation": {"inlier_indices": [0]}}), encoding="utf-8")
    payload = service.get_stereo_review("analysis-test")
    assert payload["draft"]["correspondences"] == request.model_dump()["correspondences"]
    assert payload["draft"]["reference_signature"] == payload["reference"]["signature"]
    assert payload["validation"]["inlier_indices"] == [0]
    context["model"]["gaussian_model_path"] = str(tmp_path.parent / "outside.ply")
    with pytest.raises(ValueError):
        model_review_reference(context, tmp_path)


def test_discarded_enclosure_sfm_points_do_not_shrink_preview_subject(tmp_path, monkeypatch):
    service, _, _, _ = _manual_model_service(tmp_path, monkeypatch)
    context = json.loads((tmp_path / "pose_debug/model_reference/context.json").read_text(encoding="utf-8"))
    _gaussian_review_model(tmp_path, context)
    before = model_review_reference(context, tmp_path)
    context['reference']['points'].extend({'id': 100 + i, 'xyz': [100 + i, 100, 100], 'rgb': [255, 255, 255]} for i in range(20))
    after = model_review_reference(context, tmp_path)
    assert after['radius'] == before['radius']
    assert after['center'] == before['center']
