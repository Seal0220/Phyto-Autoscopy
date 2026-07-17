from __future__ import annotations

import pytest

from app.core.exceptions import AnalysisError
from app.database.schema import initialize_schema
from app.models.analysis_models import (
    AnalysisCreateRequest,
    ManualCorrection,
    ManualCorrectionRequest,
)
from app.repositories.analysis_repository import AnalysisRepository
from tests.fixtures.analysis_baseline import (
    BASELINE_CALIBRATION_ID,
    BASELINE_RECORD_ID,
)
from tests.integration.analysis_test_support import (
    analysis_parameters,
    assert_raw_unchanged,
    create_analysis_service,
    create_validated_run,
    wait_for_status,
)


def test_manual_corrections_are_append_only_and_delete_falls_back(
    tmp_path,
    monkeypatch,
) -> None:
    service, dataset = create_analysis_service(tmp_path, monkeypatch)
    try:
        run = create_validated_run(service, manual_review_required=True)
        service.start(run.analysis_id)
        ready = wait_for_status(service, run.analysis_id, {"needs_review", "failed"})
        assert ready.status == "needs_review", ready.last_error

        before = service.repository.get_detection(run.analysis_id, 3, "top")
        assert before is not None
        automatic = before.automatic_detection.model_copy(deep=True)
        first = service.save_correction(
            run.analysis_id,
            ManualCorrectionRequest(
                frame_id=3,
                camera_id="top",
                corrected_x_px=60.0,
                corrected_y_px=30.0,
                reason="第一筆人工校正",
            ),
            "reviewer-a",
        )
        second = service.save_correction(
            run.analysis_id,
            ManualCorrectionRequest(
                frame_id=3,
                camera_id="top",
                corrected_x_px=61.0,
                corrected_y_px=31.0,
                reason="第二筆人工校正",
            ),
            "reviewer-b",
        )

        history = service.list_corrections(run.analysis_id)
        assert [item.correction_id for item in history] == [
            first.correction_id,
            second.correction_id,
        ]
        latest = service.repository.get_detection(run.analysis_id, 3, "top")
        assert latest.automatic_detection == automatic
        assert latest.resolved_detection.detection_type == "Manual"
        assert latest.resolved_detection.selected_point.x_px == 61.0

        service.delete_correction(run.analysis_id, second.correction_id)
        fallback = service.repository.get_detection(run.analysis_id, 3, "top")
        assert fallback.automatic_detection == automatic
        assert fallback.resolved_detection.detection_type == "Manual"
        assert fallback.resolved_detection.selected_point.x_px == 60.0
        assert len(service.list_corrections(run.analysis_id)) == 1

        service.reconstruct(run.analysis_id, manual_review_completed=True)
        completed = wait_for_status(service, run.analysis_id, {"completed", "failed"})
        assert completed.status == "completed", completed.last_error
        assert completed.manual_review_completed is True
        service.save_correction(
            run.analysis_id,
            ManualCorrectionRequest(
                frame_id=3,
                camera_id="side",
                corrected_x_px=50.0,
                corrected_y_px=30.0,
                reason="重建後再修正",
            ),
            "reviewer-c",
        )
        with pytest.raises(AnalysisError, match="完成後"):
            service.get_trajectory(run.analysis_id)
        assert service.get_run(
            run.analysis_id
        ).average_reprojection_error_px is None
        assert_raw_unchanged(dataset)
    finally:
        service.close()
        dataset["database"].close()


