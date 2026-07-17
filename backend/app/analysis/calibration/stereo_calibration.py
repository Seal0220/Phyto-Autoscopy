from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np


FISHEYE_CALIB_FIX_INTRINSIC = 1 << 8

from .calibration_quality import (
    calculate_point_coverage,
    calculate_reprojection_errors,
    normalize_image_points,
    require_matching_image_sizes,
    validate_camera_matrix,
    validate_distortion_coefficients,
    validate_finite_matrix,
    validate_image_size,
)
from .camera_calibration import (
    CalibrationImage,
    DEFAULT_CALIBRATION_CRITERIA,
    DEFAULT_CORNER_DETECTION_FLAGS,
    DISTORTION_COEFFICIENT_ORDER,
    SquareSize,
    create_chessboard_object_points,
    detect_chessboard_corners,
    distortion_coefficients_named,
    load_calibration_image,
    normalize_pattern_size,
    normalize_square_size_mm,
)


@dataclass(slots=True)
class StereoCalibrationResult:
    image_size: tuple[int, int]
    pattern_size: tuple[int, int]
    square_size_mm: tuple[float, float]
    top_camera_matrix: np.ndarray
    top_distortion_coefficients: np.ndarray
    side_camera_matrix: np.ndarray
    side_distortion_coefficients: np.ndarray
    rotation_matrix: np.ndarray
    translation_vector: np.ndarray
    essential_matrix: np.ndarray
    fundamental_matrix: np.ndarray
    top_rectification_rotation: np.ndarray
    side_rectification_rotation: np.ndarray
    top_projection_matrix: np.ndarray
    side_projection_matrix: np.ndarray
    disparity_to_depth_matrix: np.ndarray
    top_valid_pixel_roi: tuple[int, int, int, int]
    side_valid_pixel_roi: tuple[int, int, int, int]
    rms_error: float
    reprojection_error_per_pair: tuple[dict[str, float | str], ...]
    point_coverage: dict[str, dict[str, Any]]
    pair_ids: tuple[str, ...]
    total_pair_count: int
    successful_pair_count: int
    corner_detections: tuple[dict[str, Any], ...] = ()
    projection_model: str = "brown_pinhole"

    @property
    def top_distortion_named(self) -> dict[str, float]:
        if self.projection_model == "fisheye":
            return {
                name: float(self.top_distortion_coefficients.reshape(-1)[index])
                for index, name in enumerate(("k1", "k2", "k3", "k4"))
            }
        return distortion_coefficients_named(self.top_distortion_coefficients)

    @property
    def side_distortion_named(self) -> dict[str, float]:
        if self.projection_model == "fisheye":
            return {
                name: float(self.side_distortion_coefficients.reshape(-1)[index])
                for index, name in enumerate(("k1", "k2", "k3", "k4"))
            }
        return distortion_coefficients_named(self.side_distortion_coefficients)

    @property
    def stereo_mean_reprojection_error(self) -> float:
        """Expose OpenCV's global stereo RMS under the profile field name."""

        return self.rms_error

    def to_dict(self, *, include_corners: bool = True) -> dict[str, Any]:
        detections: list[dict[str, Any]] = []
        for item in self.corner_detections:
            detections.append(
                {
                    "pair_id": item["pair_id"],
                    "top": item["top"].to_dict(include_corners=include_corners),
                    "side": item["side"].to_dict(include_corners=include_corners),
                    "usable": bool(item["usable"]),
                }
            )
        return {
            "image_width": self.image_size[0],
            "image_height": self.image_size[1],
            "chessboard_pattern": list(self.pattern_size),
            "square_size_mm": list(self.square_size_mm),
            "top_camera_matrix": self.top_camera_matrix.astype(float).tolist(),
            "top_distortion_coefficients": (
                self.top_distortion_coefficients.reshape(-1).astype(float).tolist()
            ),
            "side_camera_matrix": self.side_camera_matrix.astype(float).tolist(),
            "side_distortion_coefficients": (
                self.side_distortion_coefficients.reshape(-1).astype(float).tolist()
            ),
            "projection_model": self.projection_model,
            "distortion_coefficient_order": (
                ["k1", "k2", "k3", "k4"]
                if self.projection_model == "fisheye"
                else list(DISTORTION_COEFFICIENT_ORDER)
            ),
            "top_distortion_named": self.top_distortion_named,
            "side_distortion_named": self.side_distortion_named,
            "rotation_matrix": self.rotation_matrix.astype(float).tolist(),
            "translation_vector": (
                self.translation_vector.reshape(-1).astype(float).tolist()
            ),
            "essential_matrix": self.essential_matrix.astype(float).tolist(),
            "fundamental_matrix": self.fundamental_matrix.astype(float).tolist(),
            "top_rectification_rotation": (
                self.top_rectification_rotation.astype(float).tolist()
            ),
            "side_rectification_rotation": (
                self.side_rectification_rotation.astype(float).tolist()
            ),
            "top_projection_matrix": (
                self.top_projection_matrix.astype(float).tolist()
            ),
            "side_projection_matrix": (
                self.side_projection_matrix.astype(float).tolist()
            ),
            "disparity_to_depth_matrix": (
                self.disparity_to_depth_matrix.astype(float).tolist()
            ),
            "top_valid_pixel_roi": list(self.top_valid_pixel_roi),
            "side_valid_pixel_roi": list(self.side_valid_pixel_roi),
            "rms_error": self.rms_error,
            "stereo_mean_reprojection_error": self.stereo_mean_reprojection_error,
            "reprojection_error_per_pair": list(self.reprojection_error_per_pair),
            "point_coverage": self.point_coverage,
            "pair_ids": list(self.pair_ids),
            "total_pair_count": self.total_pair_count,
            "successful_pair_count": self.successful_pair_count,
            "corner_detections": detections,
        }


