from __future__ import annotations

import cv2
import numpy as np

from app.calibration.board_detection import detect_board
from app.calibration.board_generation import (
    fixed_board_values,
    render_calibration_board,
)
from app.models.calibration_models import CalibrationBoardProfile


def board_profile(board_type: str) -> CalibrationBoardProfile:
    return CalibrationBoardProfile(
        board_profile_id=f"test-{board_type}",
        name=f"測試 {board_type}",
        board_type=board_type,
        squares_x=8,
        squares_y=6,
        square_length_mm=30,
        marker_length_mm=22,
        aruco_dictionary="DICT_5X5_100",
        created_at="2026-07-20T00:00:00+00:00",
        updated_at="2026-07-20T00:00:00+00:00",
    )


def test_generated_charuco_board_is_detectable_png() -> None:
    board = board_profile("charuco")
    image_bytes = render_calibration_board(board)

    assert image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert b"pHYs" in image_bytes
    result = detect_board(image_bytes, board)
    assert result.board_detected is True
    assert result.marker_count > 0


def test_generated_chessboard_has_expected_inner_corners() -> None:
    board = board_profile("chessboard")
    image_bytes = render_calibration_board(board)
    image = cv2.imdecode(
        np.frombuffer(image_bytes, dtype=np.uint8),
        cv2.IMREAD_GRAYSCALE,
    )

    assert image is not None
    found, corners = cv2.findChessboardCorners(
        image,
        (board.squares_x - 1, board.squares_y - 1),
    )
    assert found is True
    assert corners is not None
    assert len(corners) == (board.squares_x - 1) * (board.squares_y - 1)


def test_a4_landscape_geometry_uses_printable_paper_area() -> None:
    values = fixed_board_values("a4", "landscape", 8, 6)

    assert values["name"] == "A4 橫向 OpenCV 校正板"
    assert values["board_type"] == "charuco"
    assert values["aruco_dictionary"] == "DICT_5X5_100"
    assert values["print_margin_mm"] == 10.0
    assert values["square_length_mm"] == 31.666667
    assert values["marker_length_mm"] == 23.222222
