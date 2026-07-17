from __future__ import annotations

from inspect import Parameter, signature

import cv2
import numpy as np
import pytest

from app.analysis.calibration import (
    DISTORTION_COEFFICIENT_ORDER,
    calibrate_camera,
    calibrate_camera_from_points,
    camera_matrix_from_diagonal_fov,
    create_chessboard_object_points,
    detect_chessboard_corners,
    distortion_coefficients_named,
)


PATTERN_SIZE = (10, 7)
SQUARE_SIZE_MM = 12.0
IMAGE_SIZE = (640, 480)


def _render_chessboard(
    pattern_size: tuple[int, int] = PATTERN_SIZE,
    *,
    square_pixels: int = 50,
    margin: int = 30,
) -> np.ndarray:
    columns, rows = pattern_size
    image = np.full(
        (
            (rows + 1) * square_pixels + margin * 2,
            (columns + 1) * square_pixels + margin * 2,
        ),
        255,
        dtype=np.uint8,
    )
    for row in range(rows + 1):
        for column in range(columns + 1):
            if (row + column) % 2 == 0:
                cv2.rectangle(
                    image,
                    (
                        margin + column * square_pixels,
                        margin + row * square_pixels,
                    ),
                    (
                        margin + (column + 1) * square_pixels,
                        margin + (row + 1) * square_pixels,
                    ),
                    0,
                    thickness=-1,
                )
    return image