def compute_epipolar_lines(
    points: Any,
    fundamental_matrix: Any,
    *,
    source_image: int,
) -> np.ndarray:
    """Compute corresponding lines in the other image.

    ``source_image`` follows OpenCV: use ``1`` for top-image points and ``2``
    for side-image points.
    """

    if source_image not in (1, 2):
        raise ValueError("source_image 只能是 1（頂視）或 2（側視）。")
    normalized_points = normalize_image_points(points, name="points")
    fundamental = validate_finite_matrix(
        fundamental_matrix,
        name="fundamental_matrix",
        shape=(3, 3),
    )
    lines = cv2.computeCorrespondEpilines(
        normalized_points,
        source_image,
        fundamental,
    )
    normalized_lines = validate_finite_matrix(
        lines,
        name="epipolar_lines",
    ).reshape(-1, 3)
    return normalized_lines


def calculate_epipolar_rms_error(
    top_points: Any,
    side_points: Any,
    fundamental_matrix: Any,
) -> float:
    """Calculate symmetric point-to-epipolar-line RMS distance in pixels."""

    top = normalize_image_points(top_points, name="top_points").reshape(-1, 2)
    side = normalize_image_points(
        side_points,
        name="side_points",
        expected_count=len(top),
    ).reshape(-1, 2)
    side_lines = compute_epipolar_lines(
        top,
        fundamental_matrix,
        source_image=1,
    )
    top_lines = compute_epipolar_lines(
        side,
        fundamental_matrix,
        source_image=2,
    )

    def point_line_distances(points: np.ndarray, lines: np.ndarray) -> np.ndarray:
        numerator = np.abs(
            lines[:, 0] * points[:, 0]
            + lines[:, 1] * points[:, 1]
            + lines[:, 2]
        )
        denominator = np.sqrt(lines[:, 0] ** 2 + lines[:, 1] ** 2)
        if np.any(denominator <= np.finfo(np.float64).eps):
            raise ValueError("基礎矩陣產生無效的極線。")
        return numerator / denominator

    top_distances = point_line_distances(top, top_lines)
    side_distances = point_line_distances(side, side_lines)
    squared = np.concatenate((top_distances**2, side_distances**2))
    return float(np.sqrt(np.mean(squared)))


