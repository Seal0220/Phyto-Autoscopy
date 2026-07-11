from __future__ import annotations

from app.hardware.cameras.camera_types import CameraScanResult


def scan_opencv_indices(max_index: int) -> list[CameraScanResult]:
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        return [CameraScanResult("opencv", -1, False, f"OpenCV import failed: {exc}")]

    results: list[CameraScanResult] = []
    for index in range(max_index):
        capture = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        connected = bool(capture and capture.isOpened())
        results.append(CameraScanResult(str(index), index, connected))
        if capture:
            capture.release()
    return results
