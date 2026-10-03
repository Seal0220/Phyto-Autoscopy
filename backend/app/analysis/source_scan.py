from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import Event, RLock
from time import monotonic
from typing import Callable
from uuid import uuid4

from app.core.exceptions import AnalysisError, public_error_detail
from app.models.analysis_models import (
    AnalysisSourcePreview,
    AnalysisSourcePreviewRequest,
    AnalysisSourceScanStatus,
)


logger = logging.getLogger(__name__)
_RESULT_TTL_SECONDS = 600
_MAX_PENDING_SCANS = 3


@dataclass(slots=True)
class _ScanJob:
    scan_id: str
    request: AnalysisSourcePreviewRequest
    status: str = "queued"
    processed_frames: int = 0
    total_frames: int = 0
    preview: AnalysisSourcePreview | None = None
    error: str | None = None
    finished_at: float | None = None
    cancelled: Event = field(default_factory=Event)
    future: Future[None] | None = None


class SourceScanManager:
    """Run full, cancellable image validation outside the HTTP request."""

    def __init__(
        self,
        scan: Callable[
            [AnalysisSourcePreviewRequest, Callable[[int, int], None], Callable[[], bool]],
            AnalysisSourcePreview,
        ],
    ) -> None:
        self._scan = scan
        self._lock = RLock()
        self._jobs: dict[str, _ScanJob] = {}
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="analysis-source-scan",
        )

    def _prune(self) -> None:
        deadline = monotonic() - _RESULT_TTL_SECONDS
        for scan_id, job in tuple(self._jobs.items()):
            if job.finished_at is not None and job.finished_at < deadline:
                del self._jobs[scan_id]

    @staticmethod
    def _snapshot(job: _ScanJob) -> AnalysisSourceScanStatus:
        return AnalysisSourceScanStatus(
            scan_id=job.scan_id,
            status=job.status,
            processed_frames=job.processed_frames,
            total_frames=job.total_frames,
            preview=job.preview if job.status == "completed" else None,
            error=job.error,
        )

    def start(self, request: AnalysisSourcePreviewRequest) -> AnalysisSourceScanStatus:
        with self._lock:
            self._prune()
            pending = sum(
                job.status in {"queued", "scanning"}
                for job in self._jobs.values()
            )
            if pending >= _MAX_PENDING_SCANS:
                raise AnalysisError("影像掃描工作較多，請稍後重新掃描。")
            scan_id = uuid4().hex
            job = _ScanJob(scan_id=scan_id, request=request)
            self._jobs[scan_id] = job
            job.future = self._executor.submit(self._run, job)
            return self._snapshot(job)

    def get(self, scan_id: str) -> AnalysisSourceScanStatus:
        with self._lock:
            self._prune()
            job = self._jobs.get(scan_id)
            if job is None:
                raise AnalysisError("找不到影像掃描結果，請重新掃描。")
            return self._snapshot(job)

    def cancel(self, scan_id: str) -> AnalysisSourceScanStatus:
        with self._lock:
            job = self._jobs.get(scan_id)
            if job is None:
                raise AnalysisError("找不到影像掃描結果，請重新掃描。")
            if job.status in {"queued", "scanning"}:
                job.cancelled.set()
                if job.future is not None:
                    job.future.cancel()
                job.status = "cancelled"
                job.finished_at = monotonic()
            return self._snapshot(job)

    def _run(self, job: _ScanJob) -> None:
        with self._lock:
            if job.cancelled.is_set():
                return
            job.status = "scanning"

        def update_progress(processed: int, total: int) -> None:
            with self._lock:
                if not job.cancelled.is_set():
                    job.processed_frames = processed
                    job.total_frames = total

        try:
            preview = self._scan(
                job.request,
                update_progress,
                job.cancelled.is_set,
            )
        except InterruptedError:
            job.cancelled.set()
            preview = None
            error = None
        except Exception as exc:
            logger.exception("Analysis source scan failed")
            preview = None
            error = public_error_detail(exc)
        else:
            error = None

        with self._lock:
            if job.cancelled.is_set():
                job.status = "cancelled"
            elif error is not None:
                job.status = "failed"
                job.error = error
            else:
                job.status = "completed"
                job.preview = preview
            job.finished_at = monotonic()

    def close(self) -> None:
        with self._lock:
            for job in self._jobs.values():
                if job.status in {"queued", "scanning"}:
                    job.cancelled.set()
        self._executor.shutdown(wait=False, cancel_futures=True)
