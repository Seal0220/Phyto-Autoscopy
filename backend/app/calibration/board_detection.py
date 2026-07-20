from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from app.calibration.quality_metrics import (
    MINIMUM_CHARUCO_CORNERS,
    MINIMUM_CHESSBOARD_CORNERS,
    frame_quality,
    pose_signature,
)
from app.models.calibration_models import CalibrationBoardProfile


@dataclass(frozen=True, slots=True)
class BoardDetectionResult:
    image_size: tuple[int, int]
    board_detected: bool
    marker_count: int
    corner_count: int
    capture_ready: bool
    object_points: np.ndarray
    image_points: np.ndarray
    board_center: tuple[float, float] | None
    board_scale: float | None
    pose_signature: tuple[float, ...] | None
    sharpness: float
    mean_brightness: float
    overexposed_ratio: float
    underexposed_ratio: float
    warnings: tuple[str, ...]
    preview_jpeg: bytes | None = None

    def to_dict(self, *, include_points: bool = True) -> dict[str, Any]:
        payload = {
            "image_width": self.image_size[0],
            "image_height": self.image_size[1],
            "board_detected": self.board_detected,
            "marker_count": self.marker_count,
            "corner_count": self.corner_count,
            "capture_ready": self.capture_ready,
            "board_center": list(self.board_center) if self.board_center else None,
            "board_scale": self.board_scale,
            "pose_signature": list(self.pose_signature) if self.pose_signature else None,
            "sharpness": self.sharpness,
            "mean_brightness": self.mean_brightness,
            "overexposed_ratio": self.overexposed_ratio,
            "underexposed_ratio": self.underexposed_ratio,
            "warnings": list(self.warnings),
        }
        if include_points:
            payload["object_points"] = self.object_points.astype(float).tolist()
            payload["image_points"] = self.image_points.astype(float).tolist()
        return payload


def decode_image(image_bytes: bytes) -> np.ndarray:
    encoded = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise ValueError("無法解碼相機校正影像，請重新連線後再試。")
    return image


def _aruco_dictionary(name: str):
    if not hasattr(cv2, "aruco"):
        raise ValueError("目前 OpenCV 缺少 ArUco/ChArUco 支援。")
    identifier = getattr(cv2.aruco, name, None)
    if identifier is None:
        raise ValueError(f"不支援的 ArUco dictionary：{name}")
    return cv2.aruco.getPredefinedDictionary(identifier)


def _charuco_detection(
    gray: np.ndarray,
    board_profile: CalibrationBoardProfile,
) -> tuple[np.ndarray, np.ndarray, int, list[Any], np.ndarray | None]:
    dictionary = _aruco_dictionary(board_profile.aruco_dictionary)
    board = cv2.aruco.CharucoBoard(
        (board_profile.squares_x, board_profile.squares_y),
        board_profile.square_length_mm,
        board_profile.marker_length_mm,
        dictionary,
    )
    detector = cv2.aruco.CharucoDetector(board)
    charuco_corners, charuco_ids, marker_corners, marker_ids = detector.detectBoard(gray)
    marker_count = 0 if marker_ids is None else int(len(marker_ids))
    normalized_marker_corners = (
        []
        if marker_corners is None
        else list(marker_corners)
    )
    if charuco_corners is None or charuco_ids is None:
        return (
            np.empty((0, 3), dtype=np.float32),
            np.empty((0, 2), dtype=np.float32),
            marker_count,
            normalized_marker_corners,
            marker_ids,
        )
    ids = np.asarray(charuco_ids, dtype=np.int32).reshape(-1)
    board_points = np.asarray(board.getChessboardCorners(), dtype=np.float32)
    return (
        board_points[ids].reshape(-1, 3),
        np.asarray(charuco_corners, dtype=np.float32).reshape(-1, 2),
        marker_count,
        normalized_marker_corners,
        marker_ids,
    )


