from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from app.models.calibration_models import CameraIntrinsics


def _adapt_camera_matrix(
    camera_matrix: list[list[float]],
    calibration_size: tuple[int, int],
    analysis_size: tuple[int, int],
) -> np.ndarray:
    calibration_width, calibration_height = calibration_size
    analysis_width, analysis_height = analysis_size
    if analysis_width * calibration_height != analysis_height * calibration_width:
        raise ValueError("分析影像與內參校正影像的長寬比不相容。")
    scale_x = analysis_width / calibration_width
    scale_y = analysis_height / calibration_height
    matrix = np.asarray(camera_matrix, dtype=np.float64).copy()
    matrix[0, 0] *= scale_x
    matrix[0, 2] *= scale_x
    matrix[1, 1] *= scale_y
    matrix[1, 2] *= scale_y
    return matrix


def build_intrinsics_snapshot(
    intrinsics: CameraIntrinsics,
    analysis_size: tuple[int, int],
    *,
    balance: float = 0.0,
) -> dict[str, Any]:
    width, height = analysis_size
    adapted = _adapt_camera_matrix(
        intrinsics.camera_matrix,
        (intrinsics.width, intrinsics.height),
        analysis_size,
    )
    distortion = np.asarray(
        intrinsics.distortion_coefficients,
        dtype=np.float64,
    ).reshape(-1, 1)
    if intrinsics.camera_model == "opencv_fisheye":
        undistorted = cv2.fisheye.estimateNewCameraMatrixForUndistortRectify(
            adapted,
            distortion,
            (width, height),
            np.eye(3, dtype=np.float64),
            balance=float(balance),
        )
    else:
        undistorted, _ = cv2.getOptimalNewCameraMatrix(
            adapted,
            distortion,
            (width, height),
            0,
            (width, height),
        )
    return {
        **intrinsics.model_dump(mode="json"),
        "calibration_image_width": intrinsics.width,
        "calibration_image_height": intrinsics.height,
        "analysis_image_width": width,
        "analysis_image_height": height,
        "adapted_camera_matrix": adapted.astype(float).tolist(),
        "undistorted_camera_matrix": undistorted.astype(float).tolist(),
        "calibration_reprojection_error_px": intrinsics.reprojection_error_px,
        "intrinsics_created_at": intrinsics.created_at,
        "intrinsics_updated_at": intrinsics.updated_at,
        "intrinsics_version": intrinsics.source_run_id,
        "undistortion_balance": float(balance),
    }
