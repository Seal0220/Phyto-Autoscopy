from __future__ import annotations

import numpy as np

from app.analysis.calibration.resolution_adaptation import (
    adapt_stereo_resolution,
)
from app.analysis.reconstruction.triangulation import triangulate_point


def _project(
    projection: np.ndarray,
    point: np.ndarray,
) -> np.ndarray:
    homogeneous = projection @ np.append(point, 1.0)
    return homogeneous[:2] / homogeneous[2]


def test_stereo_calibration_scales_to_independent_camera_resolutions() -> None:
    camera = np.asarray([
        [400.0, 0.0, 80.0],
        [0.0, 400.0, 60.0],
        [0.0, 0.0, 1.0],
    ])
    top_projection = np.column_stack([camera, np.zeros(3)])
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
    fundamental = np.linalg.inv(camera).T @ essential @ np.linalg.inv(camera)

    adapted = adapt_stereo_resolution(
        calibration_resolution=(160, 120),
        camera_resolutions={
            "top": (320, 180),
            "side": (80, 90),
        },
        top_camera_matrix=camera,
        side_camera_matrix=camera,
        top_projection_matrix=top_projection,
        side_projection_matrix=side_projection,
        fundamental_matrix=fundamental,
    )

    assert adapted.top.scale_x == 2.0
    assert adapted.top.scale_y == 1.5
    assert adapted.side.scale_x == 0.5
    assert adapted.side.scale_y == 0.75
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
