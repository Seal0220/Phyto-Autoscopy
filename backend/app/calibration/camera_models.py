from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median
from typing import Any

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class CameraModelResult:
    camera_model: str
    camera_matrix: np.ndarray
    distortion_coefficients: np.ndarray
    reprojection_error_px: float
    median_reprojection_error_px: float
    maximum_reprojection_error_px: float
    validation_error_px: float
    per_image_errors: tuple[dict[str, Any], ...]
    stable: bool
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "camera_model": self.camera_model,
            "camera_matrix": self.camera_matrix.astype(float).tolist(),
            "distortion_coefficients": self.distortion_coefficients.reshape(-1).astype(float).tolist(),
            "reprojection_error_px": self.reprojection_error_px,
            "median_reprojection_error_px": self.median_reprojection_error_px,
            "maximum_reprojection_error_px": self.maximum_reprojection_error_px,
            "validation_error_px": self.validation_error_px,
            "per_image_errors": list(self.per_image_errors),
            "stable": self.stable,
            "score": self.score,
        }


def _points(samples: Sequence[object]):
    object_points = [
        np.asarray(sample.object_points, dtype=np.float32).reshape(-1, 3)
        for sample in samples
    ]
    image_points = [
        np.asarray(sample.image_points, dtype=np.float32).reshape(-1, 2)
        for sample in samples
    ]
    if any(len(objects) < 6 or len(objects) != len(images) for objects, images in zip(object_points, image_points)):
        raise ValueError("校正樣本的角點資料不完整。")
    return object_points, image_points


def _calibrate_pinhole(
    objects: list[np.ndarray],
    images: list[np.ndarray],
    image_size: tuple[int, int],
    *,
    rational: bool,
):
    flags = cv2.CALIB_RATIONAL_MODEL if rational else 0
    return cv2.calibrateCamera(
        objects,
        images,
        image_size,
        None,
        None,
        flags=flags,
        criteria=(
            cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
            120,
            1e-8,
        ),
    )


def _calibrate_fisheye(
    objects: list[np.ndarray],
    images: list[np.ndarray],
    image_size: tuple[int, int],
):
    fisheye_objects = [value.astype(np.float64).reshape(-1, 1, 3) for value in objects]
    fisheye_images = [value.astype(np.float64).reshape(-1, 1, 2) for value in images]
    matrix = np.eye(3, dtype=np.float64)
    matrix[0, 0] = image_size[0] / 2.0
    matrix[1, 1] = image_size[0] / 2.0
    matrix[0, 2] = (image_size[0] - 1) / 2.0
    matrix[1, 2] = (image_size[1] - 1) / 2.0
    distortion = np.zeros((4, 1), dtype=np.float64)
    return cv2.fisheye.calibrate(
        fisheye_objects,
        fisheye_images,
        image_size,
        matrix,
        distortion,
        flags=(
            cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC
            | cv2.fisheye.CALIB_CHECK_COND
            | cv2.fisheye.CALIB_FIX_SKEW
        ),
        criteria=(
            cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
            120,
            1e-8,
        ),
    )


