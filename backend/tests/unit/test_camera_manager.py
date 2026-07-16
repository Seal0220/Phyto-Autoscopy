from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock
from time import monotonic, sleep
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.config import AppSettings, CameraConfig
from app.core.exceptions import CameraError
from app.hardware.cameras.camera_identifier import (
    camera_backend_candidates,
    configure_opencv_logging,
    open_opencv_capture,
)
from app.hardware.cameras.camera_manager import OpenCVCameraManager
from app.hardware.cameras.camera_worker import CameraWorker
from app.hardware.cameras.mock_camera import MockCameraManager


class FakeEncoded:
    def __init__(self, value: bytes) -> None:
        self.value = value

    def tobytes(self) -> bytes:
        return self.value


class FakeCapture:
    def __init__(
        self,
        device_index: int,
        fail_reads: bool = False,
        opened: bool = True,
        on_release=None,
    ) -> None:
        self.device_index = device_index
        self.fail_reads = fail_reads
        self.opened = opened
        self.on_release = on_release
        self.released = False
        self.read_count = 0
        self.properties: list[tuple[int, int]] = []

    def isOpened(self) -> bool:
        return self.opened and not self.released

    def set(self, prop: int, value: int) -> bool:
        self.properties.append((prop, value))
        return True

    def read(self):
        self.read_count += 1
        if self.released or self.fail_reads:
            return False, None
        return True, f"frame-{self.device_index}-{self.read_count}".encode()

    def release(self) -> None:
        if self.released:
            return
        self.released = True
        if self.opened and self.on_release is not None:
            self.on_release(self.device_index)


class FakeVideoRegistry:
    def __init__(self, owner) -> None:
        self.owner = owner

    def getCameraBackends(self) -> tuple[int, ...]:
        return (self.owner.CAP_MSMF, self.owner.CAP_DSHOW)

    def getBackendName(self, backend: int) -> str:
        return {
            self.owner.CAP_MSMF: "MSMF",
            self.owner.CAP_DSHOW: "DSHOW",
        }.get(backend, "AUTO")


class FakeCV2:
    CAP_ANY = 0
    CAP_DSHOW = 700
    CAP_MSMF = 1400
    CAP_PROP_FRAME_WIDTH = 3
    CAP_PROP_FRAME_HEIGHT = 4
    CAP_PROP_FPS = 5
    CAP_PROP_FOURCC = 6
    CAP_PROP_BUFFERSIZE = 38
    IMWRITE_JPEG_QUALITY = 1

    def __init__(self) -> None:
        self.videoio_registry = FakeVideoRegistry(self)
        self.open_calls: list[tuple[int, int | None, FakeCapture]] = []
        self.fail_first_device_zero = False
        self.fail_open_backends: set[int] = set()
        self._active_lock = Lock()
        self.active_by_index: dict[int, int] = {}
        self.maximum_active_by_index: dict[int, int] = {}

    def VideoCapture(
        self,
        device_index: int,
        backend: int | None = None,
    ) -> FakeCapture:
        effective_backend = self.CAP_ANY if backend is None else backend
        failed_read = (
            self.fail_first_device_zero
            and device_index == 0
            and not any(call[0] == 0 for call in self.open_calls)
        )
        opened = effective_backend not in self.fail_open_backends
        capture = FakeCapture(
            device_index,
            fail_reads=failed_read,
            opened=opened,
            on_release=self._capture_released,
        )
        self.open_calls.append((device_index, backend, capture))
        if opened:
            with self._active_lock:
                active = self.active_by_index.get(device_index, 0) + 1
                self.active_by_index[device_index] = active
                self.maximum_active_by_index[device_index] = max(
                    active,
                    self.maximum_active_by_index.get(device_index, 0),
                )
        return capture

    def _capture_released(self, device_index: int) -> None:
        with self._active_lock:
            self.active_by_index[device_index] = max(
                0,
                self.active_by_index.get(device_index, 0) - 1,
            )

    def imencode(self, _extension: str, image: bytes, _options: list[int]):
        return True, FakeEncoded(b"jpeg:" + image)

    @staticmethod
    def VideoWriter_fourcc(*_value: str) -> int:
        return 1234


