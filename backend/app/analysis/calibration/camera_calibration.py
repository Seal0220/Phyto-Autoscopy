from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from math import radians, tan
from typing import Any

import cv2
import numpy as np

from .calibration_quality import (
    calculate_point_coverage,
    calculate_reprojection_errors,
    normalize_image_points,
    require_matching_image_sizes,
    validate_camera_matrix,
    validate_distortion_coefficients,
    validate_image_size,
)


DISTORTION_COEFFICIENT_ORDER = ("k1", "k2", "p1", "p2", "k3")
DEFAULT_CORNER_DETECTION_FLAGS = (
    cv2.CALIB_CB_ADAPTIVE_THRESH
    | cv2.CALIB_CB_NORMALIZE_IMAGE
)
DEFAULT_SUBPIX_CRITERIA = (
    cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
    30,
    0.001,
)
DEFAULT_CALIBRATION_CRITERIA = (
    cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
    100,
    1e-7,
)
FISHEYE_CALIB_USE_INTRINSIC_GUESS = 1 << 0
FISHEYE_CALIB_RECOMPUTE_EXTRINSIC = 1 << 1
FISHEYE_CALIB_CHECK_COND = 1 << 2
FISHEYE_CALIB_FIX_SKEW = 1 << 3

CalibrationImage = str | PathLike[str] | np.ndarray
SquareSize = float | tuple[float, float] | list[float]


@dataclass(slots=True)
class ChessboardDetection:
    image_id: str
    image_size: tuple[int, int]
    found: bool
    corners: np.ndarray | None

    def to_dict(self, *, include_corners: bool = True) -> dict[str, Any]:
        return {
            "image_id": self.image_id,
            "image_width": self.image_size[0],
            "image_height": self.image_size[1],
            "found": self.found,
            "corner_count": 0 if self.corners is None else int(len(self.corners)),
            "corners": (
                self.corners.reshape(-1, 2).astype(float).tolist()
                if include_corners and self.corners is not None
                else None
            ),
        }


@dataclass(slots=True)
class CameraCalibrationResult:
    image_size: tuple[int, int]
    pattern_size: tuple[int, int]
    square_size_mm: tuple[float, float]
    camera_matrix: np.ndarray
    distortion_coefficients: np.ndarray
    rotation_vectors: tuple[np.ndarray, ...]
    translation_vectors: tuple[np.ndarray, ...]
    rms_error: float
    mean_reprojection_error: float
    reprojection_error_per_image: tuple[dict[str, float | int | str], ...]
    point_coverage: dict[str, Any]
    image_ids: tuple[str, ...]
    total_image_count: int
    successful_image_count: int
    corner_detections: tuple[ChessboardDetection, ...] = ()
    projection_model: str = "brown_pinhole"

    @property
    def distortion_named(self) -> dict[str, float]:
        if self.projection_model == "fisheye":
            coefficients = self.distortion_coefficients.reshape(-1)
            return {
                name: float(coefficients[index])
                for index, name in enumerate(("k1", "k2", "k3", "k4"))
            }
        return distortion_coefficients_named(self.distortion_coefficients)

    def to_dict(self, *, include_corners: bool = True) -> dict[str, Any]:
        return {
            "image_width": self.image_size[0],
            "image_height": self.image_size[1],
            "chessboard_pattern": list(self.pattern_size),
            "square_size_mm": list(self.square_size_mm),
            "camera_matrix": self.camera_matrix.astype(float).tolist(),
            "distortion_coefficients": (
                self.distortion_coefficients.reshape(-1).astype(float).tolist()
            ),
            "projection_model": self.projection_model,
            "distortion_coefficient_order": (
                ["k1", "k2", "k3", "k4"]
                if self.projection_model == "fisheye"
                else list(DISTORTION_COEFFICIENT_ORDER)
            ),
            "distortion_named": self.distortion_named,
            "rotation_vectors": [
                vector.reshape(-1).astype(float).tolist()
                for vector in self.rotation_vectors
            ],
            "translation_vectors": [
                vector.reshape(-1).astype(float).tolist()
                for vector in self.translation_vectors
            ],
            "rms_error": self.rms_error,
            "mean_reprojection_error": self.mean_reprojection_error,
            "reprojection_error_per_image": list(self.reprojection_error_per_image),
            "point_coverage": self.point_coverage,
            "image_ids": list(self.image_ids),
            "total_image_count": self.total_image_count,
            "successful_image_count": self.successful_image_count,
            "corner_detections": [
                detection.to_dict(include_corners=include_corners)
                for detection in self.corner_detections
            ],
        }


