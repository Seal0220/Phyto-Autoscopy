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


def test_seed_confirmation_queues_one_resume_until_pausing_worker_exits() -> None:
    entered, release, resumed = Event(), Event(), Event()
    calls = []

    def worker(analysis_id, cancel_event):
        calls.append(analysis_id)
        if len(calls) == 1:
            entered.set()
            assert release.wait(2)
        else:
            resumed.set()

    manager = AnalysisJobManager(worker)
    try:
        manager.start("seeded")
        assert entered.wait(1)
        assert manager.start_when_idle("seeded")
        assert manager.start_when_idle("seeded")
        assert calls == ["seeded"]
        release.set()
        assert resumed.wait(1)
        assert calls == ["seeded", "seeded"]
    finally:
        release.set()
        manager.close()


def test_operator_cancel_prevents_a_queued_initialization_resume() -> None:
    entered, release = Event(), Event()
    calls = []

    def worker(analysis_id, cancel_event):
        calls.append(analysis_id)
        entered.set()
        assert release.wait(2)

    manager = AnalysisJobManager(worker)
    try:
        manager.start("seeded")
        assert entered.wait(1)
        manager.start_when_idle("seeded")
        assert manager.cancel("seeded")
        release.set()
        assert manager.wait_until_idle("seeded")
        assert calls == ["seeded"]
    finally:
        release.set()
        manager.close()
