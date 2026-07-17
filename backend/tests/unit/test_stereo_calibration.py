from __future__ import annotations

from inspect import Parameter, signature

import cv2
import numpy as np
import pytest

from app.analysis.calibration import (
    calculate_epipolar_rms_error,
    calibrate_stereo_from_points,
    compute_epipolar_lines,
    create_chessboard_object_points,
)


PATTERN_SIZE = (10, 7)
SQUARE_SIZE_MM = 12.0
IMAGE_SIZE = (640, 480)


def _synthetic_stereo_points() -> dict[str, object]:
    object_points = create_chessboard_object_points(
        PATTERN_SIZE,
        SQUARE_SIZE_MM,
    )
    top_camera_matrix = np.array(
        [
            [820.0, 0.0, 320.0],
            [0.0, 815.0, 240.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    side_camera_matrix = np.array(
        [
            [800.0, 0.0, 318.0],
            [0.0, 805.0, 242.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    distortion = np.zeros(5, dtype=np.float64)
    expected_rotation, _ = cv2.Rodrigues(
        np.array([0.01, 0.04, -0.01], dtype=np.float64)
    )
    expected_translation = np.array(
        [[55.0], [2.0], [5.0]],
        dtype=np.float64,
    )

    top_points: list[np.ndarray] = []
    side_points: list[np.ndarray] = []
    for index in range(10):
        object_rotation_vector = np.array(
            [
                [-0.18 + 0.04 * index],
                [0.10 * np.sin(index)],
                [0.025 * np.cos(index)],
            ],
            dtype=np.float64,
        )
        object_rotation, _ = cv2.Rodrigues(object_rotation_vector)
        object_translation = np.array(
            [
                [-100.0 + 15.0 * index],
                [-50.0 + 10.0 * (index % 4)],
                [720.0 + 10.0 * index],
            ],
            dtype=np.float64,
        )
        side_object_rotation = expected_rotation @ object_rotation
        side_object_translation = (
            expected_rotation @ object_translation + expected_translation
        )
        side_object_rotation_vector, _ = cv2.Rodrigues(side_object_rotation)

        projected_top, _ = cv2.projectPoints(
            object_points,
            object_rotation_vector,
            object_translation,
            top_camera_matrix,
            distortion,
        )
        projected_side, _ = cv2.projectPoints(
            object_points,
            side_object_rotation_vector,
            side_object_translation,
            side_camera_matrix,
            distortion,
        )
        top_points.append(projected_top)
        side_points.append(projected_side)

    return {
        "top_points": top_points,
        "side_points": side_points,
        "top_camera_matrix": top_camera_matrix,
        "side_camera_matrix": side_camera_matrix,
        "distortion": distortion,
        "expected_rotation": expected_rotation,
        "expected_translation": expected_translation,
    }


def test_stereo_calibration_recovers_geometry_and_projection_matrices() -> None:
    data = _synthetic_stereo_points()
    pair_ids = [f"pair-{index}" for index in range(10)]

    result = calibrate_stereo_from_points(
        data["top_points"],
        data["side_points"],
        IMAGE_SIZE,
        IMAGE_SIZE,
        PATTERN_SIZE,
        SQUARE_SIZE_MM,
        data["top_camera_matrix"],
        data["distortion"],
        data["side_camera_matrix"],
        data["distortion"],
        pair_ids=pair_ids,
    )

    assert result.image_size == IMAGE_SIZE
    assert result.pattern_size == PATTERN_SIZE
    assert result.square_size_mm == (SQUARE_SIZE_MM, SQUARE_SIZE_MM)
    assert result.rotation_matrix.shape == (3, 3)
    assert result.translation_vector.shape == (3, 1)
    assert result.essential_matrix.shape == (3, 3)
    assert result.fundamental_matrix.shape == (3, 3)
    assert result.top_projection_matrix.shape == (3, 4)
    assert result.side_projection_matrix.shape == (3, 4)
    assert result.top_rectification_rotation.shape == (3, 3)
    assert result.side_rectification_rotation.shape == (3, 3)
    assert result.disparity_to_depth_matrix.shape == (4, 4)
    assert np.isfinite(result.rotation_matrix).all()
    assert np.isfinite(result.translation_vector).all()
    assert np.isfinite(result.essential_matrix).all()
    assert np.isfinite(result.fundamental_matrix).all()
    assert np.isfinite(result.top_projection_matrix).all()
    assert np.isfinite(result.side_projection_matrix).all()
    assert result.rms_error < 0.01
    assert np.allclose(
        result.rotation_matrix,
        data["expected_rotation"],
        atol=1e-4,
    )
    assert np.allclose(
        result.translation_vector,
        data["expected_translation"],
        atol=1e-3,
    )
    assert result.pair_ids == tuple(pair_ids)
    assert len(result.reprojection_error_per_pair) == 10
    assert result.reprojection_error_per_pair[0]["pair_id"] == "pair-0"
    assert result.reprojection_error_per_pair[0]["epipolar_rms_error_px"] < 0.01
    assert result.point_coverage["top"]["point_count"] == 700
    assert result.point_coverage["side"]["point_count"] == 700

    serialized = result.to_dict()
    assert serialized["top_projection_matrix"] == (
        result.top_projection_matrix.tolist()
    )
    assert serialized["side_projection_matrix"] == (
        result.side_projection_matrix.tolist()
    )
    assert serialized["top_rectification_rotation"] == (
        result.top_rectification_rotation.tolist()
    )
    assert serialized["side_rectification_rotation"] == (
        result.side_rectification_rotation.tolist()
    )
    assert serialized["disparity_to_depth_matrix"] == (
        result.disparity_to_depth_matrix.tolist()
    )
    assert serialized["top_valid_pixel_roi"] == list(result.top_valid_pixel_roi)
    assert serialized["side_valid_pixel_roi"] == list(result.side_valid_pixel_roi)
    assert serialized["stereo_mean_reprojection_error"] == result.rms_error


def test_epipolar_lines_and_symmetric_error_use_fundamental_matrix() -> None:
    data = _synthetic_stereo_points()
    result = calibrate_stereo_from_points(
        data["top_points"],
        data["side_points"],
        IMAGE_SIZE,
        IMAGE_SIZE,
        PATTERN_SIZE,
        SQUARE_SIZE_MM,
        data["top_camera_matrix"],
        data["distortion"],
        data["side_camera_matrix"],
        data["distortion"],
    )

    lines = compute_epipolar_lines(
        data["top_points"][0],
        result.fundamental_matrix,
        source_image=1,
    )
    error = calculate_epipolar_rms_error(
        data["top_points"][0],
        data["side_points"][0],
        result.fundamental_matrix,
    )

    assert lines.shape == (70, 3)
    assert np.isfinite(lines).all()
    assert error < 0.01


def test_stereo_calibration_rejects_resolution_mismatch() -> None:
    data = _synthetic_stereo_points()

    with pytest.raises(ValueError, match="解析度不一致"):
        calibrate_stereo_from_points(
            data["top_points"],
            data["side_points"],
            IMAGE_SIZE,
            (800, 600),
            PATTERN_SIZE,
            SQUARE_SIZE_MM,
            data["top_camera_matrix"],
            data["distortion"],
            data["side_camera_matrix"],
            data["distortion"],
        )


def test_stereo_pattern_and_square_size_are_explicit_not_inferred() -> None:
    parameters = signature(calibrate_stereo_from_points).parameters

    assert parameters["pattern_size"].default is Parameter.empty
    assert parameters["square_size_mm"].default is Parameter.empty


def test_stereo_calibration_rejects_invalid_matrix_shape() -> None:
    data = _synthetic_stereo_points()

    with pytest.raises(ValueError, match="top_camera_matrix 形狀"):
        calibrate_stereo_from_points(
            data["top_points"],
            data["side_points"],
            IMAGE_SIZE,
            IMAGE_SIZE,
            PATTERN_SIZE,
            SQUARE_SIZE_MM,
            np.eye(4),
            data["distortion"],
            data["side_camera_matrix"],
            data["distortion"],
        )


def test_stereo_calibration_rejects_unpaired_corner_sets() -> None:
    data = _synthetic_stereo_points()

    with pytest.raises(ValueError, match="角點組數必須一致"):
        calibrate_stereo_from_points(
            data["top_points"],
            data["side_points"][:-1],
            IMAGE_SIZE,
            IMAGE_SIZE,
            PATTERN_SIZE,
            SQUARE_SIZE_MM,
            data["top_camera_matrix"],
            data["distortion"],
            data["side_camera_matrix"],
            data["distortion"],
        )


def test_fisheye_stereo_calibration_produces_dynamic_geometry() -> None:
    object_points = create_chessboard_object_points(
        PATTERN_SIZE,
        SQUARE_SIZE_MM,
    ).astype(np.float64).reshape(-1, 1, 3)
    camera_matrix = np.asarray([
        [410.0, 0.0, 320.0],
        [0.0, 410.0, 240.0],
        [0.0, 0.0, 1.0],
    ])
    distortion = np.asarray([-0.03, 0.002, 0.0, 0.0]).reshape(4, 1)
    stereo_rotation, _ = cv2.Rodrigues(
        np.asarray([0.01, 0.025, -0.008])
    )
    stereo_translation = np.asarray([[65.0], [2.0], [4.0]])
    top_points = []
    side_points = []
    for index in range(10):
        rotation_vector = np.asarray([
            [-0.12 + 0.025 * index],
            [0.05 * np.sin(index)],
            [0.02 * np.cos(index)],
        ])
        rotation, _ = cv2.Rodrigues(rotation_vector)
        translation = np.asarray([
            [-80.0 + 12.0 * index],
            [-45.0 + 9.0 * (index % 4)],
            [650.0 + 12.0 * index],
        ])
        side_rotation = stereo_rotation @ rotation
        side_rotation_vector, _ = cv2.Rodrigues(side_rotation)
        side_translation = stereo_rotation @ translation + stereo_translation
        top, _ = cv2.fisheye.projectPoints(
            object_points,
            rotation_vector,
            translation,
            camera_matrix,
            distortion,
        )
        side, _ = cv2.fisheye.projectPoints(
            object_points,
            side_rotation_vector,
            side_translation,
            camera_matrix,
            distortion,
        )
        top_points.append(top)
        side_points.append(side)

    result = calibrate_stereo_from_points(
        top_points,
        side_points,
        IMAGE_SIZE,
        IMAGE_SIZE,
        PATTERN_SIZE,
        SQUARE_SIZE_MM,
        camera_matrix,
        distortion,
        camera_matrix,
        distortion,
        projection_model="fisheye",
    )

    assert result.projection_model == "fisheye"
    assert result.rms_error < 0.01
    assert np.allclose(
        result.translation_vector,
        stereo_translation,
        atol=0.1,
    )