def physical_camera_settings() -> AppSettings:
    settings = AppSettings()
    settings.hardware.camera_scan_max_index = 3
    settings.cameras["top"].capture_fps = 60
    settings.cameras["side"].enabled = False
    settings.cameras["rotating"].enabled = False
    return settings


def test_mock_camera_capture_returns_jpeg_bytes() -> None:
    manager = MockCameraManager(AppSettings())
    frame = manager.capture("top")
    assert frame.data.startswith(b"\xff\xd8")
    assert frame.content_type == "image/jpeg"


def test_mock_camera_status_reports_measured_fps(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.hardware.cameras.mock_camera.make_mock_jpeg",
        lambda camera_id, sequence: f"{camera_id}-{sequence}".encode(),
    )
    settings = AppSettings()
    settings.cameras["top"].capture_fps = 60
    manager = MockCameraManager(settings)
    _first, sequence = manager.wait_for_frame("top")
    manager.wait_for_frame(
        "top",
        after_sequence=sequence,
    )

    assert manager.get_status("top").actual_fps > 0


def test_opencv_native_logging_keeps_errors_and_fatal_messages() -> None:
    levels: list[int] = []
    logging_api = SimpleNamespace(
        LOG_LEVEL_ERROR=7,
        setLogLevel=levels.append,
    )
    fake_cv2 = SimpleNamespace(
        utils=SimpleNamespace(logging=logging_api),
    )

    configure_opencv_logging(fake_cv2)

    assert levels == [7]


def test_windows_camera_backends_use_registered_msmf_and_dshow(
    monkeypatch,
) -> None:
    fake_cv2 = FakeCV2()
    monkeypatch.setattr(
        "app.hardware.cameras.camera_identifier.sys.platform",
        "win32",
    )

    assert camera_backend_candidates(fake_cv2) == [
        fake_cv2.CAP_MSMF,
        fake_cv2.CAP_DSHOW,
    ]


def test_windows_camera_open_falls_back_from_msmf_to_dshow(monkeypatch) -> None:
    fake_cv2 = FakeCV2()
    fake_cv2.fail_open_backends.add(fake_cv2.CAP_MSMF)
    monkeypatch.setattr(
        "app.hardware.cameras.camera_identifier.sys.platform",
        "win32",
    )

    capture, backend, error = open_opencv_capture(0, cv2_module=fake_cv2)

    assert capture is not None
    assert backend == "DSHOW"
    assert error is None
    assert [call[1] for call in fake_cv2.open_calls] == [
        fake_cv2.CAP_MSMF,
        fake_cv2.CAP_DSHOW,
    ]
    assert fake_cv2.open_calls[0][2].released is True
    capture.release()


def test_physical_camera_reuses_one_capture_and_scan_skips_active_index(
    monkeypatch,
) -> None:
    fake_cv2 = FakeCV2()
    monkeypatch.setattr(
        "app.hardware.cameras.camera_identifier.sys.platform",
        "win32",
    )
    manager = OpenCVCameraManager(
        physical_camera_settings(),
        cv2_module=fake_cv2,
    )
    manager.start()
    try:
        first, sequence = manager.wait_for_frame("top")
        second, next_sequence = manager.wait_for_frame(
            "top",
            after_sequence=sequence,
        )

        assert first.data.startswith(b"jpeg:")
        assert second.data.startswith(b"jpeg:")
        assert next_sequence > sequence
        assert manager.get_status("top").actual_fps > 0
        assert [call[1] for call in fake_cv2.open_calls if call[0] == 0] == [
            fake_cv2.CAP_MSMF
        ]

        scanned = manager.scan()
        top_device = next(item for item in scanned if item["device_index"] == 0)

        assert top_device == {
            "camera_id": "top",
            "device_index": 0,
            "connected": True,
            "error": None,
            "camera_name": "CHLOROCULUS EYE-TOP",
            "in_use": True,
            "backend": "MSMF",
        }
        assert len([call for call in fake_cv2.open_calls if call[0] == 0]) == 1
    finally:
        manager.close_all()

    assert all(call[2].released for call in fake_cv2.open_calls)


