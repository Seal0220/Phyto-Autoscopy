from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from app.models.analysis_models import CameraPoseResult


FIXED_CAMERA_IDS = ("top", "side")


def _rotation_distance_deg(
    left: np.ndarray,
    right: np.ndarray,
) -> float:
    relative = left @ right.T
    cosine = min(
        1.0,
        max(-1.0, (float(np.trace(relative)) - 1.0) / 2.0),
    )
    return float(math.degrees(math.acos(cosine)))


def _reference_index(rotations: Sequence[np.ndarray]) -> int:
    return min(
        range(len(rotations)),
        key=lambda index: sum(
            _rotation_distance_deg(rotations[index], candidate)
            for candidate in rotations
        ),
    )


def evaluate_fixed_camera_pose_consistency(
    poses: Sequence[CameraPoseResult],
    *,
    translation_warning_mm: float = 5.0,
    rotation_warning_deg: float = 2.0,
) -> tuple[list[CameraPoseResult], dict[str, dict]]:
    """Compare fixed-camera measurements with a Run-level reference.

    Every valid ArUco measurement remains authoritative. The reference only
    detects possible mount movement and never overwrites an image pose.
    """

    updates: dict[str, CameraPoseResult] = {}
    summary: dict[str, dict] = {}
    for camera_id in FIXED_CAMERA_IDS:
        camera_poses = [
            pose
            for pose in poses
            if (
                pose.camera_id == camera_id
                and pose.valid
                and pose.rotation_matrix is not None
                and pose.translation_vector_mm is not None
            )
        ]
        reference_poses = [
            pose
            for pose in camera_poses
            if pose.pose_source in {"aruco", "feature_refined"}
        ]
        if not reference_poses:
            summary[camera_id] = {
                "status": "unavailable",
                "valid_pose_count": len(camera_poses),
                "measured_pose_count": 0,
                "warning_view_ids": [],
            }
            continue

        reference_rotations = [
            np.asarray(pose.rotation_matrix, dtype=np.float64).reshape(3, 3)
            for pose in reference_poses
        ]
        reference_translations = np.asarray(
            [pose.translation_vector_mm for pose in reference_poses],
            dtype=np.float64,
        ).reshape(-1, 3)
        reference_index = _reference_index(reference_rotations)
        reference_rotation = reference_rotations[reference_index]
        reference_translation = np.median(
            reference_translations,
            axis=0,
        )
        translation_deviations: list[float] = []
        rotation_deviations: list[float] = []
        warning_view_ids: list[str] = []

        for pose in camera_poses:
            rotation = np.asarray(
                pose.rotation_matrix,
                dtype=np.float64,
            ).reshape(3, 3)
            translation = np.asarray(
                pose.translation_vector_mm,
                dtype=np.float64,
            ).reshape(3)
            translation_deviation = float(
                np.linalg.norm(translation - reference_translation)
            )
            rotation_deviation = _rotation_distance_deg(
                rotation,
                reference_rotation,
            )
            translation_deviations.append(translation_deviation)
            rotation_deviations.append(rotation_deviation)
            warnings = list(pose.quality_warnings)
            if (
                translation_deviation > translation_warning_mm
                or rotation_deviation > rotation_warning_deg
            ):
                warning_view_ids.append(pose.view_id)
                warnings.append(
                    "固定相機姿態偏離本次分析的穩健基準，"
                    "可能發生支架位移；保留此影像自己的 ArUco 姿態。"
                )
            updates[pose.view_id] = pose.model_copy(
                update={
                    "fixed_pose_translation_deviation_mm": (
                        translation_deviation
                    ),
                    "fixed_pose_rotation_deviation_deg": (
                        rotation_deviation
                    ),
                    "quality_warnings": list(dict.fromkeys(warnings)),
                }
            )

        summary[camera_id] = {
            "status": "warning" if warning_view_ids else "stable",
            "valid_pose_count": len(camera_poses),
            "measured_pose_count": len(reference_poses),
            "reference_view_id": reference_poses[reference_index].view_id,
            "reference_rotation_matrix": (
                reference_rotation.astype(float).tolist()
            ),
            "reference_translation_vector_mm": (
                reference_translation.astype(float).tolist()
            ),
            "median_translation_deviation_mm": float(
                np.median(translation_deviations)
            ),
            "maximum_translation_deviation_mm": max(
                translation_deviations
            ),
            "median_rotation_deviation_deg": float(
                np.median(rotation_deviations)
            ),
            "maximum_rotation_deviation_deg": max(rotation_deviations),
            "translation_warning_threshold_mm": translation_warning_mm,
            "rotation_warning_threshold_deg": rotation_warning_deg,
            "warning_view_ids": warning_view_ids,
        }

    return [
        updates.get(pose.view_id, pose)
        for pose in poses
    ], summary