def test_initialize_schema_migrates_legacy_unique_correction_table(
    tmp_path,
    monkeypatch,
) -> None:
    service, dataset = create_analysis_service(tmp_path, monkeypatch)
    database = dataset["database"]
    try:
        run = service.create(
            AnalysisCreateRequest(
                record_id=BASELINE_RECORD_ID,
                calibration_id=BASELINE_CALIBRATION_ID,
                parameters=analysis_parameters(),
            ),
            "pytest-operator",
        )
        service.close()
        with database.transaction() as connection:
            connection.execute("DROP TABLE manual_corrections")
            connection.execute(
                """
                CREATE TABLE manual_corrections (
                    correction_id TEXT PRIMARY KEY,
                    analysis_id TEXT NOT NULL,
                    frame_id INTEGER NOT NULL,
                    camera_id TEXT NOT NULL,
                    automatic_x_px REAL,
                    automatic_y_px REAL,
                    corrected_x_px REAL,
                    corrected_y_px REAL,
                    operator_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    reason TEXT,
                    invalid INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(analysis_id, frame_id, camera_id),
                    FOREIGN KEY(analysis_id) REFERENCES analysis_runs(analysis_id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                INSERT INTO manual_corrections(
                    correction_id, analysis_id, frame_id, camera_id,
                    corrected_x_px, corrected_y_px, operator_id,
                    created_at, invalid
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    "legacy-correction",
                    run.analysis_id,
                    3,
                    "top",
                    60.0,
                    30.0,
                    "legacy-user",
                    "2026-07-17T00:00:00+00:00",
                ),
            )

        initialize_schema(database)
        repository = AnalysisRepository(database)
        assert repository.get_correction(run.analysis_id, "legacy-correction") is not None
        repository.insert_correction(
            ManualCorrection(
                correction_id="new-correction",
                analysis_id=run.analysis_id,
                frame_id=3,
                camera_id="top",
                corrected_x_px=61.0,
                corrected_y_px=31.0,
                operator_id="new-user",
                created_at="2026-07-17T00:00:01+00:00",
            )
        )
        assert len(repository.list_corrections(run.analysis_id)) == 2
    finally:
        service.close()
        database.close()


def test_manual_invalid_is_an_interpolation_barrier_and_delete_is_guarded(
    tmp_path,
    monkeypatch,
) -> None:
    service, dataset = create_analysis_service(tmp_path, monkeypatch)
    try:
        run = create_validated_run(service, manual_review_required=True)
        service.start(run.analysis_id)
        ready = wait_for_status(service, run.analysis_id, {"needs_review", "failed"})
        assert ready.status == "needs_review", ready.last_error

        for frame_id in (4, 5):
            stored = service.repository.get_detection(
                run.analysis_id,
                frame_id,
                "top",
            )
            assert stored is not None
            automatic = stored.automatic_detection.model_copy(
                update={
                    "candidate_points": [],
                    "selected_point": None,
                    "detection_type": "Missing",
                    "valid": False,
                    "status_reason": "no_candidate",
                },
                deep=True,
            )
            service.repository.upsert_detection(
                stored.model_copy(
                    update={
                        "automatic_detection": automatic,
                        "interpolated_detection": None,
                        "resolved_detection": automatic,
                    },
                    deep=True,
                )
            )

        service._interpolate_camera(service.get_run(run.analysis_id), "top")
        before = service.repository.get_detection(run.analysis_id, 4, "top")
        assert before.interpolated_detection is not None

        correction = service.save_correction(
            run.analysis_id,
            ManualCorrectionRequest(
                frame_id=5,
                camera_id="top",
                invalid=True,
                reason="人工確認此影格無效",
            ),
            "reviewer",
        )

        blocked = service.repository.get_detection(run.analysis_id, 4, "top")
        assert blocked.interpolated_detection is None
        invalid = service.repository.get_detection(run.analysis_id, 5, "top")
        assert invalid.resolved_detection.detection_type == "Invalid"

        service.repository.update_state(
            run.analysis_id,
            updated_at=service.get_run(run.analysis_id).updated_at,
            status="processing",
        )
        with pytest.raises(AnalysisError, match="不可刪除"):
            service.delete_correction(run.analysis_id, correction.correction_id)
        assert service.repository.get_correction(
            run.analysis_id,
            correction.correction_id,
        ) is not None
        service.repository.update_state(
            run.analysis_id,
            updated_at=service.get_run(run.analysis_id).updated_at,
            status="reviewing",
        )
        assert_raw_unchanged(dataset)
    finally:
        service.close()
        dataset["database"].close()


def test_correction_file_refresh_failure_keeps_database_view_consistent(
    tmp_path,
    monkeypatch,
) -> None:
    service, dataset = create_analysis_service(tmp_path, monkeypatch)
    reported_errors = []
    service.error_reporter = reported_errors.append
    try:
        run = create_validated_run(service, manual_review_required=True)
        service.start(run.analysis_id)
        ready = wait_for_status(service, run.analysis_id, {"needs_review", "failed"})
        assert ready.status == "needs_review", ready.last_error

        first = service.save_correction(
            run.analysis_id,
            ManualCorrectionRequest(
                frame_id=3,
                camera_id="top",
                corrected_x_px=60.0,
                corrected_y_px=30.0,
                reason="第一筆人工校正",
            ),
            "reviewer-a",
        )

        def fail_export(_run) -> None:
            raise OSError("simulated artifact failure")

        monkeypatch.setattr(service, "_write_detection_exports", fail_export)
        with pytest.raises(AnalysisError, match="衍生檔案刷新失敗"):
            service.save_correction(
                run.analysis_id,
                ManualCorrectionRequest(
                    frame_id=3,
                    camera_id="top",
                    corrected_x_px=61.0,
                    corrected_y_px=31.0,
                    reason="第二筆人工校正",
                ),
                "reviewer-b",
            )

        history = service.list_corrections(run.analysis_id)
        assert len(history) == 2
        second = history[-1]
        detail = service.get_frame_detail(run.analysis_id, 3)
        assert detail.top_detection.resolved_detection.selected_point.x_px == 61.0
        failed_refresh = service.get_run(run.analysis_id)
        assert failed_refresh.status == "reviewing"
        assert "衍生檔案刷新失敗" in failed_refresh.last_error
        assert failed_refresh.average_reprojection_error_px is None

        with pytest.raises(AnalysisError, match="衍生檔案刷新失敗"):
            service.delete_correction(run.analysis_id, second.correction_id)

        history = service.list_corrections(run.analysis_id)
        assert [item.correction_id for item in history] == [first.correction_id]
        detail = service.get_frame_detail(run.analysis_id, 3)
        assert detail.top_detection.resolved_detection.selected_point.x_px == 60.0
        assert len(reported_errors) == 2
        assert_raw_unchanged(dataset)
    finally:
        service.close()
        dataset["database"].close()
