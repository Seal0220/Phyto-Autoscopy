import cv2
import numpy as np

from app.analysis.detection.top_tip_detection import top_tip_candidates


def rectangle_contour(x: int, y: int, width: int, height: int):
    mask = np.zeros((80, 80), dtype=np.uint8)
    cv2.rectangle(mask, (x, y), (x + width, y + height), 255, -1)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    return contours[0]


def test_top_tip_uses_largest_contours_and_plant_base_distance() -> None:
    small = rectangle_contour(5, 5, 4, 4)
    large = rectangle_contour(20, 10, 20, 30)

    result = top_tip_candidates(
        [small, large],
        plant_base=(30, 40),
        num_selected_points=1,
    )

    assert len(result.selected_contours) == 1
    assert result.candidate_points[0][1] == 10


def test_top_tip_restores_roi_origin() -> None:
    contour = rectangle_contour(0, 0, 8, 8)
    result = top_tip_candidates(
        [contour],
        plant_base=(14, 18),
        num_selected_points=1,
        roi_origin=(10, 10),
    )
    assert result.candidate_points[0][0] >= 10
    assert result.candidate_points[0][1] >= 10
