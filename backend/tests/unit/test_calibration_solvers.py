from __future__ import annotations

from types import SimpleNamespace

import cv2
import numpy as np

from app.calibration.board_detection import detect_board
from app.calibration.camera_models import solve_camera_model
from app.models.calibration_models import CalibrationBoardProfile


NOW = "2026-07-20T00:00:00+00:00"


def _chessboard_image(
    squares_x: int,
    squares_y: int,
    square_pixels: int = 64,
) -> np.ndarray:
    margin = square_pixels
    image = np.full(
        (
            squares_y * square_pixels + margin * 2,
            squares_x * square_pixels + margin * 2,
            3,
        ),
        255,
        dtype=np.uint8,
    )
    for row in range(squares_y):
        for column in range(squares_x):
            if (row + column) % 2:
                continue
            cv2.rectangle(
                image,
                (
                    margin + column * square_pixels,
                    margin + row * square_pixels,
                ),
                (
                    margin + (column + 1) * square_pixels,
                    margin + (row + 1) * square_pixels,
                ),
                0,
                thickness=-1,
            )
    return image


def _synthetic_samples() -> list[SimpleNamespace]:
    columns = 10
    rows = 7
    grid = np.mgrid[0:columns, 0:rows].T.reshape(-1, 2)
    objects = np.zeros((len(grid), 3), dtype=np.float32)
    objects[:, :2] = grid.astype(np.float32) * 20.0
    camera_matrix = np.asarray(
        [
            [820.0, 0.0, 320.0],
            [0.0, 815.0, 240.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    samples = []
    for index in range(12):
        rotation = np.asarray(
            [
                -0.2 + 0.035 * index,
                0.14 * np.sin(index * 0.7),
                0.05 * np.cos(index * 0.5),
            ],
            dtype=np.float64,
        )
        translation = np.asarray(
            [
                -90.0 + 15.0 * index,
                -50.0 + 18.0 * (index % 5),
                620.0 + 14.0 * index,
            ],
            dtype=np.float64,
        )
        images, _ = cv2.projectPoints(
            objects,
            rotation,
            translation,
            camera_matrix,
            np.zeros(5, dtype=np.float64),
        )
        samples.append(SimpleNamespace(
            sample_id=f"sample-{index}",
            object_points=objects.tolist(),
            image_points=images.reshape(-1, 2).tolist(),
        ))
    return samples


def test_board_detection_uses_unified_board_profile() -> None:
    board = CalibrationBoardProfile(
        board_profile_id="board-test",
        name="測試棋盤格",
        board_type="chessboard",
        squares_x=11,
        squares_y=8,
        square_length_mm=20.0,
        marker_length_mm=14.0,
        created_at=NOW,
        updated_at=NOW,
    )
    encoded, payload = cv2.imencode(
        ".png",
        _chessboard_image(board.squares_x, board.squares_y),
    )

    assert encoded is True
    result = detect_board(payload.tobytes(), board)
    assert result.board_detected is True
    assert result.corner_count == 70
    assert result.object_points.shape == (70, 3)
    assert result.image_points.shape == (70, 2)


def test_unified_opencv_intrinsic_solver_reports_holdout_quality() -> None:
    result = solve_camera_model(
        "opencv",
        _synthetic_samples(),
        (640, 480),
    )

    assert result.camera_model == "opencv"
    assert result.stable is True
    assert result.reprojection_error_px < 0.01
    assert result.validation_error_px < 0.01
    assert result.maximum_reprojection_error_px < 0.05
    assert len(result.per_image_errors) == 12
    assert any(item["holdout"] for item in result.per_image_errors)
