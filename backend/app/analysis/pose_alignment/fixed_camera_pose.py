from __future__ import annotations

import math
from collections.abc import Callable, Sequence

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


def _reference_index(
    rotations: Sequence[np.ndarray],
    *,
    cancel_check: Callable[[], None] | None = None,
) -> int:
    """Find the angular medoid, weighting identical measurements once.

    Registered fixed-camera poses repeat across every capture. Comparing all
    copies to each other is quadratic in the image count without adding any
    information. Counts retain their original influence on the angular medoid.
    Distinct rotations are compared in bounded NumPy blocks instead of Python
    pairs, without approximating the rotation distance or averaging matrices.
    """
    if cancel_check is not None:
        cancel_check()
    unique, first_indices, counts = np.unique(
        np.asarray(rotations, dtype=np.float64).reshape(-1, 9),
        axis=0,
        return_index=True,
        return_counts=True,
    )
    if cancel_check is not None:
        cancel_check()
    if len(unique) == 1:
        return int(first_indices[0])

    # Original order preserves the first measurement when medoid scores tie.
    order = np.argsort(first_indices)
    unique, first_indices, counts = unique[order], first_indices[order], counts[order]
    scores = np.zeros(len(unique), dtype=np.float64)
    block_size = 512
    for start in range(0, len(unique), block_size):
        stop = start + block_size
        for other in range(0, len(unique), block_size):
            if cancel_check is not None:
                cancel_check()
            # trace(R1 @ R2.T) equals the inner product of their nine entries.
            angles = np.einsum("ik,jk->ij", unique[start:stop], unique[other:other + block_size])
            angles -= 1.0
            angles *= 0.5
            np.clip(angles, -1.0, 1.0, out=angles)
            np.arccos(angles, out=angles)
            scores[start:stop] += angles @ counts[other:other + block_size]
    return int(first_indices[int(np.argmin(scores))])


def evaluate_fixed_camera_pose_consistency(
    poses: Sequence[CameraPoseResult],
    *,
    translation_warning_mm: float = 5.0,
    rotation_warning_deg: float = 2.0,
    cancel_check: Callable[[], None] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[list[CameraPoseResult], dict[str, dict]]:
    """Compare fixed-camera measurements with a Run-level reference.

    Every valid measured pose remains authoritative. The reference only
    detects possible mount movement and never overwrites an image pose.
    """

    updates: dict[str, CameraPoseResult] = {}
    summary: dict[str, dict] = {}
    if cancel_check is not None:
        cancel_check()
    poses_by_camera = {
        camera_id: [
            pose
            for pose in poses
            if (
                pose.camera_id == camera_id
                and pose.valid
                and pose.rotation_matrix is not None
                and pose.translation_vector_mm is not None
            )
        ]
        for camera_id in FIXED_CAMERA_IDS
    }
    total = sum(len(items) for items in poses_by_camera.values())
    completed = 0
    if progress_callback is not None:
        progress_callback(completed, total)
    for camera_id, camera_poses in poses_by_camera.items():
        if cancel_check is not None:
            cancel_check()
        reference_poses = [
            pose
            for pose in camera_poses
            if pose.pose_source in {"aruco", "feature_refined", "rig_stereo"}
        ]
        if not reference_poses:
            summary[camera_id] = {
                "status": "unavailable",
                "valid_pose_count": len(camera_poses),
                "measured_pose_count": 0,
                "warning_view_ids": [],
            }
            completed += len(camera_poses)
            if progress_callback is not None:
                progress_callback(completed, total)
            continue

        reference_rotations = [
            np.asarray(pose.rotation_matrix, dtype=np.float64).reshape(3, 3)
            for pose in reference_poses
        ]
        reference_translations = np.asarray(
            [pose.translation_vector_mm for pose in reference_poses],
            dtype=np.float64,
        ).reshape(-1, 3)
        reference_index = _reference_index(reference_rotations, cancel_check=cancel_check)
        reference_rotation = reference_rotations[reference_index]
        reference_translation = np.median(
            reference_translations,
            axis=0,
        )
        translation_deviations: list[float] = []
        rotation_deviations: list[float] = []
        warning_view_ids: list[str] = []

        for index, pose in enumerate(camera_poses):
            if index % 256 == 0 and cancel_check is not None:
                cancel_check()
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
                    "可能發生支架位移；保留此影像自己的量測姿態。"
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
            completed += 1
            if completed % 256 == 0 and progress_callback is not None:
                progress_callback(completed, total)

        if progress_callback is not None:
            progress_callback(completed, total)

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