def calibrate_stereo(
    top_images: Sequence[CalibrationImage],
    side_images: Sequence[CalibrationImage],
    pattern_size: Sequence[int],
    square_size_mm: SquareSize,
    top_camera_matrix: Any,
    top_distortion_coefficients: Any,
    side_camera_matrix: Any,
    side_distortion_coefficients: Any,
    *,
    pair_ids: Sequence[str] | None = None,
    corner_flags: int = DEFAULT_CORNER_DETECTION_FLAGS,
    calibration_flags: int = cv2.CALIB_FIX_INTRINSIC,
    criteria: tuple[int, int, float] = DEFAULT_CALIBRATION_CRITERIA,
    rectify_flags: int = cv2.CALIB_ZERO_DISPARITY,
    rectify_alpha: float = -1.0,
) -> StereoCalibrationResult:
    """Detect paired corners and calibrate the top/side stereo cameras."""

    if not top_images or not side_images:
        raise ValueError("至少需要一組頂視與側視雙目校正影像。")
    if len(top_images) != len(side_images):
        raise ValueError("頂視與側視雙目校正影像數量必須一致。")
    if pair_ids is not None and len(pair_ids) != len(top_images):
        raise ValueError("pair_ids 數量必須與雙目校正影像組數一致。")

    normalized_pattern = normalize_pattern_size(pattern_size)
    normalized_square_size = normalize_square_size_mm(square_size_mm)
    top_loaded = [load_calibration_image(image) for image in top_images]
    side_loaded = [load_calibration_image(image) for image in side_images]
    ids = tuple(
        str(pair_ids[index]) if pair_ids is not None else str(index)
        for index in range(len(top_images))
    )
    image_size = require_matching_image_sizes(
        [
            *((image.shape[1], image.shape[0]) for image in top_loaded),
            *((image.shape[1], image.shape[0]) for image in side_loaded),
        ],
        names=[
            *(f"{pair_id}:top" for pair_id in ids),
            *(f"{pair_id}:side" for pair_id in ids),
        ],
    )

    detections: list[dict[str, Any]] = []
    top_points: list[np.ndarray] = []
    side_points: list[np.ndarray] = []
    successful_ids: list[str] = []
    for index, pair_id in enumerate(ids):
        top_detection = detect_chessboard_corners(
            top_loaded[index],
            normalized_pattern,
            image_id=f"{pair_id}:top",
            flags=corner_flags,
        )
        side_detection = detect_chessboard_corners(
            side_loaded[index],
            normalized_pattern,
            image_id=f"{pair_id}:side",
            flags=corner_flags,
        )
        usable = top_detection.found and side_detection.found
        detections.append(
            {
                "pair_id": pair_id,
                "top": top_detection,
                "side": side_detection,
                "usable": usable,
            }
        )
        if usable:
            top_points.append(top_detection.corners)
            side_points.append(side_detection.corners)
            successful_ids.append(pair_id)

    if not successful_ids:
        raise ValueError("沒有任一組雙目影像同時偵測到棋盤角點。")

    result = calibrate_stereo_from_points(
        top_points,
        side_points,
        image_size,
        image_size,
        normalized_pattern,
        normalized_square_size,
        top_camera_matrix,
        top_distortion_coefficients,
        side_camera_matrix,
        side_distortion_coefficients,
        pair_ids=successful_ids,
        calibration_flags=calibration_flags,
        criteria=criteria,
        rectify_flags=rectify_flags,
        rectify_alpha=rectify_alpha,
        total_pair_count=len(ids),
    )
    result.corner_detections = tuple(detections)
    return result


