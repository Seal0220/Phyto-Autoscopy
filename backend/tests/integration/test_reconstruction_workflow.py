from __future__ import annotations

from tests.integration.analysis_test_support import (
    assert_raw_unchanged,
    create_analysis_service,
    create_validated_run,
    wait_for_status,
)


def test_validated_stereo_and_world_calibration_reconstructs_trajectory(
    tmp_path,
    monkeypatch,
) -> None:
    service, dataset = create_analysis_service(tmp_path, monkeypatch)
    try:
        run = create_validated_run(service, manual_review_required=False)
        service.start(run.analysis_id)
        completed = wait_for_status(
            service,
            run.analysis_id,
            {"completed", "failed"},
        )

        assert completed.status == "completed", completed.last_error
        assert completed.manual_review_completed is False
        assert completed.progress == 1.0
        trajectory = service.get_trajectory(run.analysis_id)
        errors = service.get_reprojection_errors(run.analysis_id)
        summary = service.get_detection_summary(run.analysis_id)
        assert len(trajectory) == 6
        assert len(errors) == 6
        assert all(point.valid for point in trajectory)
        assert all(399.9 <= point.z_mm <= 400.1 for point in trajectory)
        expected = {
            item["frame_id"]: item
            for item in dataset["manifest"]["known_world_points"]
        }
        for point in trajectory:
            target = expected[point.frame_id]
            assert abs(point.x_mm - target["x_mm"]) <= 0.1
            assert abs(point.y_mm - target["y_mm"]) <= 3.0
            assert abs(point.z_mm - target["z_mm"]) <= 0.1
        assert summary.reprojection["high_error_count"] == 0
        assert summary.reprojection["overall_mean_px"] < 3.0
        stored = service.get_run(run.analysis_id)
        assert stored.average_reprojection_error_px == (
            summary.reprojection["overall_mean_px"]
        )
        assert_raw_unchanged(dataset)
    finally:
        service.close()
        dataset["database"].close()


def test_reconstruct_without_manual_review_persists_explicit_false(
    tmp_path,
    monkeypatch,
) -> None:
    service, dataset = create_analysis_service(tmp_path, monkeypatch)
    try:
        run = create_validated_run(service, manual_review_required=True)
        service.start(run.analysis_id)
        waiting = wait_for_status(
            service,
            run.analysis_id,
            {"needs_review", "failed"},
        )
        assert waiting.status == "needs_review", waiting.last_error
        assert service._runner.wait_until_idle(run.analysis_id, timeout=1)

        reconstructing = service.reconstruct(
            run.analysis_id,
            manual_review_completed=False,
        )
        assert reconstructing.manual_review_completed is False
        assert service.get_run(run.analysis_id).manual_review_completed is False

        completed = wait_for_status(
            service,
            run.analysis_id,
            {"completed", "failed"},
        )
        assert completed.status == "completed", completed.last_error
        assert completed.manual_review_completed is False
    finally:
        service.close()
        dataset["database"].close()