def _synthetic_camera_points() -> tuple[list[np.ndarray], np.ndarray]:
    object_points = create_chessboard_object_points(
        PATTERN_SIZE,
        SQUARE_SIZE_MM,
    )
    camera_matrix = np.array(
        [
            [820.0, 0.0, 320.0],
            [0.0, 815.0, 240.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    distortion = np.zeros(5, dtype=np.float64)
    image_points: list[np.ndarray] = []
    for index in range(10):
        rotation_vector = np.array(
            [
                [-0.18 + 0.04 * index],
                [0.12 * np.sin(index)],
                [0.03 * np.cos(index)],
            ],
            dtype=np.float64,
        )
        translation_vector = np.array(
            [
                [-80.0 + 16.0 * index],
                [-40.0 + 8.0 * (index % 4)],
                [650.0 + 12.0 * index],
            ],
            dtype=np.float64,
        )
        projected, _ = cv2.projectPoints(
            object_points,
            rotation_vector,
            translation_vector,
            camera_matrix,
            distortion,
        )
        image_points.append(projected)
    return image_points, camera_matrix


def test_detect_chessboard_corners_refines_rendered_board() -> None:
    detection = detect_chessboard_corners(
        _render_chessboard(),
        PATTERN_SIZE,
        image_id="rendered-board",
    )

    assert detection.found is True
    assert detection.image_id == "rendered-board"
    assert detection.corners is not None
    assert detection.corners.shape == (PATTERN_SIZE[0] * PATTERN_SIZE[1], 1, 2)
    assert np.isfinite(detection.corners).all()
    assert detection.to_dict()["corner_count"] == 70


def test_detect_chessboard_corners_reads_windows_chinese_path(tmp_path) -> None:
    image_path = tmp_path / "校正影像_俯視角.png"
    encoded, buffer = cv2.imencode(".png", _render_chessboard())
    assert encoded is True
    image_path.write_bytes(buffer.tobytes())

    detection = detect_chessboard_corners(
        image_path,
        PATTERN_SIZE,
        image_id="chinese-path",
    )

    assert detection.found is True
    assert detection.corners is not None
    assert detection.corners.shape == (70, 1, 2)


def test_detect_chessboard_corners_reports_empty_image_file(tmp_path) -> None:
    image_path = tmp_path / "empty.png"
    image_path.touch()

    with pytest.raises(ValueError, match="校正影像為空"):
        detect_chessboard_corners(image_path, PATTERN_SIZE)


def test_calibrate_camera_from_synthetic_corners_reports_quality() -> None:
    image_points, expected_camera_matrix = _synthetic_camera_points()
    image_ids = [f"image-{index}" for index in range(len(image_points))]

    result = calibrate_camera_from_points(
        image_points,
        IMAGE_SIZE,
        PATTERN_SIZE,
        SQUARE_SIZE_MM,
        image_ids=image_ids,
    )

    assert result.image_size == IMAGE_SIZE
    assert result.pattern_size == PATTERN_SIZE
    assert result.square_size_mm == (SQUARE_SIZE_MM, SQUARE_SIZE_MM)
    assert result.camera_matrix.shape == (3, 3)
    assert result.distortion_coefficients.shape == (5,)
    assert np.isfinite(result.camera_matrix).all()
    assert np.isfinite(result.distortion_coefficients).all()
    assert result.rms_error < 0.01
    assert result.mean_reprojection_error < 0.01
    assert len(result.reprojection_error_per_image) == len(image_points)
    assert result.reprojection_error_per_image[0]["image_id"] == "image-0"
    assert result.point_coverage["point_count"] == len(image_points) * 70
    assert 0.0 < result.point_coverage["grid"]["coverage_ratio"] <= 1.0
    assert result.successful_image_count == len(image_points)
    assert result.total_image_count == len(image_points)
    assert np.allclose(result.camera_matrix, expected_camera_matrix, atol=0.01)


def test_distortion_coefficients_preserve_opencv_order_and_named_mapping() -> None:
    coefficients = np.array([0.1, -0.2, 0.003, -0.004, 0.05])

    assert DISTORTION_COEFFICIENT_ORDER == ("k1", "k2", "p1", "p2", "k3")
    assert distortion_coefficients_named(coefficients) == {
        "k1": 0.1,
        "k2": -0.2,
        "p1": 0.003,
        "p2": -0.004,
        "k3": 0.05,
    }


def test_square_size_is_explicit_and_scales_object_points_in_mm() -> None:
    square_parameter = signature(calibrate_camera_from_points).parameters[
        "square_size_mm"
    ]
    assert square_parameter.default is Parameter.empty

    object_points = create_chessboard_object_points(
        (3, 2),
        (12.5, 8.0),
    )
    assert object_points.tolist() == [
        [0.0, 0.0, 0.0],
        [12.5, 0.0, 0.0],
        [25.0, 0.0, 0.0],
        [0.0, 8.0, 0.0],
        [12.5, 8.0, 0.0],
        [25.0, 8.0, 0.0],
    ]

    with pytest.raises(ValueError, match="square_size_mm"):
        create_chessboard_object_points(PATTERN_SIZE, 0.0)
    with pytest.raises(ValueError, match="明確提供"):
        create_chessboard_object_points(PATTERN_SIZE, None)


def test_calibrate_camera_rejects_mixed_image_resolutions_before_detection() -> None:
    images = [
        np.zeros((480, 640), dtype=np.uint8),
        np.zeros((600, 800), dtype=np.uint8),
    ]

    with pytest.raises(ValueError, match="解析度不一致"):
        calibrate_camera(
            images,
            PATTERN_SIZE,
            SQUARE_SIZE_MM,
        )


def test_calibrate_camera_rejects_non_finite_corner_coordinates() -> None:
    image_points, _ = _synthetic_camera_points()
    image_points[0] = image_points[0].copy()
    image_points[0][0, 0, 0] = np.nan

    with pytest.raises(ValueError, match="NaN"):
        calibrate_camera_from_points(
            image_points,
            IMAGE_SIZE,
            PATTERN_SIZE,
            SQUARE_SIZE_MM,
        )


def test_camera_hardware_fov_builds_a_finite_intrinsic_seed() -> None:
    matrix = camera_matrix_from_diagonal_fov((1280, 960), 126.0)

    assert matrix.shape == (3, 3)
    assert np.isfinite(matrix).all()
    assert matrix[0, 0] == pytest.approx(matrix[1, 1])
    assert matrix[0, 2] == pytest.approx(639.5)
    assert matrix[1, 2] == pytest.approx(479.5)