def normalize_pattern_size(pattern_size: Sequence[int]) -> tuple[int, int]:
    if len(pattern_size) != 2:
        raise ValueError("pattern_size 必須是 (欄數, 列數)。")
    columns, rows = (int(value) for value in pattern_size)
    if columns < 2 or rows < 2:
        raise ValueError("棋盤內角點欄數與列數必須至少為 2。")
    return columns, rows


def normalize_square_size_mm(square_size_mm: SquareSize) -> tuple[float, float]:
    """Validate measured chessboard spacing without deriving it from board size."""

    if square_size_mm is None or isinstance(square_size_mm, (str, bytes, bool)):
        raise ValueError(
            "square_size_mm 必須明確提供實際測量值，不得留空或推導。"
        )
    if isinstance(square_size_mm, (int, float, np.number)):
        normalized = (float(square_size_mm), float(square_size_mm))
    else:
        if len(square_size_mm) != 2:
            raise ValueError("square_size_mm 必須為單一數值或 (x, y)。")
        normalized = (float(square_size_mm[0]), float(square_size_mm[1]))
    if not np.isfinite(normalized).all() or normalized[0] <= 0 or normalized[1] <= 0:
        raise ValueError("square_size_mm 必須是已實際測量的正有限數值。")
    return normalized


def create_chessboard_object_points(
    pattern_size: Sequence[int],
    square_size_mm: SquareSize,
) -> np.ndarray:
    """Create planar object points from explicit measured square spacing."""

    columns, rows = normalize_pattern_size(pattern_size)
    square_x, square_y = normalize_square_size_mm(square_size_mm)
    points = np.zeros((columns * rows, 3), dtype=np.float32)
    grid = np.mgrid[0:columns, 0:rows].T.reshape(-1, 2).astype(np.float32)
    points[:, 0] = grid[:, 0] * square_x
    points[:, 1] = grid[:, 1] * square_y
    return points


def distortion_coefficients_named(coefficients: Any) -> dict[str, float]:
    """Map OpenCV's first five distortion coefficients to their names.

    OpenCV stores the baseline coefficients as ``k1, k2, p1, p2, k3``.
    Keeping this ordering beside a named representation prevents the common
    mistake of serializing ``k3`` before the tangential coefficients.
    """

    normalized = validate_distortion_coefficients(
        coefficients,
        name="distortion_coefficients",
    )
    return {
        name: float(normalized[index])
        for index, name in enumerate(DISTORTION_COEFFICIENT_ORDER)
    }


def load_calibration_image(image: CalibrationImage) -> np.ndarray:
    if isinstance(image, (str, PathLike)):
        image_path = Path(image)
        if not image_path.is_file():
            raise ValueError(f"校正影像不存在：{image_path}")
        try:
            encoded_image = np.fromfile(image_path, dtype=np.uint8)
        except OSError as error:
            raise ValueError(f"無法讀取校正影像：{image_path}") from error
        if encoded_image.size == 0:
            raise ValueError(f"校正影像為空：{image_path}")
        try:
            loaded = cv2.imdecode(encoded_image, cv2.IMREAD_UNCHANGED)
        except cv2.error as error:
            raise ValueError(f"無法解碼校正影像：{image_path}") from error
        if loaded is None:
            raise ValueError(f"無法讀取校正影像：{image_path}")
    else:
        loaded = np.asarray(image)

    if loaded.ndim not in (2, 3) or loaded.shape[0] <= 0 or loaded.shape[1] <= 0:
        raise ValueError("校正影像必須是非空的灰階或彩色影像。")
    if loaded.ndim == 3 and loaded.shape[2] not in (1, 3, 4):
        raise ValueError("校正影像只支援 1、3 或 4 通道。")
    if loaded.dtype != np.uint8:
        raise ValueError("棋盤角點偵測需要 uint8 校正影像。")
    return np.ascontiguousarray(loaded)


