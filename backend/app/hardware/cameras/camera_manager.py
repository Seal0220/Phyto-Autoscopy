from __future__ import annotations

from dataclasses import asdict
from threading import RLock
from typing import Any, Protocol

from app.core.config import AppSettings, CameraConfig
from app.core.exceptions import CameraError
from app.hardware.cameras.camera_identifier import (
    enumerate_opencv_device_names,
    load_opencv,
    opencv_device_name,
    scan_opencv_indices,
)
from app.hardware.cameras.camera_registry import CameraRegistry
from app.hardware.cameras.camera_types import CameraFrame, CameraScanResult
from app.hardware.cameras.camera_worker import CameraWorker
from app.models.camera_models import CameraStatus


class CameraManagerInterface(Protocol):
    def start(self) -> None: ...

    def scan(self) -> list[dict]: ...

    def reconfigure(self) -> None: ...

    def get_status(self, camera_id: str) -> CameraStatus: ...

    def get_statuses(self) -> list[CameraStatus]: ...

    def capture(self, camera_id: str) -> CameraFrame: ...

    def wait_for_frame(
        self,
        camera_id: str,
        after_sequence: int | None = None,
        timeout: float = 3.0,
    ) -> tuple[CameraFrame, int]: ...

    def begin_preview(self, camera_id: str) -> None: ...

    def end_preview(self, camera_id: str) -> None: ...

    def reconnect(self, camera_id: str) -> CameraStatus: ...

    def reconnect_all(self) -> list[CameraStatus]: ...

    def close_all(self) -> None: ...


