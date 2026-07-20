from __future__ import annotations

from collections.abc import Sequence
from statistics import median

import numpy as np


MINIMUM_INTRINSIC_SAMPLES = 8
MINIMUM_CHARUCO_CORNERS = 8
MINIMUM_CHESSBOARD_CORNERS = 12
MINIMUM_SHARPNESS = 35.0
MAXIMUM_CLIPPED_RATIO = 0.35
DUPLICATE_POSE_DISTANCE = 0.075

INTRINSIC_EXCELLENT_ERROR_PX = 0.45
INTRINSIC_ACCEPTABLE_ERROR_PX = 0.9
INTRINSIC_WARNING_ERROR_PX = 1.5
EXTRINSIC_ACCEPTABLE_ERROR_PX = 2.0
ROTATION_AXIS_ACCEPTABLE_ERROR_MM = 8.0


def frame_quality(
    gray: np.ndarray,
) -> dict[str, float | list[str]]:
    normalized = np.asarray(gray, dtype=np.uint8)
    sharpness = float(np.var(_laplacian(normalized)))
    mean_brightness = float(np.mean(normalized))
    overexposed_ratio = float(np.mean(normalized >= 248))
    underexposed_ratio = float(np.mean(normalized <= 7))
    warnings: list[str] = []
    if sharpness < MINIMUM_SHARPNESS:
        warnings.append("校正板影像過度模糊，請重新對焦或保持裝置穩定。")
    if overexposed_ratio > MAXIMUM_CLIPPED_RATIO:
        warnings.append("校正板影像過曝，請降低曝光或改善照明。")
    if underexposed_ratio > MAXIMUM_CLIPPED_RATIO:
        warnings.append("校正板影像曝光不足，請提高曝光或增加照明。")
    return {
        "sharpness": sharpness,
        "mean_brightness": mean_brightness,
        "overexposed_ratio": overexposed_ratio,
        "underexposed_ratio": underexposed_ratio,
        "warnings": warnings,
    }


def _laplacian(gray: np.ndarray) -> np.ndarray:
    import cv2

    return cv2.Laplacian(gray, cv2.CV_64F)


def pose_signature(
    points: Sequence[Sequence[float]],
    image_size: Sequence[int],
) -> list[float] | None:
    values = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if len(values) < 4:
        return None
    width, height = (float(image_size[0]), float(image_size[1]))
    center = np.mean(values, axis=0)
    normalized = values - center
    covariance = np.cov(normalized.T)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    major = eigenvectors[:, int(np.argmax(eigenvalues))]
    angle = float(np.arctan2(major[1], major[0]) / np.pi)
    area = max(1.0, float(np.ptp(values[:, 0]) * np.ptp(values[:, 1])))
    scale = float(np.sqrt(area / max(1.0, width * height)))
    anisotropy = float(
        np.sqrt(max(eigenvalues) / max(1e-9, min(eigenvalues)))
    )
    return [
        float(center[0] / width),
        float(center[1] / height),
        scale,
        angle,
        min(anisotropy, 20.0) / 20.0,
    ]


def is_duplicate_pose(
    candidate: Sequence[float] | None,
    existing: Sequence[Sequence[float] | None],
) -> bool:
    if candidate is None:
        return False
    normalized = np.asarray(candidate, dtype=np.float64)
    for value in existing:
        if value is None:
            continue
        other = np.asarray(value, dtype=np.float64)
        if other.shape == normalized.shape and float(np.linalg.norm(other - normalized)) < DUPLICATE_POSE_DISTANCE:
            return True
    return False


def sample_coverage(samples: Sequence[object]) -> dict[str, float | int | bool]:
    accepted = [sample for sample in samples if bool(getattr(sample, "accepted", False))]
    centers = [
        getattr(sample, "board_center", None)
        for sample in accepted
        if getattr(sample, "board_center", None) is not None
    ]
    scales = [
        float(getattr(sample, "board_scale"))
        for sample in accepted
        if getattr(sample, "board_scale", None) is not None
    ]
    signatures = [
        getattr(sample, "pose_signature", None)
        for sample in accepted
        if getattr(sample, "pose_signature", None) is not None
    ]
    occupied: set[tuple[int, int]] = set()
    edge_hits = 0
    for center in centers:
        x = float(center[0])
        y = float(center[1])
        occupied.add((min(2, int(x * 3)), min(2, int(y * 3))))
        if x < 0.2 or x > 0.8 or y < 0.2 or y > 0.8:
            edge_hits += 1
    diversity = 0.0
    if len(signatures) >= 2:
        values = np.asarray(signatures, dtype=np.float64)
        distances = [
            float(np.linalg.norm(values[left] - values[right]))
            for left in range(len(values))
            for right in range(left + 1, len(values))
        ]
        diversity = float(median(distances)) if distances else 0.0
    scale_span = max(scales) - min(scales) if len(scales) >= 2 else 0.0
    ready = (
        len(accepted) >= MINIMUM_INTRINSIC_SAMPLES
        and len(occupied) >= 5
        and edge_hits >= 2
        and scale_span >= 0.08
        and diversity >= 0.12
    )
    return {
        "accepted_sample_count": len(accepted),
        "grid_coverage": len(occupied) / 9.0,
        "edge_sample_count": edge_hits,
        "scale_span": scale_span,
        "pose_diversity": diversity,
        "ready": ready,
    }


def intrinsic_quality_status(
    mean_error_px: float,
    validation_error_px: float,
    coverage: dict,
) -> str:
    error = max(float(mean_error_px), float(validation_error_px))
    if error <= INTRINSIC_EXCELLENT_ERROR_PX and bool(coverage.get("ready")):
        return "excellent"
    if error <= INTRINSIC_ACCEPTABLE_ERROR_PX and bool(coverage.get("ready")):
        return "acceptable"
    if error <= INTRINSIC_WARNING_ERROR_PX:
        return "warning"
    return "failed"


def extrinsic_quality_status(
    reprojection_error_px: float,
    graph_connected: bool,
    axis_error_mm: float | None,
) -> str:
    if not graph_connected or not np.isfinite(reprojection_error_px):
        return "failed"
    if axis_error_mm is not None and axis_error_mm > ROTATION_AXIS_ACCEPTABLE_ERROR_MM:
        return "warning"
    if reprojection_error_px <= EXTRINSIC_ACCEPTABLE_ERROR_PX / 2:
        return "excellent"
    if reprojection_error_px <= EXTRINSIC_ACCEPTABLE_ERROR_PX:
        return "acceptable"
    if reprojection_error_px <= EXTRINSIC_ACCEPTABLE_ERROR_PX * 2:
        return "warning"
    return "failed"
