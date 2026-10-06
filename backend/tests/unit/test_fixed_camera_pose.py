from __future__ import annotations

from threading import Event
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from app.analysis.checkpoints import StepJournal
from app.analysis.pose_alignment import fixed_camera_pose
from app.core.exceptions import AnalysisPausedError
from app.models.analysis_models import AnalysisRound, AnalysisView, CameraPoseResult


def _rotation(degrees: float) -> np.ndarray:
    return cv2.Rodrigues(np.array([0.0, 0.0, np.deg2rad(degrees)]))[0]


def _pose(index: int, camera: str = "top", **changes) -> CameraPoseResult:
    return CameraPoseResult(
        **{
            "analysis_id": "analysis-test",
            "round_key": "record:mode:round.01",
            "view_id": f"{camera}-{index}",
            "camera_id": camera,
            "rotation_matrix": np.eye(3).tolist(),
            "translation_vector_mm": [0.0, 0.0, 0.0],
            "pose_source": "rig_stereo",
            "valid": True,
            **changes,
        }
    )


@pytest.mark.parametrize("seed", [0, 42, 123])
def test_block_medoid_matches_original_angular_medoid(seed):
    rng = np.random.default_rng(seed)
    rotations = [cv2.Rodrigues(vector)[0] for vector in rng.normal(size=(23, 3))]
    rotations += [rotations[7]] * 9 + [rotations[3]] * 2
    expected = min(
        range(len(rotations)),
        key=lambda index: sum(
            fixed_camera_pose._rotation_distance_deg(rotations[index], other)
            for other in rotations
        ),
    )
    assert fixed_camera_pose._reference_index(rotations) == expected


def test_repeated_measurements_retain_their_medoid_weight_and_first_index():
    rotations = [_rotation(60), _rotation(110)] + [_rotation(0)] * 10
    assert fixed_camera_pose._reference_index(rotations) == 2
    assert fixed_camera_pose._reference_index(rotations[:3]) == 0
    quarter_turn = np.array([[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]])
    assert fixed_camera_pose._reference_index([quarter_turn, np.eye(3)]) == 0
    assert fixed_camera_pose._reference_index([np.eye(3), quarter_turn]) == 0