def _chessboard_detection(
    gray: np.ndarray,
    board_profile: CalibrationBoardProfile,
) -> tuple[np.ndarray, np.ndarray]:
    pattern = (
        board_profile.squares_x - 1,
        board_profile.squares_y - 1,
    )
    found, corners = cv2.findChessboardCorners(
        gray,
        pattern,
        cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE,
    )
    if not found or corners is None:
        return (
            np.empty((0, 3), dtype=np.float32),
            np.empty((0, 2), dtype=np.float32),
        )
    refined = cv2.cornerSubPix(
        gray,
        corners,
        (11, 11),
        (-1, -1),
        (
            cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
            30,
            0.001,
        ),
    ).reshape(-1, 2)
    grid = np.mgrid[0:pattern[0], 0:pattern[1]].T.reshape(-1, 2)
    object_points = np.zeros((len(grid), 3), dtype=np.float32)
    object_points[:, :2] = grid.astype(np.float32) * board_profile.square_length_mm
    return object_points, refined.astype(np.float32)


def _geometry(
    points: np.ndarray,
    image_size: tuple[int, int],
) -> tuple[tuple[float, float] | None, float | None, tuple[float, ...] | None]:
    if len(points) < 4:
        return None, None, None
    width, height = image_size
    center_px = np.mean(points, axis=0)
    center = (
        float(center_px[0] / width),
        float(center_px[1] / height),
    )
    area = float(cv2.contourArea(cv2.convexHull(points.astype(np.float32))))
    scale = float(np.sqrt(max(0.0, area) / max(1.0, width * height)))
    signature = pose_signature(points, image_size)
    return center, scale, tuple(signature) if signature is not None else None


def detect_board(
    image_bytes: bytes,
    board_profile: CalibrationBoardProfile,
    *,
    include_preview: bool = False,
) -> BoardDetectionResult:
    image = decode_image(image_bytes)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    image_size = (int(gray.shape[1]), int(gray.shape[0]))
    quality = frame_quality(gray)
    marker_count = 0
    marker_corners: list[Any] = []
    marker_ids = None
    if board_profile.board_type == "charuco":
        (
            object_points,
            image_points,
            marker_count,
            marker_corners,
            marker_ids,
        ) = _charuco_detection(gray, board_profile)
        minimum_corners = MINIMUM_CHARUCO_CORNERS
    else:
        object_points, image_points = _chessboard_detection(gray, board_profile)
        minimum_corners = MINIMUM_CHESSBOARD_CORNERS
    warnings = list(quality["warnings"])
    board_detected = len(image_points) >= minimum_corners
    if not board_detected:
        warnings.append(
            f"校正板角點不足，目前 {len(image_points)} 個，至少需要 {minimum_corners} 個。"
        )
    center, scale, signature = _geometry(image_points, image_size)
    if scale is not None and scale < 0.12:
        warnings.append("校正板在畫面中過小，請將校正板移近鏡頭。")
    capture_ready = board_detected and not warnings
    preview_jpeg = None
    if include_preview:
        preview = image.copy()
        if board_profile.board_type == "charuco" and marker_ids is not None:
            cv2.aruco.drawDetectedMarkers(preview, marker_corners, marker_ids)
        if len(image_points):
            for point in image_points:
                cv2.circle(
                    preview,
                    (int(round(point[0])), int(round(point[1]))),
                    3,
                    (64, 240, 160) if capture_ready else (0, 190, 255),
                    -1,
                    cv2.LINE_AA,
                )
        encoded, data = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if encoded:
            preview_jpeg = data.tobytes()
    return BoardDetectionResult(
        image_size=image_size,
        board_detected=board_detected,
        marker_count=marker_count,
        corner_count=int(len(image_points)),
        capture_ready=capture_ready,
        object_points=object_points,
        image_points=image_points,
        board_center=center,
        board_scale=scale,
        pose_signature=signature,
        sharpness=float(quality["sharpness"]),
        mean_brightness=float(quality["mean_brightness"]),
        overexposed_ratio=float(quality["overexposed_ratio"]),
        underexposed_ratio=float(quality["underexposed_ratio"]),
        warnings=tuple(dict.fromkeys(warnings)),
        preview_jpeg=preview_jpeg,
    )