def _project_error(
    camera_model: str,
    objects: np.ndarray,
    images: np.ndarray,
    matrix: np.ndarray,
    distortion: np.ndarray,
) -> tuple[float, float]:
    observed = images.astype(np.float64).reshape(-1, 1, 2)
    if camera_model == "opencv_fisheye":
        undistorted = cv2.fisheye.undistortPoints(
            observed,
            matrix,
            distortion,
            P=matrix,
        )
        success, rotation, translation = cv2.solvePnP(
            objects.astype(np.float64),
            undistorted,
            matrix,
            None,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not success:
            raise ValueError("Fisheye 留出影像姿態求解失敗。")
        projected, _ = cv2.fisheye.projectPoints(
            objects.astype(np.float64).reshape(-1, 1, 3),
            rotation,
            translation,
            matrix,
            distortion,
        )
    else:
        success, rotation, translation = cv2.solvePnP(
            objects.astype(np.float64),
            observed,
            matrix,
            distortion,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not success:
            raise ValueError("留出影像姿態求解失敗。")
        projected, _ = cv2.projectPoints(
            objects.astype(np.float64),
            rotation,
            translation,
            matrix,
            distortion,
        )
    errors = np.linalg.norm(
        projected.reshape(-1, 2) - images.reshape(-1, 2),
        axis=1,
    )
    return float(np.sqrt(np.mean(errors * errors))), float(np.max(errors))


def _model_stable(
    matrix: np.ndarray,
    distortion: np.ndarray,
    image_size: tuple[int, int],
) -> bool:
    if not np.isfinite(matrix).all() or not np.isfinite(distortion).all():
        return False
    focal_values = (float(matrix[0, 0]), float(matrix[1, 1]))
    if min(focal_values) <= 0 or max(focal_values) > max(image_size) * 20:
        return False
    if abs(float(matrix[0, 2]) - image_size[0] / 2) > image_size[0]:
        return False
    if abs(float(matrix[1, 2]) - image_size[1] / 2) > image_size[1]:
        return False
    return bool(np.max(np.abs(distortion)) < 50)


def solve_camera_model(
    camera_model: str,
    samples: Sequence[object],
    image_size: tuple[int, int],
) -> CameraModelResult:
    if len(samples) < 4:
        raise ValueError("相機模型計算至少需要四張有效校正影像。")
    objects, images = _points(samples)
    holdout_count = max(1, len(samples) // 5)
    holdout_indices = set(range(len(samples) - holdout_count, len(samples)))
    train_objects = [value for index, value in enumerate(objects) if index not in holdout_indices]
    train_images = [value for index, value in enumerate(images) if index not in holdout_indices]
    try:
        if camera_model == "opencv_fisheye":
            _, matrix, distortion, _, _ = _calibrate_fisheye(
                train_objects,
                train_images,
                image_size,
            )
        else:
            _, matrix, distortion, _, _ = _calibrate_pinhole(
                train_objects,
                train_images,
                image_size,
                rational=camera_model == "opencv_rational",
            )
    except cv2.error as error:
        raise ValueError(f"{camera_model} 相機模型計算失敗：{error}") from error
    per_image: list[dict[str, Any]] = []
    training_errors: list[float] = []
    holdout_errors: list[float] = []
    maximum_errors: list[float] = []
    for index, sample in enumerate(samples):
        rms, maximum = _project_error(
            camera_model,
            objects[index],
            images[index],
            np.asarray(matrix, dtype=np.float64),
            np.asarray(distortion, dtype=np.float64),
        )
        holdout = index in holdout_indices
        (holdout_errors if holdout else training_errors).append(rms)
        maximum_errors.append(maximum)
        per_image.append({
            "sample_id": sample.sample_id,
            "rms_error_px": rms,
            "maximum_error_px": maximum,
            "holdout": holdout,
        })
    mean_error = float(np.mean(training_errors))
    validation_error = float(np.mean(holdout_errors))
    stable = _model_stable(matrix, distortion, image_size)
    parameter_penalty = len(np.asarray(distortion).reshape(-1)) * 0.005
    score = mean_error + validation_error * 1.5 + parameter_penalty
    if not stable:
        score += 1000.0
    all_rms = training_errors + holdout_errors
    return CameraModelResult(
        camera_model=camera_model,
        camera_matrix=np.asarray(matrix, dtype=np.float64),
        distortion_coefficients=np.asarray(distortion, dtype=np.float64).reshape(-1),
        reprojection_error_px=mean_error,
        median_reprojection_error_px=float(median(all_rms)),
        maximum_reprojection_error_px=float(max(maximum_errors)),
        validation_error_px=validation_error,
        per_image_errors=tuple(per_image),
        stable=stable,
        score=score,
    )


def compare_camera_models(
    samples: Sequence[object],
    image_size: tuple[int, int],
    requested_model: str,
) -> tuple[dict[str, CameraModelResult], CameraModelResult]:
    models = (
        [requested_model]
        if requested_model != "auto"
        else ["opencv", "opencv_rational", "opencv_fisheye"]
    )
    results: dict[str, CameraModelResult] = {}
    failures: list[str] = []
    for model in models:
        try:
            results[model] = solve_camera_model(model, samples, image_size)
        except ValueError as error:
            failures.append(str(error))
    if not results:
        detail = failures[0] if failures else "沒有可用的相機模型。"
        raise ValueError(f"所有相機模型均計算失敗：{detail}")
    selected = min(results.values(), key=lambda result: result.score)
    return results, selected