class OpenCVCameraManager:
    def __init__(
        self,
        settings: AppSettings,
        *,
        cv2_module: Any | None = None,
    ) -> None:
        self.settings = settings
        self.registry = CameraRegistry(settings)
        self._lock = RLock()
        self._lifecycle_lock = RLock()
        self._cv2 = cv2_module
        self._workers: dict[str, CameraWorker] = {}
        self._last_error: dict[str, str | None] = {}
        self._preview_clients: dict[str, int] = {}

    def start(self) -> None:
        self._synchronize_workers()

    def reconfigure(self) -> None:
        self._synchronize_workers()

    def scan(self) -> list[dict]:
        """List device indices without reopening indices owned by live workers."""
        with self._lifecycle_lock:
            self._synchronize_workers()
            try:
                cv2 = self._get_cv2()
            except CameraError as exc:
                return self._unavailable_scan_results(str(exc))

            with self._lock:
                workers_by_index = {
                    worker.config.device_index: worker
                    for worker in self._workers.values()
                }
                assigned_by_index: dict[int, list[tuple[str, CameraConfig]]] = {}
                for camera_id, config in self.registry.all().items():
                    if config.device_index is None:
                        continue
                    assigned_by_index.setdefault(config.device_index, []).append(
                        (camera_id, config)
                    )

            active_indices = set(workers_by_index)
            device_names = enumerate_opencv_device_names(cv2_module=cv2)
            probed = {
                result.device_index: result
                for result in scan_opencv_indices(
                    self.settings.hardware.camera_scan_max_index,
                    skip_indices=active_indices,
                    cv2_module=cv2,
                    device_names=device_names,
                )
            }

        results: list[CameraScanResult] = []
        for device_index in range(self.settings.hardware.camera_scan_max_index):
            assignments = assigned_by_index.get(device_index, [])
            camera_id = assignments[0][0] if assignments else None
            camera_name = assignments[0][1].device_name if assignments else None
            worker = workers_by_index.get(device_index)
            if worker is not None:
                state = worker.state()
                results.append(
                    CameraScanResult(
                        camera_id=camera_id,
                        camera_name=camera_name,
                        device_name=opencv_device_name(
                            device_names,
                            device_index,
                            state.backend,
                        ),
                        device_index=device_index,
                        connected=state.connected,
                        error=state.error,
                        in_use=True,
                        backend=state.backend,
                    )
                )
                continue

            result = probed.get(device_index)
            results.append(
                CameraScanResult(
                    camera_id=camera_id,
                    camera_name=camera_name,
                    device_name=result.device_name if result else None,
                    device_index=device_index,
                    connected=bool(result and result.connected),
                    error=result.error if result else "相機掃描失敗。",
                    in_use=False,
                    backend=result.backend if result else None,
                )
            )
        return [asdict(result) for result in results]

    def _unavailable_scan_results(self, error: str) -> list[dict]:
        assigned_by_index = {
            config.device_index: (camera_id, config.device_name)
            for camera_id, config in self.registry.all().items()
            if config.device_index is not None
        }
        return [
            asdict(
                CameraScanResult(
                    camera_id=assigned_by_index.get(device_index, (None, None))[0],
                    camera_name=assigned_by_index.get(device_index, (None, None))[1],
                    device_index=device_index,
                    connected=False,
                    error=error,
                )
            )
            for device_index in range(self.settings.hardware.camera_scan_max_index)
        ]

    def get_status(self, camera_id: str) -> CameraStatus:
        config = self.registry.get(camera_id)
        with self._lock:
            worker = self._workers.get(camera_id)
            preview_clients = self._preview_clients.get(camera_id, 0)
            manager_error = self._last_error.get(camera_id)
        state = worker.state() if worker is not None else None
        return CameraStatus(
            camera_id=camera_id,
            camera_name=config.device_name,
            device_index=config.device_index,
            enabled=config.enabled,
            connected=bool(state and state.connected),
            previewing=bool(state and state.connected and preview_clients > 0),
            width=config.width,
            height=config.height,
            preview_fps=config.preview_fps,
            actual_fps=getattr(state, "actual_fps", 0.0),
            last_error=manager_error or (state.error if state is not None else None),
        )

    def get_statuses(self) -> list[CameraStatus]:
        return [self.get_status(camera_id) for camera_id in self.registry.roles()]

    def capture(self, camera_id: str) -> CameraFrame:
        config = self.registry.get(camera_id)
        if not config.enabled:
            raise CameraError(f"相機 {camera_id} 尚未啟用。")
        with self._lock:
            worker = self._workers.get(camera_id)
        if worker is None:
            raise CameraError(f"相機 {camera_id} 尚未開始連線。")

        # A saved capture must be newer than the request.  Preview consumers
        # may use the current cache, but snapshots/schedules first observe the
        # sequence and then wait for the next published frame.
        sequence = worker.state().sequence
        frame, _sequence = worker.wait_for_frame(
            after_sequence=sequence,
            timeout=3.0,
        )
        return frame

    def wait_for_frame(
        self,
        camera_id: str,
        after_sequence: int | None = None,
        timeout: float = 3.0,
    ) -> tuple[CameraFrame, int]:
        config = self.registry.get(camera_id)
        if not config.enabled:
            raise CameraError(f"相機 {camera_id} 尚未啟用。")
        with self._lock:
            worker = self._workers.get(camera_id)
        if worker is None:
            raise CameraError(f"相機 {camera_id} 尚未開始連線。")
        return worker.wait_for_frame(
            after_sequence=after_sequence,
            timeout=timeout,
        )

    def begin_preview(self, camera_id: str) -> None:
        self.registry.get(camera_id)
        with self._lock:
            self._preview_clients[camera_id] = (
                self._preview_clients.get(camera_id, 0) + 1
            )

    def end_preview(self, camera_id: str) -> None:
        with self._lock:
            remaining = max(0, self._preview_clients.get(camera_id, 0) - 1)
            if remaining:
                self._preview_clients[camera_id] = remaining
            else:
                self._preview_clients.pop(camera_id, None)

    def reconnect(self, camera_id: str) -> CameraStatus:
        config = self.registry.get(camera_id)
        self._replace_worker(camera_id, config)
        return self.get_status(camera_id)

    def reconnect_all(self) -> list[CameraStatus]:
        with self._lifecycle_lock:
            for camera_id, config in self.registry.all().items():
                self._replace_worker(camera_id, config)
        return self.get_statuses()

    def close_all(self) -> None:
        with self._lifecycle_lock:
            with self._lock:
                workers = list(self._workers.items())
                self._preview_clients.clear()
            for camera_id, worker in workers:
                if worker.close():
                    with self._lock:
                        if self._workers.get(camera_id) is worker:
                            self._workers.pop(camera_id, None)
                else:
                    with self._lock:
                        self._last_error[camera_id] = (
                            "相機讀取器未能在期限內關閉。"
                        )

    def _get_cv2(self):
        if self._cv2 is not None:
            return self._cv2
        cv2 = load_opencv()
        if cv2 is None:
            raise CameraError("尚未安裝 OpenCV 相機驅動程式。")
        self._cv2 = cv2
        return cv2

    @staticmethod
    def _signature(config: CameraConfig) -> tuple[Any, ...]:
        return (
            config.enabled,
            config.device_index,
            config.width,
            config.height,
            config.capture_fps,
            config.jpeg_quality,
        )

    def _synchronize_workers(self) -> None:
        with self._lifecycle_lock:
            configured = self.registry.all()
            with self._lock:
                workers = dict(self._workers)
            stale_camera_ids = set(workers).difference(configured)
            for camera_id in stale_camera_ids:
                self._remove_worker(camera_id)

            try:
                cv2 = self._get_cv2()
            except CameraError as exc:
                self.close_all()
                with self._lock:
                    for camera_id, config in configured.items():
                        self._last_error[camera_id] = (
                            str(exc) if config.enabled else "相機未啟用。"
                        )
                return

            changed_camera_ids = [
                camera_id
                for camera_id, config in configured.items()
                if (
                    (worker := workers.get(camera_id)) is not None
                    and (
                        not worker.is_running()
                        or worker.signature != self._signature(config)
                    )
                )
            ]
            for camera_id in changed_camera_ids:
                self._remove_worker(camera_id)

            for camera_id, config in configured.items():
                with self._lock:
                    worker = self._workers.get(camera_id)
                if (
                    worker is not None
                    and worker.is_running()
                    and worker.signature == self._signature(config)
                ):
                    continue
                self._replace_worker(camera_id, config, cv2_module=cv2)

    def _remove_worker(self, camera_id: str) -> None:
        with self._lifecycle_lock:
            with self._lock:
                worker = self._workers.get(camera_id)
            if worker is not None and not worker.close():
                error = "舊相機連線尚未安全關閉，請稍後再試。"
                with self._lock:
                    self._last_error[camera_id] = error
                raise CameraError(error)
            with self._lock:
                if self._workers.get(camera_id) is worker:
                    self._workers.pop(camera_id, None)
                self._last_error.pop(camera_id, None)
                self._preview_clients.pop(camera_id, None)

    def _replace_worker(
        self,
        camera_id: str,
        config: CameraConfig,
        *,
        cv2_module: Any | None = None,
    ) -> None:
        with self._lifecycle_lock:
            with self._lock:
                previous = self._workers.get(camera_id)
            if previous is not None and not previous.close():
                error = "舊相機連線尚未安全關閉，請稍後再重新連線。"
                with self._lock:
                    self._workers[camera_id] = previous
                    self._last_error[camera_id] = error
                raise CameraError(error)
            with self._lock:
                if self._workers.get(camera_id) is previous:
                    self._workers.pop(camera_id, None)

            if not config.enabled:
                with self._lock:
                    self._last_error[camera_id] = "相機未啟用。"
                return

            if config.device_index is None:
                with self._lock:
                    self._last_error[camera_id] = "相機尚未選擇裝置。"
                return

            try:
                cv2 = cv2_module or self._get_cv2()
            except CameraError as exc:
                with self._lock:
                    self._last_error[camera_id] = str(exc)
                return

            worker = CameraWorker(camera_id, config, cv2)
            with self._lock:
                self._workers[camera_id] = worker
                self._last_error[camera_id] = None
            worker.start()
