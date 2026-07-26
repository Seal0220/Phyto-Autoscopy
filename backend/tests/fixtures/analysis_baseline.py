from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np


FRAME_COUNT = 8
IMAGE_SIZE = (160, 120)
BASELINE_RECORD_ID = "record_analysis_baseline"
BASELINE_CALIBRATION_ID = "calibration_analysis_baseline"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_png(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded_ok, encoded = cv2.imencode(".png", image)
    if not encoded_ok:
        raise RuntimeError(f"無法建立基準影像：{path}")
    path.write_bytes(encoded.tobytes())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _projection_payload() -> dict:
    camera_matrix = [
        [400.0, 0.0, 80.0],
        [0.0, 400.0, 60.0],
        [0.0, 0.0, 1.0],
    ]
    return {
        "calibration_id": BASELINE_CALIBRATION_ID,
        "status": "valid",
        "valid": True,
        "image_width": IMAGE_SIZE[0],
        "image_height": IMAGE_SIZE[1],
        "top_camera_identifier": "top",
        "side_camera_identifier": "side",
        "top_camera_matrix": camera_matrix,
        "side_camera_matrix": camera_matrix,
        "top_distortion_coefficients": [0.0, 0.0, 0.0, 0.0, 0.0],
        "side_distortion_coefficients": [0.0, 0.0, 0.0, 0.0, 0.0],
        "rotation_matrix": [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        "translation_vector": [-10.0, 0.0, 0.0],
        "top_projection_matrix": [
            [400.0, 0.0, 80.0, 0.0],
            [0.0, 400.0, 60.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
        ],
        "side_projection_matrix": [
            [400.0, 0.0, 80.0, -4000.0],
            [0.0, 400.0, 60.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
        ],
        "world_transform_matrix": [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        "fixture_notice": (
            "這是測試用合成校正，不是論文公開的校正參數，"
            "不得用於實際測量。"
        ),
    }


def create_analysis_baseline(root: Path) -> dict:
    """Materialize a small fixed stereo dataset with known labels and geometry."""

    root = root.resolve()
    record_path = root / "captures" / BASELINE_RECORD_ID
    calibration_path = (
        root
        / "calibration"
        / BASELINE_CALIBRATION_ID
        / "calibration.json"
    )
    record_path.mkdir(parents=True, exist_ok=False)

    start = datetime(2026, 7, 17, tzinfo=timezone.utc)
    metadata_rows: list[dict] = []
    pairs: list[dict] = []
    manual_labels: list[dict] = []
    known_world_points: list[dict] = []
    raw_paths: list[Path] = []

    for frame_id in range(1, FRAME_COUNT + 1):
        timestamp = (start + timedelta(seconds=frame_id - 1)).isoformat()
        top_relative = (
            f"modes/baseline/top/"
            f"cycle_{frame_id:06d}_capture_{frame_id:06d}.png"
        )
        side_relative = (
            f"modes/baseline/side/"
            f"cycle_{frame_id:06d}_capture_{frame_id:06d}.png"
        )
        top_path = record_path / top_relative
        side_path = record_path / side_relative
        top_image = np.zeros((IMAGE_SIZE[1], IMAGE_SIZE[0], 3), dtype=np.uint8)
        side_image = np.zeros_like(top_image)

        top_point = None
        side_point = None
        if frame_id >= 3:
            point_index = frame_id - 3
            world_x = float(-20 + point_index * 5)
            world_y = float(-30 + point_index)
            world_z = 400.0
            top_point = [world_x + 80.0, world_y + 60.0]
            side_point = [top_point[0] - 10.0, top_point[1]]
            cv2.line(
                top_image,
                (80, 108),
                tuple(int(round(value)) for value in top_point),
                (255, 255, 255),
                5,
            )
            cv2.line(
                side_image,
                (82, 108),
                tuple(int(round(value)) for value in side_point),
                (255, 255, 255),
                5,
            )
            cv2.circle(
                top_image,
                tuple(int(round(value)) for value in top_point),
                4,
                (255, 255, 255),
                -1,
            )
            cv2.circle(
                side_image,
                tuple(int(round(value)) for value in side_point),
                4,
                (255, 255, 255),
                -1,
            )
            known_world_points.append({
                "frame_id": frame_id,
                "x_mm": world_x,
                "y_mm": world_y,
                "z_mm": world_z,
            })
            manual_labels.extend([
                {
                    "frame_id": frame_id,
                    "camera_id": "top",
                    "x_px": top_point[0],
                    "y_px": top_point[1],
                },
                {
                    "frame_id": frame_id,
                    "camera_id": "side",
                    "x_px": side_point[0],
                    "y_px": side_point[1],
                },
            ])

        _write_png(top_path, top_image)
        _write_png(side_path, side_image)
        raw_paths.extend([top_path, side_path])

        for camera_id, camera_name, relative_path in (
            ("top", "CHLOROCULUS EYE-TOP", top_relative),
            ("side", "CHLOROCULUS EYE-SIDE", side_relative),
        ):
            metadata_rows.append({
                "project_name": "Phyto-Autoscopy",
                "project_name_zh": "綠色自視症",
                "device_name": "CHLOROCULUS",
                "record_id": BASELINE_RECORD_ID,
                "cycle_id": frame_id,
                "camera_id": camera_id,
                "camera_name": camera_name,
                "timestamp": timestamp,
                "angle_deg": 0.0,
                "motor_position_deg": 0.0,
                "file_path": relative_path,
                "status": "success",
                "error_message": "",
            })
        pairs.append({
            "frame_id": frame_id,
            "cycle_id": frame_id,
            "top_path": top_relative,
            "side_path": side_relative,
            "timestamp_delta_ms": 0.0,
            "pair_status": "paired",
        })

    fieldnames = list(metadata_rows[0])
    metadata_path = record_path / "metadata.csv"
    with metadata_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(metadata_rows)

    _write_json(
        record_path / "config.json",
        {
            "record_id": BASELINE_RECORD_ID,
            "status": "completed",
            "created_at": start.isoformat(),
            "ended_at": (start + timedelta(seconds=FRAME_COUNT - 1)).isoformat(),
            "record_path": record_path.as_posix(),
            "fixture_notice": "小型合成資料，不代表真實植物運動。",
        },
    )
    _write_json(calibration_path, _projection_payload())

    manifest = {
        "dataset_id": "analysis_baseline_v1",
        "record_id": BASELINE_RECORD_ID,
        "calibration_id": BASELINE_CALIBRATION_ID,
        "image_size": list(IMAGE_SIZE),
        "frame_count": FRAME_COUNT,
        "pairs": pairs,
        "manual_tip_labels": manual_labels,
        "known_world_points": known_world_points,
        "expected_trajectory_range_mm": {
            "x": [-20.0, 5.0],
            "y": [-30.0, -25.0],
            "z": [399.99, 400.01],
        },
        "raw_sha256": {
            path.relative_to(record_path).as_posix(): _sha256(path)
            for path in raw_paths
        },
        "method_scope": "fixed",
        "research_disclaimer": (
            "此資料集僅驗證測量管線，不推論植物是否具有意識。"
        ),
    }
    manifest_path = root / "analysis_baseline_manifest.json"
    _write_json(manifest_path, manifest)
    return {
        "root": root,
        "record_path": record_path,
        "metadata_path": metadata_path,
        "calibration_path": calibration_path,
        "manifest_path": manifest_path,
        "manifest": manifest,
    }
