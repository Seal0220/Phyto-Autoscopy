import numpy as np
import pytest

from app.analysis.reconstruction.triangulation import triangulate_points


def projections():
    top = np.array([
        [100, 0, 0, 0],
        [0, 100, 0, 0],
        [0, 0, 1, 0],
    ], dtype=float)
    side = np.array([
        [100, 0, 0, -1000],
        [0, 100, 0, 0],
        [0, 0, 1, 0],
    ], dtype=float)
    return top, side


def test_triangulation_recovers_known_point_in_projection_units() -> None:
    top, side = projections()
    result = triangulate_points(
        top,
        side,
        np.array([[20, 40]], dtype=float),
        np.array([[-180, 40]], dtype=float),
    )
    assert np.allclose(result[0], [1, 2, 5], atol=1e-6)


def test_triangulation_rejects_mismatched_inputs() -> None:
    top, side = projections()
    with pytest.raises(ValueError):
        triangulate_points(top, side, [[1, 2]], [])
