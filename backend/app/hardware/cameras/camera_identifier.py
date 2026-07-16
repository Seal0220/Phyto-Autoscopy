from __future__ import annotations

import logging
import sys
from typing import Any

from app.hardware.cameras.camera_types import CameraScanResult

logger = logging.getLogger(__name__)


def configure_opencv_logging(cv2: Any) -> None:
    """Suppress expected probe warnings while retaining driver errors."""
    logging_api = getattr(getattr(cv2, "utils", None), "logging", None)
    set_log_level = getattr(logging_api, "setLogLevel", None)
    error_level = getattr(logging_api, "LOG_LEVEL_ERROR", 2)
    if not callable(set_log_level):
        set_log_level = getattr(cv2, "setLogLevel", None)
        error_level = getattr(cv2, "LOG_LEVEL_ERROR", error_level)
    if not callable(set_log_level):
        return

    try:
        set_log_level(error_level)
    except Exception:
        logger.debug("無法調整 OpenCV 原生日誌層級。", exc_info=True)


def load_opencv():
    try:
        import cv2  # type: ignore
    except ImportError:
        return None
    configure_opencv_logging(cv2)
    return cv2


def _backend_name(cv2: Any, backend: int) -> str:
    if backend == getattr(cv2, "CAP_ANY", 0):
        return "AUTO"
    try:
        return str(cv2.videoio_registry.getBackendName(backend))
    except Exception:
        if backend == getattr(cv2, "CAP_MSMF", None):
            return "MSMF"
        return str(backend)


def camera_backend_candidates(cv2: Any) -> list[int]:
    """Return registered camera backends without probing unrelated adapters."""
    cap_any = getattr(cv2, "CAP_ANY", 0)
    if not sys.platform.startswith("win"):
        return [cap_any]

    cap_msmf = getattr(cv2, "CAP_MSMF", None)
    cap_dshow = getattr(cv2, "CAP_DSHOW", None)
    registry_available = True
    try:
        camera_backends = set(cv2.videoio_registry.getCameraBackends())
    except Exception:
        registry_available = False
        camera_backends = set()

    candidates = [
        backend
        for backend in (cap_msmf, cap_dshow)
        if backend is not None
        and (backend in camera_backends or not registry_available)
    ]
    return list(dict.fromkeys(candidates)) or [cap_any]


def open_opencv_capture(
    device_index: int,
    *,
    cv2_module: Any | None = None,
) -> tuple[Any | None, str | None, str | None]:
    cv2 = cv2_module or load_opencv()
    if cv2 is None:
        return None, None, "尚未安裝 OpenCV 相機驅動程式。"

    errors: list[str] = []
    for backend in camera_backend_candidates(cv2):
        backend_name = _backend_name(cv2, backend)
        capture = None
        opened = False
        try:
            if backend == getattr(cv2, "CAP_ANY", 0):
                capture = cv2.VideoCapture(device_index)
            else:
                capture = cv2.VideoCapture(device_index, backend)
            opened = bool(capture and capture.isOpened())
            if opened:
                return capture, backend_name, None
            errors.append(f"{backend_name} 無法開啟")
        except Exception:
            errors.append(f"{backend_name} 開啟失敗")
            logger.debug(
                "OpenCV backend failed while opening device index %s: %s",
                device_index,
                backend_name,
                exc_info=True,
            )
        finally:
            if capture is not None and not opened:
                try:
                    capture.release()
                except Exception:
                    logger.debug(
                        "Failed to release unopened camera index %s",
                        device_index,
                        exc_info=True,
                    )

    detail = "、".join(errors) if errors else "沒有可用的 OpenCV 相機後端"
    return None, None, f"裝置索引 {device_index} 無法連線（{detail}）。"


def scan_opencv_indices(
    max_index: int,
    *,
    skip_indices: set[int] | None = None,
    cv2_module: Any | None = None,
) -> list[CameraScanResult]:
    cv2 = cv2_module or load_opencv()
    if cv2 is None:
        return [
            CameraScanResult(
                camera_id=None,
                device_index=-1,
                connected=False,
                error="尚未安裝 OpenCV 相機驅動程式。",
            )
        ]

    skipped = skip_indices or set()
    results: list[CameraScanResult] = []
    for index in range(max_index):
        if index in skipped:
            continue
        capture, backend, error = open_opencv_capture(
            index,
            cv2_module=cv2,
        )
        connected = capture is not None
        results.append(
            CameraScanResult(
                camera_id=None,
                device_index=index,
                connected=connected,
                error=error,
                backend=backend,
            )
        )
        if capture is not None:
            try:
                capture.release()
            except Exception:
                logger.warning(
                    "Failed to release scanned camera index %s",
                    index,
                    exc_info=True,
                )
    return results
