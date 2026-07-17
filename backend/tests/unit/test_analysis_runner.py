from __future__ import annotations

from threading import Event

from app.analysis.analysis_runner import AnalysisJobManager


def test_job_manager_distinguishes_running_and_queued_jobs() -> None:
    first_started = Event()
    second_started = Event()
    release_first = Event()
    release_second = Event()

    def worker(analysis_id: str, _cancel_event: Event) -> None:
        if analysis_id == "first":
            first_started.set()
            assert release_first.wait(timeout=2)
            return
        second_started.set()
        assert release_second.wait(timeout=2)

    manager = AnalysisJobManager(worker, maximum_workers=1)
    try:
        assert manager.start("first") is True
        assert first_started.wait(timeout=1)
        assert manager.start("second") is True

        assert manager.running_analysis_ids() == ("first",)
        assert manager.active_analysis_ids() == ("first", "second")

        release_first.set()
        assert second_started.wait(timeout=1)
        assert manager.running_analysis_ids() == ("second",)
    finally:
        release_first.set()
        release_second.set()
        manager.close()