def test_capture_waits_for_frame_newer_than_request(monkeypatch) -> None:
    fake_cv2 = FakeCV2()
    monkeypatch.setattr(
        "app.hardware.cameras.camera_identifier.sys.platform",
        "win32",
    )
    manager = OpenCVCameraManager(
        physical_camera_settings(),
        cv2_module=fake_cv2,
    )
    manager.start()
    try:
        cached, sequence = manager.wait_for_frame("top")
        captured = manager.capture("top")
        _next, next_sequence = manager.wait_for_frame("top")

        assert captured.data != cached.data
        assert next_sequence > sequence
    finally:
        manager.close_all()


def test_concurrent_reconnect_and_reconfigure_never_duplicate_reader(
    monkeypatch,
) -> None:
    fake_cv2 = FakeCV2()
    monkeypatch.setattr(
        "app.hardware.cameras.camera_identifier.sys.platform",
        "win32",
    )
    manager = OpenCVCameraManager(
        physical_camera_settings(),
        cv2_module=fake_cv2,
    )
    manager.start()
    try:
        manager.wait_for_frame("top")
        operations = [
            lambda: manager.reconnect("top"),
            manager.reconfigure,
            lambda: manager.reconnect("top"),
            manager.reconfigure,
        ]
        barrier = Barrier(len(operations) + 1)

        def run_together(operation):
            barrier.wait(timeout=1.0)
            return operation()

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(run_together, operation)
                for operation in operations
            ]
            barrier.wait(timeout=1.0)
            for future in futures:
                future.result(timeout=3.0)

        manager.wait_for_frame("top")
        assert fake_cv2.maximum_active_by_index[0] == 1
    finally:
        manager.close_all()


def test_physical_camera_recovers_after_read_failure(monkeypatch) -> None:
    fake_cv2 = FakeCV2()
    fake_cv2.fail_first_device_zero = True
    monkeypatch.setattr(CameraWorker, "_OPEN_RETRY_SECONDS", 0.01)
    monkeypatch.setattr(
        "app.hardware.cameras.camera_identifier.sys.platform",
        "win32",
    )
    manager = OpenCVCameraManager(
        physical_camera_settings(),
        cv2_module=fake_cv2,
    )
    manager.start()
    try:
        frame, _sequence = manager.wait_for_frame("top", timeout=2.0)
        assert frame.data.startswith(b"jpeg:")
        assert len([call for call in fake_cv2.open_calls if call[0] == 0]) == 2
        assert fake_cv2.open_calls[0][2].released is True
    finally:
        manager.close_all()


def test_worker_read_failures_back_off_and_log_once(caplog) -> None:
    fake_cv2 = FakeCV2()
    lifecycle_waits: list[float] = []

    class ControlledStopEvent:
        def __init__(self) -> None:
            self.stopped = False

        def is_set(self) -> bool:
            return self.stopped

        def wait(self, delay: float) -> bool:
            if delay != 0.1:
                lifecycle_waits.append(delay)
                if len(lifecycle_waits) >= 3:
                    self.stopped = True
            return self.stopped

    def open_failing_capture(
        device_index: int,
        backend: int | None = None,
    ) -> FakeCapture:
        capture = FakeCapture(
            device_index,
            fail_reads=True,
        )
        fake_cv2.open_calls.append((device_index, backend, capture))
        return capture

    fake_cv2.VideoCapture = open_failing_capture
    worker = CameraWorker(
        "top",
        physical_camera_settings().cameras["top"],
        fake_cv2,
    )
    worker._OPEN_RETRY_SECONDS = 0.01
    worker._MAX_OPEN_RETRY_SECONDS = 0.04
    worker._stop_event = ControlledStopEvent()

    worker._run()

    assert lifecycle_waits == [0.01, 0.02, 0.04]
    assert len(fake_cv2.open_calls) == 3
    assert [record.getMessage() for record in caplog.records] == [
        "相機 top 讀取失敗，正在重新連線。"
    ]
    assert all(capture.released for _, _, capture in fake_cv2.open_calls)


def test_enabled_cameras_cannot_share_device_index() -> None:
    payload = AppSettings().model_dump(mode="python")
    payload["cameras"]["side"]["device_index"] = 0

    with pytest.raises(ValidationError, match="已啟用相機不可共用裝置索引"):
        AppSettings.model_validate(payload)