def calibrate_stereo_from_points(
    top_image_points: Sequence[Any],
    side_image_points: Sequence[Any],
    top_image_size: Sequence[int],
    side_image_size: Sequence[int],
    pattern_size: Sequence[int],
    square_size_mm: SquareSize,
    top_camera_matrix: Any,
    top_distortion_coefficients: Any,
    side_camera_matrix: Any,
    side_distortion_coefficients: Any,
    *,
    pair_ids: Sequence[str] | None = None,
    calibration_flags: int = cv2.CALIB_FIX_INTRINSIC,
    criteria: tuple[int, int, float] = DEFAULT_CALIBRATION_CRITERIA,
    rectify_flags: int = cv2.CALIB_ZERO_DISPARITY,
    rectify_alpha: float = -1.0,
    total_pair_count: int | None = None,
    projection_model: str = "brown_pinhole",
) -> StereoCalibrationResult:
    """Calibrate stereo geometry from paired, precomputed chessboard corners."""

    normalized_top_size = validate_image_size(
        top_image_size,
        name="top_image_size",
    )
    normalized_side_size = validate_image_size(
        side_image_size,
        name="side_image_size",
    )
    image_size = require_matching_image_sizes(
        [normalized_top_size, normalized_side_size],
        names=["top_image_size", "side_image_size"],
    )
    normalized_pattern = normalize_pattern_size(pattern_size)
    normalized_square_size = normalize_square_size_mm(square_size_mm)
    pair_count = len(top_image_points)
    if pair_count == 0:
        raise ValueError("至少需要一組已偵測的雙目棋盤角點。")
    if len(side_image_points) != pair_count:
        raise ValueError("頂視與側視角點組數必須一致。")
    if pair_ids is not None and len(pair_ids) != pair_count:
        raise ValueError("pair_ids 數量必須與雙目角點組數一致。")
    if total_pair_count is not None and total_pair_count < pair_count:
        raise ValueError("total_pair_count 不得小於成功雙目角點組數。")

    expected_corner_count = normalized_pattern[0] * normalized_pattern[1]
    top_points = [
        normalize_image_points(
            points,
            name=f"top_image_points[{index}]",
            expected_count=expected_corner_count,
        )
        for index, points in enumerate(top_image_points)
    ]
    side_points = [
        normalize_image_points(
            points,
            name=f"side_image_points[{index}]",
            expected_count=expected_corner_count,
        )
        for index, points in enumerate(side_image_points)
    ]
    object_template = create_chessboard_object_points(
        normalized_pattern,
        normalized_square_size,
    )
    object_points = [object_template.copy() for _ in range(pair_count)]

    top_matrix = validate_camera_matrix(
        top_camera_matrix,
        name="top_camera_matrix",
    ).copy()
    side_matrix = validate_camera_matrix(
        side_camera_matrix,
        name="side_camera_matrix",
    ).copy()
    if projection_model not in {"brown_pinhole", "fisheye"}:
        raise ValueError("雙目投影模型只能是 brown_pinhole 或 fisheye。")
    fisheye = projection_model == "fisheye"
    if fisheye:
        top_distortion = np.asarray(
            top_distortion_coefficients,
            dtype=np.float64,
        ).reshape(-1, 1)
        side_distortion = np.asarray(
            side_distortion_coefficients,
            dtype=np.float64,
        ).reshape(-1, 1)
        if (
            top_distortion.shape != (4, 1)
            or side_distortion.shape != (4, 1)
            or not np.isfinite(top_distortion).all()
            or not np.isfinite(side_distortion).all()
        ):
            raise ValueError("Fisheye 雙目畸變係數必須各包含四個有效數值。")
    else:
        top_distortion = validate_distortion_coefficients(
            top_distortion_coefficients,
            name="top_distortion_coefficients",
        ).copy()
        side_distortion = validate_distortion_coefficients(
            side_distortion_coefficients,
            name="side_distortion_coefficients",
        ).copy()

    try:
        if fisheye:
            fisheye_objects = [
                value.astype(np.float64).reshape(-1, 1, 3)
                for value in object_points
            ]
            fisheye_top = [value.astype(np.float64) for value in top_points]
            fisheye_side = [value.astype(np.float64) for value in side_points]
            fisheye_result = cv2.fisheye.stereoCalibrate(
                fisheye_objects,
                fisheye_top,
                fisheye_side,
                top_matrix,
                top_distortion,
                side_matrix,
                side_distortion,
                image_size,
                flags=FISHEYE_CALIB_FIX_INTRINSIC,
                criteria=criteria,
            )
            (
                rms_error,
                top_matrix,
                top_distortion,
                side_matrix,
                side_distortion,
                rotation_matrix,
                translation_vector,
                *_optional_extrinsics,
            ) = fisheye_result
            essential_matrix = (
                np.asarray([
                    [0.0, -translation_vector[2, 0], translation_vector[1, 0]],
                    [translation_vector[2, 0], 0.0, -translation_vector[0, 0]],
                    [-translation_vector[1, 0], translation_vector[0, 0], 0.0],
                ])
                @ rotation_matrix
            )
            fundamental_matrix = (
                np.linalg.inv(side_matrix).T
                @ essential_matrix
                @ np.linalg.inv(top_matrix)
            )
        else:
            (
                rms_error,
                top_matrix,
                top_distortion,
                side_matrix,
                side_distortion,
                rotation_matrix,
                translation_vector,
                essential_matrix,
                fundamental_matrix,
            ) = cv2.stereoCalibrate(
                object_points,
                top_points,
                side_points,
                top_matrix,
                top_distortion,
                side_matrix,
                side_distortion,
                image_size,
                criteria=criteria,
                flags=calibration_flags,
            )
    except cv2.error as error:
        raise ValueError(f"雙目相機校正失敗：{error}") from error

    top_matrix = validate_camera_matrix(top_matrix, name="top_camera_matrix")
    side_matrix = validate_camera_matrix(side_matrix, name="side_camera_matrix")
    if fisheye:
        top_distortion = np.asarray(top_distortion, dtype=np.float64).reshape(4, 1)
        side_distortion = np.asarray(side_distortion, dtype=np.float64).reshape(4, 1)
    else:
        top_distortion = validate_distortion_coefficients(
            top_distortion,
            name="top_distortion_coefficients",
        )
        side_distortion = validate_distortion_coefficients(
            side_distortion,
            name="side_distortion_coefficients",
        )
    rotation_matrix = validate_finite_matrix(
        rotation_matrix,
        name="rotation_matrix",
        shape=(3, 3),
    )
    translation_vector = validate_finite_matrix(
        translation_vector,
        name="translation_vector",
    ).reshape(3, 1)
    essential_matrix = validate_finite_matrix(
        essential_matrix,
        name="essential_matrix",
        shape=(3, 3),
    )
    fundamental_matrix = validate_finite_matrix(
        fundamental_matrix,
        name="fundamental_matrix",
        shape=(3, 3),
    )
    if not np.isfinite(rms_error):
        raise ValueError("雙目校正產生無效的 RMS 重投影誤差。")

    try:
        if fisheye:
            (
                top_rectification,
                side_rectification,
                top_projection,
                side_projection,
                disparity_to_depth,
            ) = cv2.fisheye.stereoRectify(
                top_matrix,
                top_distortion,
                side_matrix,
                side_distortion,
                image_size,
                rotation_matrix,
                translation_vector,
                flags=rectify_flags,
                newImageSize=image_size,
                balance=0.0,
                fov_scale=1.0,
            )
            top_roi = (0, 0, image_size[0], image_size[1])
            side_roi = top_roi
        else:
            (
                top_rectification,
                side_rectification,
                top_projection,
                side_projection,
                disparity_to_depth,
                top_roi,
                side_roi,
            ) = cv2.stereoRectify(
                top_matrix,
                top_distortion,
                side_matrix,
                side_distortion,
                image_size,
                rotation_matrix,
                translation_vector,
                flags=rectify_flags,
                alpha=rectify_alpha,
            )
    except cv2.error as error:
        raise ValueError(f"雙目影像矯正參數計算失敗：{error}") from error

    top_rectification = validate_finite_matrix(
        top_rectification,
        name="top_rectification_rotation",
        shape=(3, 3),
    )
    side_rectification = validate_finite_matrix(
        side_rectification,
        name="side_rectification_rotation",
        shape=(3, 3),
    )
    top_projection = validate_finite_matrix(
        top_projection,
        name="top_projection_matrix",
        shape=(3, 4),
    )
    side_projection = validate_finite_matrix(
        side_projection,
        name="side_projection_matrix",
        shape=(3, 4),
    )
    disparity_to_depth = validate_finite_matrix(
        disparity_to_depth,
        name="disparity_to_depth_matrix",
        shape=(4, 4),
    )

    ids = tuple(
        str(pair_ids[index]) if pair_ids is not None else str(index)
        for index in range(pair_count)
    )
    per_pair_errors = _calculate_stereo_pair_errors(
        object_points,
        top_points,
        side_points,
        top_matrix,
        top_distortion,
        side_matrix,
        side_distortion,
        fundamental_matrix,
        ids,
        projection_model=projection_model,
    )
    return StereoCalibrationResult(
        image_size=image_size,
        pattern_size=normalized_pattern,
        square_size_mm=normalized_square_size,
        top_camera_matrix=top_matrix,
        top_distortion_coefficients=top_distortion,
        side_camera_matrix=side_matrix,
        side_distortion_coefficients=side_distortion,
        rotation_matrix=rotation_matrix,
        translation_vector=translation_vector,
        essential_matrix=essential_matrix,
        fundamental_matrix=fundamental_matrix,
        top_rectification_rotation=top_rectification,
        side_rectification_rotation=side_rectification,
        top_projection_matrix=top_projection,
        side_projection_matrix=side_projection,
        disparity_to_depth_matrix=disparity_to_depth,
        top_valid_pixel_roi=tuple(int(value) for value in top_roi),
        side_valid_pixel_roi=tuple(int(value) for value in side_roi),
        rms_error=float(rms_error),
        reprojection_error_per_pair=tuple(per_pair_errors),
        point_coverage={
            "top": calculate_point_coverage(top_points, image_size),
            "side": calculate_point_coverage(side_points, image_size),
        },
        pair_ids=ids,
        total_pair_count=(
            total_pair_count if total_pair_count is not None else pair_count
        ),
        successful_pair_count=pair_count,
        projection_model=projection_model,
    )


