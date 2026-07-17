from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import cv2
import numpy as np


def validate_image_size(
    image_size: Sequence[int],
    *,
    name: str = "image_size",
) -> tuple[int, int]:
    """Validate and normalize an OpenCV ``(width, height)`` image size."""

    if len(image_size) != 2:
        raise ValueError(f"{name} 必須是 (width, height)。")

    width, height = (int(value) for value in image_size)
    if width <= 0 or height <= 0:
        raise ValueError(f"{name} 的寬度與高度必須大於 0。")
    return width, height


def require_matching_image_sizes(
    image_sizes: Sequence[Sequence[int]],
    *,
    names: Sequence[str] | None = None,
) -> tuple[int, int]:
    """Require every calibration image to use one identical resolution."""

    if not image_sizes:
        raise ValueError("至少需要一組影像解析度。")
    if names is not None and len(names) != len(image_sizes):
        raise ValueError("names 數量必須與影像解析度數量一致。")

    normalized = [
        validate_image_size(
            image_size,
            name=names[index] if names is not None else f"image_sizes[{index}]",
        )
        for index, image_size in enumerate(image_sizes)
    ]
    expected = normalized[0]
    for index, image_size in enumerate(normalized[1:], start=1):
        if image_size != expected:
            source_name = names[index] if names is not None else f"image_sizes[{index}]"
            raise ValueError(
                f"校正影像解析度不一致：{source_name} 為 {image_size[0]}×{image_size[1]}，"
                f"預期為 {expected[0]}×{expected[1]}。"
            )
    return expected


def validate_finite_matrix(
    matrix: Any,
    *,
    name: str,
    shape: tuple[int, ...] | None = None,
) -> np.ndarray:
    """Return a float64 matrix after checking shape and finite values."""

    normalized = np.asarray(matrix, dtype=np.float64)
    if shape is not None and normalized.shape != shape:
        raise ValueError(
            f"{name} 形狀必須為 {shape}，實際為 {normalized.shape}。"
        )
    if normalized.size == 0:
        raise ValueError(f"{name} 不得為空。")
    if not np.isfinite(normalized).all():
        raise ValueError(f"{name} 包含 NaN 或無限大數值。")
    return normalized


def validate_camera_matrix(camera_matrix: Any, *, name: str) -> np.ndarray:
    matrix = validate_finite_matrix(
        camera_matrix,
        name=name,
        shape=(3, 3),
    )
    if matrix[0, 0] <= 0 or matrix[1, 1] <= 0:
        raise ValueError(f"{name} 的焦距必須大於 0。")
    if not np.isclose(matrix[2, 2], 1.0):
        raise ValueError(f"{name}[2, 2] 必須為 1。")
    return matrix


def validate_distortion_coefficients(
    coefficients: Any,
    *,
    name: str,
) -> np.ndarray:
    normalized = validate_finite_matrix(coefficients, name=name).reshape(-1)
    if normalized.size < 5:
        raise ValueError(
            f"{name} 至少需要 OpenCV 的 k1、k2、p1、p2、k3 五個係數。"
        )
    return normalized


def normalize_image_points(
    points: Any,
    *,
    name: str,
    expected_count: int | None = None,
) -> np.ndarray:
    """Normalize image points to OpenCV's ``(N, 1, 2)`` float32 format."""

    normalized = np.asarray(points, dtype=np.float32)
    if normalized.ndim == 3 and normalized.shape[1:] == (1, 2):
        pass
    elif normalized.ndim == 2 and normalized.shape[1] == 2:
        normalized = normalized.reshape(-1, 1, 2)
    else:
        raise ValueError(f"{name} 形狀必須為 (N, 2) 或 (N, 1, 2)。")

    if expected_count is not None and normalized.shape[0] != expected_count:
        raise ValueError(
            f"{name} 應包含 {expected_count} 個角點，"
            f"實際為 {normalized.shape[0]} 個。"
        )
    if not np.isfinite(normalized).all():
        raise ValueError(f"{name} 包含 NaN 或無限大數值。")
    return normalized


def normalize_object_points(
    points: Any,
    *,
    name: str,
    expected_count: int | None = None,
) -> np.ndarray:
    """Normalize object points to OpenCV's ``(N, 3)`` float32 format."""

    normalized = np.asarray(points, dtype=np.float32)
    if normalized.ndim == 3 and normalized.shape[1:] == (1, 3):
        normalized = normalized.reshape(-1, 3)
    if normalized.ndim != 2 or normalized.shape[1] != 3:
        raise ValueError(f"{name} 形狀必須為 (N, 3) 或 (N, 1, 3)。")
    if expected_count is not None and normalized.shape[0] != expected_count:
        raise ValueError(
            f"{name} 應包含 {expected_count} 個三維點，"
            f"實際為 {normalized.shape[0]} 個。"
        )
    if not np.isfinite(normalized).all():
        raise ValueError(f"{name} 包含 NaN 或無限大數值。")
    return normalized


