from __future__ import annotations

import csv
import hashlib
import time
from pathlib import Path

import numpy as np

from app.core.config import load_settings
from app.database.connection import Database
from app.database.schema import initialize_schema
from app.models.analysis_models import AnalysisCreateRequest
from app.models.calibration_models import CalibrationProfile
from app.models.capture_models import MetadataRecord
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.calibration_repository import CalibrationRepository
from app.repositories.capture_repository import CaptureRepository
from app.repositories.record_repository import RecordRepository
from app.services.analysis_service import AnalysisService
from tests.fixtures.analysis_baseline import (
    BASELINE_CALIBRATION_ID,
    BASELINE_RECORD_ID,
    create_analysis_baseline,
)
from tests.integration.test_support import write_test_config


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def analysis_parameters() -> dict:
    return {
        "segmentation": {
            "history": 20,
            "variance_threshold": 12.0,
            "detect_shadows": False,
            "learning_rate": 0.0,
            "initialization_frames": 2,
            "opening_kernel_size": 3,
            "closing_kernel_size": 3,
            "erosion_kernel_size": None,
            "minimum_top_contour_area_px": 8.0,
            "minimum_side_contour_area_px": 8.0,
        },
        "lighting_change": {
            "lighting_change_area_px": 50000.0,
            "lighting_change_est_time_frames": 2,
        },
        "top_detection": {
            "roi": [0, 0, 160, 120],
            "plant_base": [80.0, 108.0],
            "num_selected_points": 1,
            "update_roi": True,
            "roi_update_margin_px": 10,
        },
        "side_detection": {
            "roi": [0, 0, 160, 120],
            "plant_base": [82.0, 108.0],
            "num_selected_points": 1,
            "update_roi": True,
            "roi_update_margin_px": 10,
            "maximum_epipolar_distance_px": 6.0,
            "minimum_path_connectivity": 8,
            "minimum_path_edge_weight": "inverse_distance_transform",
        },
        "interpolation": {
            "method": "linear",
            "maximum_gap_seconds": 3.0,
        },
    }


def _calibration_profile(dataset: dict) -> CalibrationProfile:
    calibration = dataset["manifest"]["calibration_id"]
    assert calibration == BASELINE_CALIBRATION_ID
    output_path = dataset["calibration_path"].parent
    camera_matrix = [
        [400.0, 0.0, 80.0],
        [0.0, 400.0, 60.0],
        [0.0, 0.0, 1.0],
    ]
    top_projection = [
        [400.0, 0.0, 80.0, 0.0],
        [0.0, 400.0, 60.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
    ]
    side_projection = [
        [400.0, 0.0, 80.0, -4000.0],
        [0.0, 400.0, 60.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
    ]
    rotation = np.eye(3)
    translation = np.asarray([-10.0, 0.0, 0.0])
    essential = np.asarray([
        [0.0, -translation[2], translation[1]],
        [translation[2], 0.0, -translation[0]],
        [-translation[1], translation[0], 0.0],
    ]) @ rotation
    intrinsic = np.asarray(camera_matrix)
    fundamental = np.linalg.inv(intrinsic).T @ essential @ np.linalg.inv(intrinsic)
    return CalibrationProfile(
        calibration_id=BASELINE_CALIBRATION_ID,
        created_at="2026-07-17T00:00:00+00:00",
        updated_at="2026-07-17T00:00:00+00:00",
        status="valid",
        valid=True,
        output_path=str(output_path),
        top_camera_identifier="top",
        side_camera_identifier="side",
        image_width=160,
        image_height=120,
        chessboard_pattern=[10, 7],
        stereo_chessboard_pattern=[10, 7],
        square_size_mm=[10.0, 10.0],
        stereo_square_size_mm=[10.0, 10.0],
        individual_board_size_cm=[59.4, 84.1],
        stereo_board_size_cm=[42.0, 59.4],
        paper_baseline={"reference": "Ruiz-Melero et al. 2024"},
        actual_measurement_difference={
            "fixture": "synthetic values; not paper calibration parameters"
        },
        selected_images={"top": [], "side": [], "stereo": []},
        top_camera_matrix=camera_matrix,
        side_camera_matrix=camera_matrix,
        top_distortion_coefficients=[0.0] * 5,
        side_distortion_coefficients=[0.0] * 5,
        rotation_matrix=rotation.tolist(),
        translation_vector=translation.tolist(),
        essential_matrix=essential.tolist(),
        fundamental_matrix=fundamental.tolist(),
        top_projection_matrix=top_projection,
        side_projection_matrix=side_projection,
        top_rectification_rotation=rotation.tolist(),
        side_rectification_rotation=rotation.tolist(),
        world_transform_matrix=np.eye(4).tolist(),
    )


def create_analysis_service(tmp_path: Path, monkeypatch) -> tuple[AnalysisService, dict]:
    write_test_config(tmp_path, monkeypatch)
    dataset = create_analysis_baseline(tmp_path / "baseline")
    settings = load_settings()
    settings.paths.captures_dir = dataset["root"] / "captures"
    settings.paths.calibration_dir = dataset["root"] / "calibration"
    settings.paths.analysis_dir = dataset["root"] / "analysis"
    settings.paths.database_path = dataset["root"] / "database" / "analysis.sqlite3"

    database = Database(settings.paths.database_path)
    initialize_schema(database)
    record_repository = RecordRepository(database)
    capture_repository = CaptureRepository(database)
    calibration_repository = CalibrationRepository(database)
    analysis_repository = AnalysisRepository(database)

    record_repository.upsert(
        BASELINE_RECORD_ID,
        "2026-07-17T00:00:00+00:00",
        "completed",
        str(dataset["record_path"]),
        "2026-07-17T00:00:07+00:00",
    )
    with dataset["metadata_path"].open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            capture_repository.insert(
                MetadataRecord(
                    **{
                        **row,
                        "cycle_id": int(row["cycle_id"]),
                        "angle_deg": float(row["angle_deg"]),
                        "motor_position_deg": float(row["motor_position_deg"]),
                        "error_message": None,
                    }
                )
            )
    calibration_repository.create(_calibration_profile(dataset))
    service = AnalysisService(
        settings,
        analysis_repository,
        record_repository,
        capture_repository,
        calibration_repository,
    )
    dataset["database"] = database
    dataset["raw_hashes"] = {
        path: _sha256(path)
        for path in dataset["record_path"].rglob("*.png")
    }
    return service, dataset


def create_validated_run(
    service: AnalysisService,
    *,
    manual_review_required: bool,
):
    run = service.create(
        AnalysisCreateRequest(
            record_id=BASELINE_RECORD_ID,
            calibration_id=BASELINE_CALIBRATION_ID,
            parameters=analysis_parameters(),
            manual_review_required=manual_review_required,
        ),
        "pytest-operator",
    )
    return service.validate(run.analysis_id)


def wait_for_status(
    service: AnalysisService,
    analysis_id: str,
    statuses: set[str],
    *,
    timeout: float = 10.0,
):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = service.get_run(analysis_id)
        if run.status in statuses:
            return run
        time.sleep(0.02)
    raise AssertionError(
        f"Analysis Run 未在時限內進入 {statuses}："
        f"{service.get_run(analysis_id).model_dump()}"
    )


def assert_raw_unchanged(dataset: dict) -> None:
    assert {
        path: _sha256(path)
        for path in dataset["record_path"].rglob("*.png")
    } == dataset["raw_hashes"]