def _calculate_stereo_pair_errors(
    object_points: Sequence[np.ndarray],
    top_points: Sequence[np.ndarray],
    side_points: Sequence[np.ndarray],
    top_camera_matrix: np.ndarray,
    top_distortion_coefficients: np.ndarray,
    side_camera_matrix: np.ndarray,
    side_distortion_coefficients: np.ndarray,
    fundamental_matrix: np.ndarray,
    pair_ids: Sequence[str],
    *,
    projection_model: str = "brown_pinhole",
) -> list[dict[str, float | str]]:
    results: list[dict[str, float | str]] = []
    for index, pair_id in enumerate(pair_ids):
        fisheye = projection_model == "fisheye"
        top_observed = (
            cv2.fisheye.undistortPoints(
                top_points[index].astype(np.float64),
                top_camera_matrix,
                top_distortion_coefficients,
                P=top_camera_matrix,
            )
            if fisheye
            else top_points[index]
        )
        side_observed = (
            cv2.fisheye.undistortPoints(
                side_points[index].astype(np.float64),
                side_camera_matrix,
                side_distortion_coefficients,
                P=side_camera_matrix,
            )
            if fisheye
            else side_points[index]
        )
        top_success, top_rotation, top_translation = cv2.solvePnP(
            object_points[index],
            top_observed,
            top_camera_matrix,
            None if fisheye else top_distortion_coefficients,
        )
        side_success, side_rotation, side_translation = cv2.solvePnP(
            object_points[index],
            side_observed,
            side_camera_matrix,
            None if fisheye else side_distortion_coefficients,
        )
        if not top_success or not side_success:
            raise ValueError(f"雙目校正組 {pair_id} 無法求得校正物件姿態。")

        if fisheye:
            top_projected, _ = cv2.fisheye.projectPoints(
                object_points[index].astype(np.float64).reshape(-1, 1, 3),
                top_rotation,
                top_translation,
                top_camera_matrix,
                top_distortion_coefficients,
            )
            side_projected, _ = cv2.fisheye.projectPoints(
                object_points[index].astype(np.float64).reshape(-1, 1, 3),
                side_rotation,
                side_translation,
                side_camera_matrix,
                side_distortion_coefficients,
            )
            top_error = float(np.sqrt(np.mean(np.sum(
                (
                    top_projected.reshape(-1, 2)
                    - top_points[index].reshape(-1, 2)
                ) ** 2,
                axis=1,
            ))))
            side_error = float(np.sqrt(np.mean(np.sum(
                (
                    side_projected.reshape(-1, 2)
                    - side_points[index].reshape(-1, 2)
                ) ** 2,
                axis=1,
            ))))
        else:
            _, top_error = calculate_reprojection_errors(
                [object_points[index]],
                [top_points[index]],
                [top_rotation],
                [top_translation],
                top_camera_matrix,
                top_distortion_coefficients,
                image_ids=[pair_id],
            )
            _, side_error = calculate_reprojection_errors(
                [object_points[index]],
                [side_points[index]],
                [side_rotation],
                [side_translation],
                side_camera_matrix,
                side_distortion_coefficients,
                image_ids=[pair_id],
            )
        results.append(
            {
                "pair_id": pair_id,
                "top_rms_error_px": top_error,
                "side_rms_error_px": side_error,
                "combined_rms_error_px": float(
                    np.sqrt((top_error**2 + side_error**2) / 2.0)
                ),
                "epipolar_rms_error_px": calculate_epipolar_rms_error(
                    top_observed,
                    side_observed,
                    fundamental_matrix,
                ),
            }
        )
    return results