def calculate_reprojection_errors(
    object_points: Sequence[Any],
    image_points: Sequence[Any],
    rotation_vectors: Sequence[Any],
    translation_vectors: Sequence[Any],
    camera_matrix: Any,
    distortion_coefficients: Any,
    *,
    image_ids: Sequence[str] | None = None,
) -> tuple[list[dict[str, float | int | str]], float]:
    """Calculate per-image and global RMS reprojection errors in pixels."""

    item_count = len(object_points)
    if item_count == 0:
        raise ValueError("無法從空的角點集合計算重投影誤差。")
    if not (
        len(image_points)
        == len(rotation_vectors)
        == len(translation_vectors)
        == item_count
    ):
        raise ValueError("物件點、影像點與外參組數必須一致。")
    if image_ids is not None and len(image_ids) != item_count:
        raise ValueError("image_ids 數量必須與校正影像數量一致。")

    matrix = validate_camera_matrix(camera_matrix, name="camera_matrix")
    distortion = validate_distortion_coefficients(
        distortion_coefficients,
        name="distortion_coefficients",
    )
    per_image: list[dict[str, float | int | str]] = []
    squared_error_sum = 0.0
    point_count = 0

    for index in range(item_count):
        object_point_set = normalize_object_points(
            object_points[index],
            name=f"object_points[{index}]",
        )
        observed = normalize_image_points(
            image_points[index],
            name=f"image_points[{index}]",
            expected_count=object_point_set.shape[0],
        )
        rotation = validate_finite_matrix(
            rotation_vectors[index],
            name=f"rotation_vectors[{index}]",
        ).reshape(3, 1)
        translation = validate_finite_matrix(
            translation_vectors[index],
            name=f"translation_vectors[{index}]",
        ).reshape(3, 1)
        projected, _ = cv2.projectPoints(
            object_point_set,
            rotation,
            translation,
            matrix,
            distortion,
        )
        delta = projected.reshape(-1, 2) - observed.reshape(-1, 2)
        squared_errors = np.sum(delta.astype(np.float64) ** 2, axis=1)
        image_squared_sum = float(np.sum(squared_errors))
        rms_error = float(np.sqrt(image_squared_sum / len(squared_errors)))
        maximum_error = float(np.sqrt(np.max(squared_errors)))
        per_image.append(
            {
                "image_id": image_ids[index] if image_ids is not None else str(index),
                "point_count": int(len(squared_errors)),
                "rms_error_px": rms_error,
                "max_error_px": maximum_error,
            }
        )
        squared_error_sum += image_squared_sum
        point_count += len(squared_errors)

    mean_error = float(np.sqrt(squared_error_sum / point_count))
    return per_image, mean_error


def calculate_point_coverage(
    image_points: Sequence[Any],
    image_size: Sequence[int],
    *,
    grid_size: tuple[int, int] = (4, 4),
) -> dict[str, Any]:
    """Describe how calibration points cover the sensor image.

    The report includes an aggregate convex-hull area, bounding-box span and grid
    occupancy. These are descriptive measurements; no unverified pass/fail
    threshold is imposed here.
    """

    width, height = validate_image_size(image_size)
    grid_columns, grid_rows = grid_size
    if grid_columns <= 0 or grid_rows <= 0:
        raise ValueError("grid_size 的欄數與列數必須大於 0。")
    if not image_points:
        raise ValueError("校正點為空，無法計算空間覆蓋。")

    normalized_sets = [
        normalize_image_points(points, name=f"image_points[{index}]").reshape(-1, 2)
        for index, points in enumerate(image_points)
    ]
    all_points = np.concatenate(normalized_sets, axis=0).astype(np.float32)
    if (
        np.any(all_points[:, 0] < 0)
        or np.any(all_points[:, 0] >= width)
        or np.any(all_points[:, 1] < 0)
        or np.any(all_points[:, 1] >= height)
    ):
        raise ValueError("校正點必須位於影像範圍內。")

    minimum = np.min(all_points, axis=0)
    maximum = np.max(all_points, axis=0)
    span_x = float((maximum[0] - minimum[0]) / width)
    span_y = float((maximum[1] - minimum[1]) / height)
    bounding_box_ratio = span_x * span_y

    hull = cv2.convexHull(all_points.reshape(-1, 1, 2))
    hull_area = float(cv2.contourArea(hull)) if len(hull) >= 3 else 0.0
    convex_hull_ratio = hull_area / float(width * height)

    occupied_cells: set[tuple[int, int]] = set()
    for x_coordinate, y_coordinate in all_points:
        column = min(int(x_coordinate / width * grid_columns), grid_columns - 1)
        row = min(int(y_coordinate / height * grid_rows), grid_rows - 1)
        occupied_cells.add((column, row))
    total_cells = grid_columns * grid_rows

    per_image: list[dict[str, Any]] = []
    for index, points in enumerate(normalized_sets):
        image_minimum = np.min(points, axis=0)
        image_maximum = np.max(points, axis=0)
        image_span_x = float((image_maximum[0] - image_minimum[0]) / width)
        image_span_y = float((image_maximum[1] - image_minimum[1]) / height)
        per_image.append(
            {
                "image_index": index,
                "point_count": int(points.shape[0]),
                "bounding_box": {
                    "min_x": float(image_minimum[0]),
                    "min_y": float(image_minimum[1]),
                    "max_x": float(image_maximum[0]),
                    "max_y": float(image_maximum[1]),
                },
                "horizontal_span_ratio": image_span_x,
                "vertical_span_ratio": image_span_y,
                "bounding_box_area_ratio": image_span_x * image_span_y,
            }
        )

    return {
        "image_width": width,
        "image_height": height,
        "point_count": int(all_points.shape[0]),
        "bounding_box": {
            "min_x": float(minimum[0]),
            "min_y": float(minimum[1]),
            "max_x": float(maximum[0]),
            "max_y": float(maximum[1]),
        },
        "horizontal_span_ratio": span_x,
        "vertical_span_ratio": span_y,
        "bounding_box_area_ratio": bounding_box_ratio,
        "convex_hull_area_ratio": convex_hull_ratio,
        "grid": {
            "columns": grid_columns,
            "rows": grid_rows,
            "occupied_cells": len(occupied_cells),
            "total_cells": total_cells,
            "coverage_ratio": len(occupied_cells) / total_cells,
        },
        "per_image": per_image,
    }