def test_25761_identical_rotations_skip_pairwise_distance_computation(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Identical fixed-camera rotations must not compute pairs")

    monkeypatch.setattr(fixed_camera_pose, "_rotation_distance_deg", forbidden)
    monkeypatch.setattr(fixed_camera_pose.np, "einsum", forbidden)
    assert fixed_camera_pose._reference_index([_rotation(31.25)] * 25761) == 0


def test_distinct_rotations_use_bounded_blocks(monkeypatch):
    original = np.einsum
    shapes = []

    def record(expression, first, second):
        shapes.append((len(first), len(second)))
        return original(expression, first, second)

    monkeypatch.setattr(fixed_camera_pose.np, "einsum", record)
    rotations = [_rotation(degrees) for degrees in np.linspace(-90, 90, 513)]
    assert fixed_camera_pose._reference_index(rotations) == 256
    assert shapes == [(512, 512), (512, 1), (1, 512), (1, 1)]


def test_medoid_can_pause_between_comparison_blocks():
    checks = []

    def check():
        checks.append(True)
        if len(checks) == 4:
            raise AnalysisPausedError("pause")

    with pytest.raises(AnalysisPausedError):
        fixed_camera_pose._reference_index(
            [_rotation(degrees) for degrees in np.linspace(-90, 90, 513)],
            cancel_check=check,
        )
    assert len(checks) == 4


def test_consistency_keeps_measured_poses_and_detects_mount_movement():
    poses = [
        _pose(0), _pose(1),
        _pose(2, rotation_matrix=_rotation(10).tolist(), translation_vector_mm=[20., 0., 0.]),
        _pose(0, "side", pose_source="interpolated"),
        _pose(0, "rotating"),
        _pose(3, valid=False),
    ]
    original = [pose.model_dump() for pose in poses]
    progress = []
    updated, summary = fixed_camera_pose.evaluate_fixed_camera_pose_consistency(
        poses, progress_callback=lambda index, total: progress.append((index, total)),
    )
    assert summary["top"]["reference_view_id"] == "top-0"
    assert summary["top"]["reference_translation_vector_mm"] == [0., 0., 0.]
    assert summary["top"]["warning_view_ids"] == ["top-2"]
    assert updated[2].fixed_pose_translation_deviation_mm == 20
    assert updated[2].fixed_pose_rotation_deviation_deg == pytest.approx(10)
    assert summary["side"]["status"] == "unavailable"
    assert progress[0] == (0, 4) and progress[-1] == (4, 4)
    for before, after in zip(poses, updated):
        assert before.rotation_matrix == after.rotation_matrix
        assert before.translation_vector_mm == after.translation_vector_mm
    assert [pose.model_dump() for pose in poses] == original
    assert updated[3] is poses[3] and updated[4] is poses[4] and updated[5] is poses[5]


def test_consistency_reports_image_progress_and_pauses_without_mutating_inputs():
    poses = [_pose(index) for index in range(1100)]
    progress = []
    event = Event()

    def report(index, total):
        progress.append((index, total))
        if index == 512:
            event.set()

    def check():
        if event.is_set():
            raise AnalysisPausedError("pause")

    with pytest.raises(AnalysisPausedError):
        fixed_camera_pose.evaluate_fixed_camera_pose_consistency(
            poses, progress_callback=report, cancel_check=check,
        )
    assert progress == [(0, 1100), (256, 1100), (512, 1100)]
    assert all(pose.fixed_pose_rotation_deviation_deg is None for pose in poses)
    updated, summary = fixed_camera_pose.evaluate_fixed_camera_pose_consistency(poses)
    assert len(updated) == 1100 and summary["top"]["status"] == "stable"


@pytest.mark.parametrize("pause_stage", [None, "checking_pose_consistency", "saving_camera_poses"])
def test_saved_rounds_resume_through_consistency_and_pose_export(tmp_path, monkeypatch, pause_stage):
    from app.services import analysis_service
    from test_analysis_checkpoint_resume import _service

    service, state = _service(tmp_path)
    state["run"] = state["run"].model_copy(update={"method_name": "rotating"})
    poses = [_pose(0), _pose(0, "side")]
    views = [AnalysisView(
        analysis_id=pose.analysis_id, round_key=pose.round_key, view_id=pose.view_id,
        capture_id=index, camera_id=pose.camera_id, timestamp="2026-10-07T00:00:00+00:00",
        relative_path=f"{pose.view_id}.png", absolute_path=str(tmp_path / f"{pose.view_id}.png"),
        image_width=100, image_height=100, image_sha256="test",
    ) for index, pose in enumerate(poses)]
    rounds = [AnalysisRound(
        analysis_id="analysis-test", round_key=poses[0].round_key, record_id="record",
        mode_id="mode", round_id="round.01", status="preprocessed",
    )]
    exports = []
    service._artifacts = lambda _: SimpleNamespace(
        root=tmp_path, write_run=lambda _: None,
        write_round_camera_poses=lambda *args: exports.append("round"),
        write_aggregated_pose_results=lambda *args, **kwargs: exports.append("aggregated"),
        write_round_index=lambda *args: None,
    )
    service.repository.list_rounds = lambda _: rounds
    service.repository.list_views = lambda _: views
    service.repository.list_camera_poses = lambda _: []
    service.repository.replace_camera_poses = lambda *args: exports.append("repository")
    service.repository.update_views = lambda *args: None
    service.repository.update_pose_alignment = lambda *args, **kwargs: None
    service._prepare_model_reference = lambda *args: {"poses": {}, "quality": {}}
    monkeypatch.setattr(analysis_service, "undistort_analysis_views", lambda *args, **kwargs: [
        {"view_id": view.view_id} for view in views
    ])

    def forbidden(*args, **kwargs):
        pytest.fail("Finished rounds must resume from checkpoints")

    monkeypatch.setattr(analysis_service, "align_model_camera_poses", forbidden)
    signature = analysis_service.step_signature({
        "rig": service._stereo_pose_signature(state["run"]), "round_pipeline_version": 2,
    })
    with StepJournal(tmp_path) as journal:
        journal.save("estimating_camera_poses", poses[0].round_key, signature, {
            "poses": [pose.model_dump(mode="json") for pose in poses],
            "views": [view.model_dump(mode="json") for view in views],
            "quality": {}, "version": "test", "failed": False,
        })
    event = Event()
    event.pause_requested = True
    updates = []
    original_set_state = service._set_state

    def set_state(run, **changes):
        result = original_set_state(run, **changes)
        updates.append((result.stage, result.current_frame, result.total_frames))
        if changes.get("stage") == pause_stage:
            event.set()
        return result

    service._set_state = set_state
    try:
        if pause_stage is not None:
            with pytest.raises(AnalysisPausedError):
                service._run_round_preprocessing(state["run"], event)
            assert exports == []
        service._run_round_preprocessing(state["run"], Event())
        assert ("checking_pose_consistency", 0, 2) in updates
        assert ("checking_pose_consistency", 2, 2) in updates
        assert ("saving_camera_poses", 1, 1) in updates
        assert exports == ["round", "repository", "aggregated"]
        with StepJournal(tmp_path) as journal:
            assert journal.get("estimating_camera_poses", poses[0].round_key, signature) is not None
    finally:
        service._runner.close()