def test_only_disabled_camera_may_have_no_device_index() -> None:
    payload = AppSettings().model_dump(mode="python")
    payload["cameras"]["side"]["enabled"] = False
    payload["cameras"]["side"]["device_index"] = None

    settings = AppSettings.model_validate(payload)

    assert settings.cameras["side"].device_index is None

    payload["cameras"]["side"]["enabled"] = True
    with pytest.raises(ValidationError, match="已啟用相機必須選擇裝置"):
        AppSettings.model_validate(payload)


def test_failed_worker_close_does_not_allow_duplicate_reader() -> None:
    settings = physical_camera_settings()
    fake_cv2 = FakeCV2()
    manager = OpenCVCameraManager(settings, cv2_module=fake_cv2)

    class StoppingWorker:
        signature = manager._signature(settings.cameras["top"])

        @staticmethod
        def close() -> bool:
            return False

        @staticmethod
        def state():
            return SimpleNamespace(
                connected=False,
                error="相機連線已關閉。",
            )

    worker = StoppingWorker()
    manager._workers["top"] = worker

    with pytest.raises(CameraError, match="尚未安全關閉"):
        manager._replace_worker(
            "top",
            settings.cameras["top"],
            cv2_module=fake_cv2,
        )

    assert manager._workers["top"] is worker
    assert fake_cv2.open_calls == []
    assert manager._last_error["top"] == (
        "舊相機連線尚未安全關閉，請稍後再重新連線。"
    )
    assert manager.get_status("top").last_error == (
        "舊相機連線尚未安全關閉，請稍後再重新連線。"
    )


def test_reconfigure_removes_worker_missing_from_registry(monkeypatch) -> None:
    settings = physical_camera_settings()
    settings.cameras["temporary"] = CameraConfig(
        device_name="Temporary camera",
        device_index=3,
    )
    fake_cv2 = FakeCV2()
    monkeypatch.setattr(
        "app.hardware.cameras.camera_identifier.sys.platform",
        "win32",
    )
    manager = OpenCVCameraManager(settings, cv2_module=fake_cv2)
    manager.start()
    try:
        manager.wait_for_frame("temporary")
        temporary_capture = next(
            call[2] for call in fake_cv2.open_calls if call[0] == 3
        )

        settings.cameras.pop("temporary")
        manager.reconfigure()

        assert "temporary" not in manager._workers
        assert temporary_capture.released is True
    finally:
        manager.close_all()


def test_configure_failure_releases_capture(monkeypatch) -> None:
    fake_cv2 = FakeCV2()
    worker = CameraWorker(
        "top",
        physical_camera_settings().cameras["top"],
        fake_cv2,
    )
    configure_called = Event()

    def fail_configuration(_capture) -> None:
        configure_called.set()
        worker._stop_event.set()
        raise RuntimeError("configuration failed")

    monkeypatch.setattr(worker, "_configure_capture", fail_configuration)
    worker.start()

    assert configure_called.wait(timeout=1.0)
    assert worker.close() is True
    assert fake_cv2.open_calls[0][2].released is True
    assert worker.state().connected is False


def test_close_does_not_release_while_read_is_blocked_or_publish_after_stop(
    monkeypatch,
) -> None:
    fake_cv2 = FakeCV2()
    read_started = Event()
    allow_read_to_finish = Event()

    class BlockingCapture(FakeCapture):
        def read(self):
            read_started.set()
            allow_read_to_finish.wait(timeout=1.0)
            return True, b"blocked-frame"

    blocking_capture = BlockingCapture(0)

    def open_blocking_capture(_device_index, _backend=None):
        fake_cv2.open_calls.append((0, _backend, blocking_capture))
        return blocking_capture

    monkeypatch.setattr(fake_cv2, "VideoCapture", open_blocking_capture)
    monkeypatch.setattr(CameraWorker, "_CLOSE_TIMEOUT_SECONDS", 0.02)
    worker = CameraWorker(
        "top",
        physical_camera_settings().cameras["top"],
        fake_cv2,
    )
    initial_sequence = worker.state().sequence
    worker.start()

    assert read_started.wait(timeout=1.0)
    assert worker.close() is False
    assert blocking_capture.released is False

    allow_read_to_finish.set()
    deadline = monotonic() + 1.0
    while not blocking_capture.released and monotonic() < deadline:
        sleep(0.01)

    assert blocking_capture.released is True
    assert worker.state().sequence == initial_sequence
    assert worker.close() is True
