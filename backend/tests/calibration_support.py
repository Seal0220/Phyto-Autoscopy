from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.analysis.calibration import create_chessboard_object_points
from app.core.config import AppSettings, CameraConfig, PathSettings
from app.database.connection import Database
from app.database.schema import initialize_schema
from app.models.calibration_models import CalibrationCreateRequest, CalibrationProfile
from app.repositories.calibration_repository import CalibrationRepository
from app.services.calibration_service import CalibrationService


PATTERN_SIZE = (10, 7)
SQUARE_SIZE_MM = 12.0
IMAGE_SIZE = (640, 480)


@dataclass(slots=True)
class CalibrationHarness:
    settings: AppSettings
    database: Database
    repository: CalibrationRepository
    service: CalibrationService
    captures_dir: Path


def create_calibration_harness(
    tmp_path: Path,
    *,
    image_size: tuple[int, int] = IMAGE_SIZE,
) -> CalibrationHarness:
    width, height = image_size
    settings = AppSettings(
        paths=PathSettings(
            captures_dir=tmp_path / "captures",
            snapshots_dir=tmp_path / "snapshots",
            calibration_dir=tmp_path / "calibration",
            analysis_dir=tmp_path / "analysis",
            database_path=tmp_path / "database" / "test.sqlite3",
            logs_dir=tmp_path / "logs",
            temp_dir=tmp_path / "temp",
        ),
        cameras={
            "top": CameraConfig(
                device_name="CHLOROCULUS EYE-TOP",
                device_index=0,
                width=width,
                height=height,
            ),
            "side": CameraConfig(
                device_name="CHLOROCULUS EYE-SIDE",
                device_index=1,
                width=width,
                height=height,
            ),
            "rotating": CameraConfig(
                device_name="CHLOROCULUS EYE-ARM",
                device_index=2,
                width=width,
                height=height,
            ),
        },
    )
    settings.paths.captures_dir.mkdir(parents=True)
    settings.paths.calibration_dir.mkdir(parents=True)
    database = Database(settings.paths.database_path)
    initialize_schema(database)
    repository = CalibrationRepository(database)
    return CalibrationHarness(
        settings=settings,
        database=database,
        repository=repository,
        service=CalibrationService(settings, repository),
        captures_dir=settings.paths.captures_dir,
    )


def render_chessboard(
    *,
    image_size: tuple[int, int] = IMAGE_SIZE,
    pattern_size: tuple[int, int] = PATTERN_SIZE,
    square_pixels: int = 32,
) -> np.ndarray:
    width, height = image_size
    columns, rows = pattern_size
    board_width = (columns + 1) * square_pixels
    board_height = (rows + 1) * square_pixels
    if board_width >= width or board_height >= height:
        raise ValueError("測試棋盤必須完整位於影像內。")
    offset_x = (width - board_width) // 2
    offset_y = (height - board_height) // 2
    image = np.full((height, width), 255, dtype=np.uint8)
    for row in range(rows + 1):
        for column in range(columns + 1):
            if (row + column) % 2 == 0:
                cv2.rectangle(
                    image,
                    (
                        offset_x + column * square_pixels,
                        offset_y + row * square_pixels,
                    ),
                    (
                        offset_x + (column + 1) * square_pixels,
                        offset_y + (row + 1) * square_pixels,
                    ),
                    0,
                    thickness=-1,
                )
    return image


def write_png(path: Path, image: np.ndarray) -> None:
    success, encoded = cv2.imencode(".png", image)
    assert success is True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded.tobytes())


def write_image_sets(
    harness: CalibrationHarness,
    *,
    count: int = 1,
    image_size: tuple[int, int] = IMAGE_SIZE,
) -> tuple[list[str], list[str], list[list[str]]]:
    image = render_chessboard(image_size=image_size)
    top_paths: list[str] = []
    side_paths: list[str] = []
    stereo_pairs: list[list[str]] = []
    for index in range(count):
        top_path = harness.captures_dir / f"top_{index:03d}.png"
        side_path = harness.captures_dir / f"side_{index:03d}.png"
        write_png(top_path, image)
        write_png(side_path, image)
        top_paths.append(str(top_path))
        side_paths.append(str(side_path))
        stereo_pairs.append([str(top_path), str(side_path)])
    return top_paths, side_paths, stereo_pairs


