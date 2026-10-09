from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from threading import Event, RLock
from typing import Callable


logger = logging.getLogger(__name__)


class AnalysisJobManager:
    """Bounded in-process analysis jobs with cooperative cancellation."""

    def __init__(
        self,
        worker: Callable[[str, Event], None],
        *,
        maximum_workers: int = 1,
    ) -> None:
        if maximum_workers < 1:
            raise ValueError("分析背景工作數量至少為 1。")
        self.worker = worker
        self._executor = ThreadPoolExecutor(
            max_workers=maximum_workers,
            thread_name_prefix="analysis",
        )
        self._lock = RLock()
        self._jobs: dict[str, tuple[Future, Event]] = {}
        self._restart_requests: set[str] = set()
        self._closed = False

    def _run(self, analysis_id: str, cancel_event: Event) -> None:
        try:
            self.worker(analysis_id, cancel_event)
        finally:
            with self._lock:
                current = self._jobs.get(analysis_id)
                if current is not None and current[1] is cancel_event:
                    self._jobs.pop(analysis_id, None)

    def start(self, analysis_id: str) -> bool:
        with self._lock:
            if self._closed:
                raise RuntimeError("分析背景工作已關閉。")
            current = self._jobs.get(analysis_id)
            if current is not None and not current[0].done():
                return False
            cancel_event = Event()
            future = self._executor.submit(
                self._run,
                analysis_id,
                cancel_event,
            )
            self._jobs[analysis_id] = (future, cancel_event)
            # A very small job may finish before the dictionary assignment.
            # Remove that completed entry here so a retry is never blocked by
            # the submit/worker race.
            if future.done():
                current = self._jobs.get(analysis_id)
                if current is not None and current[1] is cancel_event:
                    self._jobs.pop(analysis_id, None)
            return True

    def start_when_idle(self, analysis_id: str) -> bool:
        """Resume after the worker publishing an initialization pause exits."""
        with self._lock:
            if self._closed:
                raise RuntimeError("分析背景工作已關閉。")
            current = self._jobs.get(analysis_id)
            if current is None or current[0].done():
                return self.start(analysis_id)
            if analysis_id not in self._restart_requests:
                self._restart_requests.add(analysis_id)
                future, cancel_event = current
                future.add_done_callback(
                    lambda _: self._restart_when_finished(analysis_id, cancel_event)
                )
            return True

    def _restart_when_finished(self, analysis_id: str, cancel_event: Event) -> None:
        with self._lock:
            if analysis_id not in self._restart_requests:
                return
            self._restart_requests.discard(analysis_id)
            if not self._closed and not cancel_event.is_set():
                self.start(analysis_id)

    def cancel(self, analysis_id: str) -> bool:
        with self._lock:
            self._restart_requests.discard(analysis_id)
            current = self._jobs.get(analysis_id)
            if current is None or current[0].done():
                return False
            current[1].pause_requested = False
            current[1].set()
            return True

    def pause(self, analysis_id: str) -> bool:
        with self._lock:
            self._restart_requests.discard(analysis_id)
            current = self._jobs.get(analysis_id)
            if current is None or current[0].done():
                return False
            current[1].pause_requested = True
            current[1].set()
            return True

    def is_active(self, analysis_id: str) -> bool:
        with self._lock:
            current = self._jobs.get(analysis_id)
            return current is not None and not current[0].done()

    def active_analysis_ids(self) -> tuple[str, ...]:
        """Return queued and running jobs in submission order."""

        with self._lock:
            return tuple(
                analysis_id
                for analysis_id, (future, _) in self._jobs.items()
                if not future.done()
            )

    def running_analysis_ids(self) -> tuple[str, ...]:
        """Return only jobs that currently own a worker thread."""

        with self._lock:
            return tuple(
                analysis_id
                for analysis_id, (future, _) in self._jobs.items()
                if future.running() and not future.done()
            )

    def wait_until_idle(self, analysis_id: str, *, timeout: float = 1.0) -> bool:
        """Wait briefly for a terminal worker to leave the active registry."""

        with self._lock:
            current = self._jobs.get(analysis_id)
            future = current[0] if current is not None else None
        if future is None:
            return True
        try:
            future.result(timeout=timeout)
        except TimeoutError:
            return False
        except Exception:
            # The service worker normally contains its own errors; either way,
            # a completed Future is idle and may be retried.
            pass
        return not self.is_active(analysis_id)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._restart_requests.clear()
            for _, cancel_event in self._jobs.values():
                cancel_event.pause_requested = True
                cancel_event.set()
        self._executor.shutdown(wait=True, cancel_futures=True)
