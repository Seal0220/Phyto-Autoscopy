from __future__ import annotations

from types import SimpleNamespace

from app.database.connection import Database
from app.database.schema import initialize_schema
from app.models.analysis_models import AnalysisRound, AnalysisRun, AnalysisView
from app.repositories.analysis_repository import AnalysisRepository
from app.services.analysis_service import AnalysisService
from app.analysis.rounds.paths import round_artifact_directory, safe_artifact_name


def _run():
    return AnalysisRun(
        analysis_id="test", method_name="rotating", method_version="1",
        git_commit="test", parameters={"input_manifest": ["x" * 1024] * 2048},
        created_at="2026-10-05T00:00:00+00:00", updated_at="2026-10-05T00:00:00+00:00",
        created_by="test", output_path="test", status="processing", stage="undistorting_images",
    )


def test_round_results_sort_numbers_across_digit_boundaries(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    try:
        initialize_schema(database)
        repository = AnalysisRepository(database)
        repository.create(_run())
        expected_ids = ["round.01", "round.2", "round.10", "round.99", "round.100",
                        "round.299", "round.300", "round.1000"]
        rounds = [
            AnalysisRound(
                analysis_id="test", round_key=f"record:{mode_id}:{round_id}",
                record_id="record", mode_id=mode_id, round_id=round_id,
                status="ready",
            )
            for mode_id in ("mode-b", "mode-a")
            for round_id in reversed(expected_ids)
        ]
        repository.replace_rounds_and_views("test", rounds, [])

        ordered = repository.list_rounds("test")
        assert [(item.mode_id, item.round_id) for item in ordered] == [
            (mode_id, round_id)
            for mode_id in ("mode-a", "mode-b")
            for round_id in expected_ids
        ]
        assert {item.round_key for item in ordered} == {item.round_key for item in rounds}
    finally:
        database.close()


def test_progress_does_not_rewrite_frozen_manifest_and_survives_reload(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    try:
        initialize_schema(database)
        repository = AnalysisRepository(database)
        repository.create(_run())
        # Exercise the same SQLite operations as a real run, rather than a mock.
        database.execute(
            "CREATE TRIGGER forbid_manifest_rewrite BEFORE UPDATE ON analysis_runs "
            "BEGIN SELECT RAISE(ABORT, 'large run row rewritten'); END"
        )
        for index in range(25):
            repository.update_state("test", updated_at="2026-10-05T01:00:00+00:00",
                                    current_frame=index, total_frames=25, progress=index / 25)
        repository.update_state("test", updated_at="2026-10-05T02:00:00+00:00",
                                status="paused", last_error="saved", completed_round_count=3)
        run = repository.get("test")
        assert (run.status, run.current_frame, run.completed_round_count) == ("paused", 24, 3)
        assert run.parameters == _run().parameters
        assert repository.list()[0].status == "paused"
        repository.update_state("test", updated_at="2026-10-05T03:00:00+00:00",
                                status="processing", clear_error=True)
        database.close()
        initialize_schema(database)
        reloaded = AnalysisRepository(database).get("test")
        assert reloaded.status == "processing" and reloaded.last_error is None
        assert reloaded.current_frame == 24 and reloaded.completed_round_count == 3
        database.execute("DROP TRIGGER forbid_manifest_rewrite")
        repository.clear_results("test")
        assert repository.get("test").completed_round_count == 0
        repository.delete("test")
        assert database.fetchone("SELECT * FROM analysis_run_progress") is None
    finally:
        database.close()


def test_current_image_uses_single_view_without_loading_manifests(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    try:
        initialize_schema(database)
        repository = AnalysisRepository(database)
        repository.create(_run())
        # Image reads must still work if parsing the large JSON would fail.
        database.execute("UPDATE analysis_runs SET parameters_json='invalid JSON' WHERE analysis_id='test'")
        view = AnalysisView(
            analysis_id="test", round_key="record:mode:round.01", view_id="view",
            capture_id=1, camera_id="top", timestamp="2026-10-05T00:00:00+00:00",
            relative_path="top.png", absolute_path="top.png",
            image_width=160, image_height=120, image_sha256="test",
        )
        database.execute(
            "INSERT INTO analysis_rounds (analysis_id,round_key,record_id,mode_id,round_id,status) "
            "VALUES (?,?,?,?,?,?)",
            ("test", view.round_key, "record", "mode", "round.01", "ready"),
        )
        database.execute(
            "INSERT INTO analysis_views (analysis_id,round_key,view_id,capture_id,camera_id,timestamp,"
            "relative_path,absolute_path,image_width,image_height,image_sha256) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (view.analysis_id, view.round_key, view.view_id, view.capture_id, view.camera_id,
             view.timestamp, view.relative_path, view.absolute_path, 160, 120, "test"),
        )
        path = round_artifact_directory(tmp_path, view.round_key) / "undistortion" / "images" / f"{safe_artifact_name(view.view_id)}.jpg"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"preview")
        def forbidden(*args):
            raise AssertionError("large manifest loaded for one preview")
        repository.get = forbidden
        repository.list_views = forbidden
        service = AnalysisService.__new__(AnalysisService)
        service.repository = repository
        service._artifacts = lambda _: SimpleNamespace(root=tmp_path, read_undistortion_manifest=forbidden)
        assert service.get_view_image_path("test", "view") == path.resolve()
        assert service.get_artifact_path("test", str(path.relative_to(tmp_path))) == path.resolve()
    finally:
        database.close()