def calibration_request(
    top_paths: list[str],
    side_paths: list[str],
    stereo_pairs: list[list[str]],
) -> CalibrationCreateRequest:
    return CalibrationCreateRequest(
        top_image_paths=top_paths,
        side_image_paths=side_paths,
        stereo_image_pairs=stereo_pairs,
        pattern_columns=PATTERN_SIZE[0],
        pattern_rows=PATTERN_SIZE[1],
        square_size_mm_x=SQUARE_SIZE_MM,
        square_size_mm_y=SQUARE_SIZE_MM,
        stereo_pattern_columns=PATTERN_SIZE[0],
        stereo_pattern_rows=PATTERN_SIZE[1],
        stereo_square_size_mm_x=SQUARE_SIZE_MM,
        stereo_square_size_mm_y=SQUARE_SIZE_MM,
        individual_board_width_cm=13.2,
        individual_board_height_cm=9.6,
        stereo_board_width_cm=13.2,
        stereo_board_height_cm=9.6,
        world_transform_matrix=np.eye(4).tolist(),
    )


def synthetic_stereo_points() -> dict[str, object]:
    object_points = create_chessboard_object_points(
        PATTERN_SIZE,
        SQUARE_SIZE_MM,
    )
    top_camera_matrix = np.array(
        [
            [820.0, 0.0, 320.0],
            [0.0, 815.0, 240.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    side_camera_matrix = np.array(
        [
            [800.0, 0.0, 318.0],
            [0.0, 805.0, 242.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    distortion = np.zeros(5, dtype=np.float64)
    stereo_rotation, _ = cv2.Rodrigues(
        np.array([0.01, 0.04, -0.01], dtype=np.float64)
    )
    stereo_translation = np.array([[55.0], [2.0], [5.0]], dtype=np.float64)

    top_points: list[np.ndarray] = []
    side_points: list[np.ndarray] = []
    for index in range(10):
        object_rotation_vector = np.array(
            [
                [-0.18 + 0.04 * index],
                [0.10 * np.sin(index)],
                [0.025 * np.cos(index)],
            ],
            dtype=np.float64,
        )
        object_rotation, _ = cv2.Rodrigues(object_rotation_vector)
        object_translation = np.array(
            [
                [-100.0 + 15.0 * index],
                [-50.0 + 10.0 * (index % 4)],
                [720.0 + 10.0 * index],
            ],
            dtype=np.float64,
        )
        side_rotation = stereo_rotation @ object_rotation
        side_translation = stereo_rotation @ object_translation + stereo_translation
        side_rotation_vector, _ = cv2.Rodrigues(side_rotation)
        projected_top, _ = cv2.projectPoints(
            object_points,
            object_rotation_vector,
            object_translation,
            top_camera_matrix,
            distortion,
        )
        projected_side, _ = cv2.projectPoints(
            object_points,
            side_rotation_vector,
            side_translation,
            side_camera_matrix,
            distortion,
        )
        top_points.append(projected_top)
        side_points.append(projected_side)
    return {
        "top_points": top_points,
        "side_points": side_points,
    }


def seed_synthetic_corner_detections(
    profile: CalibrationProfile,
    data: dict[str, object],
) -> None:
    top_points = data["top_points"]
    side_points = data["side_points"]
    profile.corner_detections = {
        "top": [
            {
                "image_id": path,
                "image_width": IMAGE_SIZE[0],
                "image_height": IMAGE_SIZE[1],
                "found": True,
                "corner_count": PATTERN_SIZE[0] * PATTERN_SIZE[1],
                "corners": top_points[index].reshape(-1, 2).tolist(),
            }
            for index, path in enumerate(profile.selected_images["top"])
        ],
        "side": [
            {
                "image_id": path,
                "image_width": IMAGE_SIZE[0],
                "image_height": IMAGE_SIZE[1],
                "found": True,
                "corner_count": PATTERN_SIZE[0] * PATTERN_SIZE[1],
                "corners": side_points[index].reshape(-1, 2).tolist(),
            }
            for index, path in enumerate(profile.selected_images["side"])
        ],
        "stereo": [
            {
                "pair_id": f"stereo_{index + 1:04d}",
                "top": {
                    "image_id": pair[0],
                    "image_width": IMAGE_SIZE[0],
                    "image_height": IMAGE_SIZE[1],
                    "found": True,
                    "corner_count": PATTERN_SIZE[0] * PATTERN_SIZE[1],
                    "corners": top_points[index].reshape(-1, 2).tolist(),
                },
                "side": {
                    "image_id": pair[1],
                    "image_width": IMAGE_SIZE[0],
                    "image_height": IMAGE_SIZE[1],
                    "found": True,
                    "corner_count": PATTERN_SIZE[0] * PATTERN_SIZE[1],
                    "corners": side_points[index].reshape(-1, 2).tolist(),
                },
                "usable": True,
            }
            for index, pair in enumerate(profile.selected_images["stereo"])
        ],
    }
    profile.status = "corners_detected"
