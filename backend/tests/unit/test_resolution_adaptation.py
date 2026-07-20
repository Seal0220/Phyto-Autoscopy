from __future__ import annotations

import numpy as np

from app.calibration.resolution_adaptation import (
    adapt_camera_pair_resolution,
)
from app.analysis.reconstruction.triangulation import triangulate_point


def _project(
    projection: np.ndarray,
    point: np.ndarray,
) -> np.ndarray:
    homogeneous = projection @ np.append(point, 1.0)
    return homogeneous[:2] / homogeneous[2]


def test_camera_pair_scales_independent_calibration_and_analysis_resolutions() -> None:
    top_camera = np.asarray([
        [400.0, 0.0, 80.0],
        [0.0, 400.0, 60.0],
        [0.0, 0.0, 1.0],
    ])
    side_camera = np.asarray([
        [800.0, 0.0, 160.0],
        [0.0, 800.0, 120.0],
        [0.0, 0.0, 1.0],
    ])
    top_projection = np.column_stack([top_camera, np.zeros(3)])
    side_projection = np.asarray([
        [400.0, 0.0, 80.0, -4000.0],
        [0.0, 400.0, 60.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
    ])
    translation = np.asarray([-10.0, 0.0, 0.0])
    essential = np.asarray([
        [0.0, -translation[2], translation[1]],
        [translation[2], 0.0, -translation[0]],
        [-translation[1], translation[0], 0.0],
    ])
    fundamental = (
        np.linalg.inv(side_camera).T
        @ essential
        @ np.linalg.inv(top_camera)
    )

    adapted = adapt_camera_pair_resolution(
        projection_resolution=(160, 120),
        calibration_resolutions={
            "top": (160, 120),
            "side": (320, 240),
        },
        camera_resolutions={
            "top": (320, 180),
            "side": (80, 90),
        },
        top_camera_matrix=top_camera,
        side_camera_matrix=side_camera,
        top_projection_matrix=top_projection,
        side_projection_matrix=side_projection,
        fundamental_matrix=fundamental,
    )

    assert adapted.top.scale_x == 2.0
    assert adapted.top.scale_y == 1.5
    assert adapted.side.scale_x == 0.25
    assert adapted.side.scale_y == 0.375
    assert adapted.metadata()["policy"] == "scale_pixel_coordinate_matrices"

    point = np.asarray([10.0, 5.0, 400.0])
    top_point = _project(adapted.top.projection_matrix, point)
    side_point = _project(adapted.side.projection_matrix, point)
    reconstructed = triangulate_point(
        adapted.top.projection_matrix,
        adapted.side.projection_matrix,
        tuple(top_point),
        tuple(side_point),
    )

    assert np.allclose(reconstructed, point, atol=1e-8)
    top_homogeneous = np.append(top_point, 1.0)
    side_homogeneous = np.append(side_point, 1.0)
    assert abs(
        side_homogeneous
        @ adapted.fundamental_matrix
        @ top_homogeneous
    ) < 1e-10
