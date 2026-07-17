import cv2
import numpy as np

from app.analysis.detection.minimum_path import minimum_path_tip


def test_minimum_path_builds_graph_path_to_epipolar_candidate() -> None:
    mask = np.zeros((60, 60), dtype=np.uint8)
    cv2.line(mask, (30, 55), (30, 25), 255, 5)
    cv2.line(mask, (30, 25), (8, 8), 255, 5)
    cv2.line(mask, (30, 25), (50, 16), 255, 5)

    result = minimum_path_tip(
        mask,
        plant_base=(30, 55),
        epipolar_line=(0, 1, -10),
        maximum_epipolar_distance_px=4,
        connectivity=8,
    )

    assert result is not None
    assert result.candidate_point[1] <= 11
    assert len(result.path) > 10
    assert result.path[0][1] > result.path[-1][1]
    assert result.path_cost > 0


def test_minimum_path_returns_none_for_disconnected_line() -> None:
    mask = np.zeros((30, 30), dtype=np.uint8)
    cv2.line(mask, (15, 25), (15, 15), 255, 3)
    result = minimum_path_tip(
        mask,
        plant_base=(15, 25),
        epipolar_line=(0, 1, -2),
        maximum_epipolar_distance_px=1,
        connectivity=8,
    )
    assert result is None
