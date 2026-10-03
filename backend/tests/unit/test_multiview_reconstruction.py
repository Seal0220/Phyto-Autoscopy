from __future__ import annotations

import numpy as np

from app.analysis.reconstruction.multiview import (
    robust_multiview_triangulate,
)
from app.analysis.tip.candidate_detector import TipCandidate2D
from app.analysis.tip.candidate_matcher import (
    TipCandidateView,
    triangulate_tip_hypotheses,
)


def _projection(center_x: float, center_y: float = 0.0) -> np.ndarray:
    intrinsic = np.asarray([
        [800.0, 0.0, 640.0],
        [0.0, 800.0, 360.0],
        [0.0, 0.0, 1.0],
    ])
    translation = np.asarray([-center_x, -center_y, 0.0])
    return intrinsic @ np.column_stack((np.eye(3), translation))


def _project(projection: np.ndarray, point: np.ndarray) -> tuple[float, float]:
    value = projection @ np.append(point, 1.0)
    pixel = value[:2] / value[2]
    return float(pixel[0]), float(pixel[1])


def test_three_view_refinement_reduces_synthetic_position_error() -> None:
    expected = np.asarray([35.0, 22.0, 900.0])
    projections = (
        _projection(0.0),
        _projection(120.0),
        _projection(30.0, 110.0),
    )
    exact = [_project(projection, expected) for projection in projections]
    baseline = robust_multiview_triangulate(
        projections[:2],
        (
            (exact[0][0] + 1.4, exact[0][1] - 0.8),
            (exact[1][0] - 1.2, exact[1][1] + 0.7),
        ),
    )
    refined = robust_multiview_triangulate(
        projections,
        (
            (exact[0][0] + 1.4, exact[0][1] - 0.8),
            (exact[1][0] - 1.2, exact[1][1] + 0.7),
            exact[2],
        ),
    )

    assert np.linalg.norm(refined.point - expected) < np.linalg.norm(
        baseline.point - expected
    )
    assert refined.used_observations == (True, True, True)


def test_invalid_rotating_observation_is_rejected_without_losing_baseline() -> None:
    expected = np.asarray([20.0, -15.0, 750.0])
    projections = (
        _projection(0.0),
        _projection(100.0),
        _projection(20.0, 90.0),
    )
    observations = [_project(projection, expected) for projection in projections]
    baseline = robust_multiview_triangulate(
        projections[:2],
        observations[:2],
    )
    result = robust_multiview_triangulate(
        projections,
        (
            observations[0],
            observations[1],
            (
                observations[2][0] + 200.0,
                observations[2][1] - 160.0,
            ),
        ),
        rejection_threshold_px=8.0,
    )

    assert result.used_observations == (True, True, False)
    assert np.allclose(result.point, baseline.point, atol=1e-9)


def test_moderately_wrong_rotating_view_cannot_shift_stereo_seed() -> None:
    expected = np.asarray([20.0, -15.0, 750.0])
    projections = (
        _projection(0.0),
        _projection(100.0),
        _projection(20.0, 90.0),
    )
    observations = [_project(projection, expected) for projection in projections]
    result = robust_multiview_triangulate(
        projections,
        (
            observations[0],
            observations[1],
            (observations[2][0] + 10.0, observations[2][1]),
        ),
        rejection_threshold_px=8.0,
    )

    assert result.used_observations == (True, True, False)
    assert np.allclose(result.point, expected, atol=1e-9)


def test_tip_pairing_can_use_rotating_when_top_tip_is_occluded() -> None:
    expected = np.asarray([20.0, -15.0, 750.0])
    sources = (
        ("rotating", _projection(20.0, 90.0), (20.0, 90.0)),
        ("side", _projection(100.0), (100.0, 0.0)),
    )
    views = []
    for camera_id, projection, center in sources:
        x, y = _project(projection, expected)
        views.append(TipCandidateView(
            view_id=camera_id,
            camera_id=camera_id,
            projection_matrix=projection,
            camera_center_world_mm=np.asarray([*center, 0.0]),
            candidates=(TipCandidate2D(
                candidate_id=camera_id,
                x_px=x,
                y_px=y,
                confidence=1.0,
                visibility_confidence=1.0,
                source="synthetic",
            ),),
        ))

    hypotheses = triangulate_tip_hypotheses(
        views,
        rejection_threshold_px=8.0,
    )

    assert hypotheses
    assert np.allclose(hypotheses[0].point_world_mm, expected, atol=1e-9)
    assert hypotheses[0].used_observations == (True, True)

