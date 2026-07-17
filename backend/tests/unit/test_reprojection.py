import numpy as np

from app.analysis.reconstruction.reprojection import (
    reprojection_errors,
    summarize_reprojection_errors,
)


def test_reprojection_error_is_zero_for_matching_observation() -> None:
    projection = np.array([
        [100, 0, 0, 0],
        [0, 100, 0, 0],
        [0, 0, 1, 0],
    ], dtype=float)
    errors = reprojection_errors(
        projection,
        [[1, 2, 5]],
        [[20, 40]],
    )
    assert errors[0] == 0


def test_reprojection_summary_uses_strict_greater_than_threshold() -> None:
    summary = summarize_reprojection_errors(
        np.array([10.0, 10.1]),
        np.array([0.0, 0.0]),
        high_error_threshold_px=10,
    )
    assert summary.high_error_count == 1
    assert summary.high_error_ratio == 0.5