def _to_grayscale(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    if image.shape[2] == 1:
        return image[:, :, 0]
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def detect_chessboard_corners(
    image: CalibrationImage,
    pattern_size: Sequence[int],
    *,
    image_id: str = "0",
    flags: int = DEFAULT_CORNER_DETECTION_FLAGS,
    subpixel_window: tuple[int, int] = (11, 11),
    criteria: tuple[int, int, float] = DEFAULT_SUBPIX_CRITERIA,
) -> ChessboardDetection:
    """Detect and refine chessboard inner corners in one image."""

    normalized_pattern = normalize_pattern_size(pattern_size)
    loaded = load_calibration_image(image)
    image_size = (int(loaded.shape[1]), int(loaded.shape[0]))
    gray = _to_grayscale(loaded)
    found, corners = cv2.findChessboardCorners(
        gray,
        normalized_pattern,
        flags,
    )
    if not found or corners is None:
        return ChessboardDetection(
            image_id=str(image_id),
            image_size=image_size,
            found=False,
            corners=None,
        )

    refined = cv2.cornerSubPix(
        gray,
        corners,
        subpixel_window,
        (-1, -1),
        criteria,
    )
    normalized_corners = normalize_image_points(
        refined,
        name="corners",
        expected_count=normalized_pattern[0] * normalized_pattern[1],
    )
    return ChessboardDetection(
        image_id=str(image_id),
        image_size=image_size,
        found=True,
        corners=normalized_corners,
    )


def calibrate_camera(
    images: Sequence[CalibrationImage],
    pattern_size: Sequence[int],
    square_size_mm: SquareSize,
    *,
    image_ids: Sequence[str] | None = None,
    corner_flags: int = DEFAULT_CORNER_DETECTION_FLAGS,
    calibration_flags: int = 0,
    criteria: tuple[int, int, float] = DEFAULT_CALIBRATION_CRITERIA,
) -> CameraCalibrationResult:
    """Detect corners and calibrate one camera from chessboard images."""

    if not images:
        raise ValueError("至少需要一張單目校正影像。")
    if image_ids is not None and len(image_ids) != len(images):
        raise ValueError("image_ids 數量必須與校正影像數量一致。")

    normalized_pattern = normalize_pattern_size(pattern_size)
    normalized_square_size = normalize_square_size_mm(square_size_mm)
    loaded_images = [load_calibration_image(image) for image in images]
    ids = tuple(
        str(image_ids[index]) if image_ids is not None else str(index)
        for index in range(len(images))
    )
    image_size = require_matching_image_sizes(
        [(image.shape[1], image.shape[0]) for image in loaded_images],
        names=ids,
    )
    detections = tuple(
        detect_chessboard_corners(
            image,
            normalized_pattern,
            image_id=ids[index],
            flags=corner_flags,
        )
        for index, image in enumerate(loaded_images)
    )
    successful = [detection for detection in detections if detection.found]
    if not successful:
        raise ValueError("所有單目校正影像皆無法偵測棋盤角點。")

    result = calibrate_camera_from_points(
        [detection.corners for detection in successful],
        image_size,
        normalized_pattern,
        normalized_square_size,
        image_ids=[detection.image_id for detection in successful],
        calibration_flags=calibration_flags,
        criteria=criteria,
        total_image_count=len(images),
    )
    result.corner_detections = detections
    return result


def calibrate_camera_from_points(
    image_points: Sequence[Any],
    image_size: Sequence[int],
    pattern_size: Sequence[int],
    square_size_mm: SquareSize,
    *,
    image_ids: Sequence[str] | None = None,
    calibration_flags: int = 0,
    criteria: tuple[int, int, float] = DEFAULT_CALIBRATION_CRITERIA,
    total_image_count: int | None = None,
    initial_camera_matrix: Any | None = None,
) -> CameraCalibrationResult:
    """Calibrate one camera from precomputed corners.

    This entry point intentionally still requires ``square_size_mm``. Image
    dimensions or paper board dimensions are never used to infer physical
    spacing.
    """

    normalized_pattern = normalize_pattern_size(pattern_size)
    normalized_square_size = normalize_square_size_mm(square_size_mm)
    normalized_image_size = validate_image_size(image_size)
    expected_corner_count = normalized_pattern[0] * normalized_pattern[1]
    if not image_points:
        raise ValueError("至少需要一組已偵測的棋盤角點。")
    if image_ids is not None and len(image_ids) != len(image_points):
        raise ValueError("image_ids 數量必須與角點組數一致。")
    if total_image_count is not None and total_image_count < len(image_points):
        raise ValueError("total_image_count 不得小於成功角點組數。")

    normalized_image_points = [
        normalize_image_points(
            points,
            name=f"image_points[{index}]",
            expected_count=expected_corner_count,
        )
        for index, points in enumerate(image_points)
    ]
    object_template = create_chessboard_object_points(
        normalized_pattern,
        normalized_square_size,
    )
    object_points = [object_template.copy() for _ in normalized_image_points]

    initial_matrix = (
        validate_camera_matrix(
            initial_camera_matrix,
            name="initial_camera_matrix",
        ).copy()
        if initial_camera_matrix is not None
        else None
    )
    effective_flags = calibration_flags | (
        cv2.CALIB_USE_INTRINSIC_GUESS
        if initial_matrix is not None
        else 0
    )
    try:
        (
            rms_error,
            camera_matrix,
            distortion_coefficients,
            rotation_vectors,
            translation_vectors,
        ) = cv2.calibrateCamera(
            object_points,
            normalized_image_points,
            normalized_image_size,
            initial_matrix,
            None,
            flags=effective_flags,
            criteria=criteria,
        )
    except cv2.error as error:
        raise ValueError(f"單目相機校正失敗：{error}") from error

    camera_matrix = validate_camera_matrix(
        camera_matrix,
        name="camera_matrix",
    )
    distortion_coefficients = validate_distortion_coefficients(
        distortion_coefficients,
        name="distortion_coefficients",
    )
    if not np.isfinite(rms_error):
        raise ValueError("單目校正產生無效的 RMS 重投影誤差。")

    ids = tuple(
        str(image_ids[index]) if image_ids is not None else str(index)
        for index in range(len(normalized_image_points))
    )
    per_image_errors, mean_error = calculate_reprojection_errors(
        object_points,
        normalized_image_points,
        rotation_vectors,
        translation_vectors,
        camera_matrix,
        distortion_coefficients,
        image_ids=ids,
    )
    coverage = calculate_point_coverage(
        normalized_image_points,
        normalized_image_size,
    )
    return CameraCalibrationResult(
        image_size=normalized_image_size,
        pattern_size=normalized_pattern,
        square_size_mm=normalized_square_size,
        camera_matrix=camera_matrix,
        distortion_coefficients=distortion_coefficients,
        rotation_vectors=tuple(
            np.asarray(vector, dtype=np.float64).reshape(3, 1)
            for vector in rotation_vectors
        ),
        translation_vectors=tuple(
            np.asarray(vector, dtype=np.float64).reshape(3, 1)
            for vector in translation_vectors
        ),
        rms_error=float(rms_error),
        mean_reprojection_error=mean_error,
        reprojection_error_per_image=tuple(per_image_errors),
        point_coverage=coverage,
        image_ids=ids,
        total_image_count=(
            total_image_count if total_image_count is not None else len(image_points)
        ),
        successful_image_count=len(image_points),
    )


def calibrate_fisheye_camera_from_points(
    image_points: Sequence[Any],
    image_size: Sequence[int],
    pattern_size: Sequence[int],
    square_size_mm: SquareSize,
    *,
    image_ids: Sequence[str] | None = None,
    total_image_count: int | None = None,
    initial_camera_matrix: Any | None = None,
) -> CameraCalibrationResult:
    """Calibrate the OpenCV fisheye model from the same detected corners."""

    normalized_pattern = normalize_pattern_size(pattern_size)
    normalized_square_size = normalize_square_size_mm(square_size_mm)
    normalized_image_size = validate_image_size(image_size)
    expected_count = normalized_pattern[0] * normalized_pattern[1]
    if not image_points:
        raise ValueError("至少需要一組已偵測的棋盤角點。")
    if image_ids is not None and len(image_ids) != len(image_points):
        raise ValueError("image_ids 數量必須與角點組數一致。")
    points = [
        normalize_image_points(
            value,
            name=f"image_points[{index}]",
            expected_count=expected_count,
        ).astype(np.float64)
        for index, value in enumerate(image_points)
    ]
    object_template = create_chessboard_object_points(
        normalized_pattern,
        normalized_square_size,
    ).astype(np.float64).reshape(-1, 1, 3)
    objects = [object_template.copy() for _ in points]
    camera_matrix = (
        validate_camera_matrix(
            initial_camera_matrix,
            name="initial_camera_matrix",
        ).copy()
        if initial_camera_matrix is not None
        else np.eye(3, dtype=np.float64)
    )
    distortion = np.zeros((4, 1), dtype=np.float64)
    try:
        (
            rms_error,
            camera_matrix,
            distortion,
            rotation_vectors,
            translation_vectors,
        ) = cv2.fisheye.calibrate(
            objects,
            points,
            normalized_image_size,
            camera_matrix,
            distortion,
            flags=(
                FISHEYE_CALIB_RECOMPUTE_EXTRINSIC
                | FISHEYE_CALIB_CHECK_COND
                | FISHEYE_CALIB_FIX_SKEW
                | (
                    FISHEYE_CALIB_USE_INTRINSIC_GUESS
                    if initial_camera_matrix is not None
                    else 0
                )
            ),
            criteria=DEFAULT_CALIBRATION_CRITERIA,
        )
    except cv2.error as error:
        raise ValueError(f"Fisheye 單目相機校正失敗：{error}") from error
    camera_matrix = validate_camera_matrix(
        camera_matrix,
        name="fisheye_camera_matrix",
    )
    distortion = np.asarray(distortion, dtype=np.float64).reshape(4, 1)
    if not np.isfinite(distortion).all() or not np.isfinite(rms_error):
        raise ValueError("Fisheye 單目校正產生無效數值。")
    ids = tuple(
        str(image_ids[index]) if image_ids is not None else str(index)
        for index in range(len(points))
    )
    per_image = []
    squared_error_sum = 0.0
    point_count = 0
    for index, observed in enumerate(points):
        projected, _ = cv2.fisheye.projectPoints(
            objects[index],
            np.asarray(rotation_vectors[index], dtype=np.float64),
            np.asarray(translation_vectors[index], dtype=np.float64),
            camera_matrix,
            distortion,
        )
        delta = projected.reshape(-1, 2) - observed.reshape(-1, 2)
        squared = np.sum(delta * delta, axis=1)
        per_image.append({
            "image_id": ids[index],
            "point_count": int(len(squared)),
            "rms_error_px": float(np.sqrt(np.mean(squared))),
            "max_error_px": float(np.sqrt(np.max(squared))),
        })
        squared_error_sum += float(np.sum(squared))
        point_count += len(squared)
    return CameraCalibrationResult(
        image_size=normalized_image_size,
        pattern_size=normalized_pattern,
        square_size_mm=normalized_square_size,
        camera_matrix=camera_matrix,
        distortion_coefficients=distortion,
        rotation_vectors=tuple(
            np.asarray(value, dtype=np.float64).reshape(3, 1)
            for value in rotation_vectors
        ),
        translation_vectors=tuple(
            np.asarray(value, dtype=np.float64).reshape(3, 1)
            for value in translation_vectors
        ),
        rms_error=float(rms_error),
        mean_reprojection_error=float(
            np.sqrt(squared_error_sum / point_count)
        ),
        reprojection_error_per_image=tuple(per_image),
        point_coverage=calculate_point_coverage(points, normalized_image_size),
        image_ids=ids,
        total_image_count=(
            total_image_count
            if total_image_count is not None
            else len(points)
        ),
        successful_image_count=len(points),
        projection_model="fisheye",
    )


def compare_camera_projection_models_from_points(
    image_points: Sequence[Any],
    image_size: Sequence[int],
    pattern_size: Sequence[int],
    square_size_mm: SquareSize,
    *,
    image_ids: Sequence[str] | None = None,
    total_image_count: int | None = None,
    diagonal_fov_deg: float | None = None,
) -> tuple[dict[str, CameraCalibrationResult], dict[str, dict[str, Any]]]:
    """Evaluate Brown/pinhole and fisheye on identical observations."""

    initial_matrix = (
        camera_matrix_from_diagonal_fov(image_size, diagonal_fov_deg)
        if diagonal_fov_deg is not None
        else None
    )
    results = {
        "brown_pinhole": calibrate_camera_from_points(
            image_points,
            image_size,
            pattern_size,
            square_size_mm,
            image_ids=image_ids,
            total_image_count=total_image_count,
            initial_camera_matrix=initial_matrix,
        )
    }
    evaluations: dict[str, dict[str, Any]] = {}
    try:
        results["fisheye"] = calibrate_fisheye_camera_from_points(
            image_points,
            image_size,
            pattern_size,
            square_size_mm,
            image_ids=image_ids,
            total_image_count=total_image_count,
            initial_camera_matrix=initial_matrix,
        )
    except ValueError as error:
        evaluations["fisheye"] = {
            "available": False,
            "error": str(error),
        }
    for model, result in results.items():
        per_image = [
            float(item["rms_error_px"])
            for item in result.reprojection_error_per_image
        ]
        evaluations[model] = {
            "available": True,
            "rms_error_px": result.rms_error,
            "mean_reprojection_error_px": result.mean_reprojection_error,
            "per_image_error_std_px": float(np.std(per_image)),
            "point_coverage": result.point_coverage,
        }
    return results, evaluations


def camera_matrix_from_diagonal_fov(
    image_size: Sequence[int],
    diagonal_fov_deg: float,
) -> np.ndarray:
    """Build the hardware-informed K seed; calibration still solves actual K/D."""

    width, height = validate_image_size(image_size)
    fov = float(diagonal_fov_deg)
    if not np.isfinite(fov) or not 0.0 < fov < 180.0:
        raise ValueError("鏡頭對角視角必須介於 0 與 180 度之間。")
    diagonal = float(np.hypot(width, height))
    focal_pixels = diagonal / (2.0 * tan(radians(fov) / 2.0))
    return np.asarray([
        [focal_pixels, 0.0, (width - 1.0) / 2.0],
        [0.0, focal_pixels, (height - 1.0) / 2.0],
        [0.0, 0.0, 1.0],
    ], dtype=np.float64)


__all__ = [
    "CameraCalibrationResult",
    "ChessboardDetection",
    "calibrate_camera",
    "calibrate_camera_from_points",
    "calibrate_fisheye_camera_from_points",
    "camera_matrix_from_diagonal_fov",
    "compare_camera_projection_models_from_points",
    "create_chessboard_object_points",
    "detect_chessboard_corners",
    "distortion_coefficients_named",
]
