import cv2
import numpy as np

from app.analysis.detection.epipolar_constraint import (
    epipolar_line_from_top_point,
    filter_contours_by_epipolar_line,
    point_line_distance,
)


def contour_at(y: int):
    mask = np.zeros((40, 40), dtype=np.uint8)
    cv2.rectangle(mask, (10, y), (20, y + 3), 255, -1)
    return cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0][0]


def test_epipolar_line_and_normalized_distance() -> None:
    fundamental = np.array([
        [0, 0, 0],
        [0, 0, -1],
        [0, 1, 0],
    ], dtype=float)
    line = epipolar_line_from_top_point(fundamental, (12, 15))

    assert point_line_distance((5, 15), line) < 1e-6
    assert point_line_distance((5, 20), line) == 5


def test_epipolar_filter_excludes_far_contours() -> None:
    selected = filter_contours_by_epipolar_line(
        [contour_at(14), contour_at(30)],
        (0, 1, -15),
        maximum_distance_px=2,
        maximum_count=2,
    )
    assert len(selected) == 1
