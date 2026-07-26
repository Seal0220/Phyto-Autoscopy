from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.analysis.reconstruction.dataset_adapter import PreparedRoundDataset


@dataclass(frozen=True, slots=True)
class BundleAdjustmentResult:
    reconstruction: object
    quality: dict[str, Any]
    refined_camera_poses: list[dict[str, Any]]


def _rotation_distance_deg(
    first: np.ndarray,
    second: np.ndarray,
) -> float:
    relative = first.T @ second
    cosine = float(
        np.clip(
            (np.trace(relative) - 1.0) / 2.0,
            -1.0,
            1.0,
        )
    )
    return math.degrees(math.acos(cosine))


def _camera_center(world_to_camera: np.ndarray) -> np.ndarray:
    rotation = world_to_camera[:3, :3]
    translation = world_to_camera[:3, 3]
    return -(rotation.T @ translation)


def _summary_value(
    summary: object,
    name: str,
    default: object = None,
) -> object:
    value = getattr(summary, name, default)
    return value() if callable(value) else value


def refine_sparse_camera_poses(
    pycolmap: object,
    reconstruction: object,
    dataset: PreparedRoundDataset,
    *,
    maximum_translation_change_mm: float = 50.0,
    maximum_rotation_change_deg: float = 10.0,
) -> BundleAdjustmentResult:
    if int(reconstruction.num_points3D()) < 4:
        return BundleAdjustmentResult(
            reconstruction=reconstruction,
            quality={
                "enabled": True,
                "status": "skipped",
                "reason": "稀疏三維點不足，未執行受約束姿態精修。",
            },
            refined_camera_poses=[],
        )

    candidate = pycolmap.Reconstruction(reconstruction)
    config = pycolmap.BundleAdjustmentConfig()
    view_by_image_id = {
        image_id: view
        for image_id, view in enumerate(dataset.views, start=1)
    }
    original_matrices = {
        image_id: view.world_to_camera_matrix.copy()
        for image_id, view in view_by_image_id.items()
    }

    for camera_id in candidate.cameras.keys():
        config.set_constant_cam_intrinsics(int(camera_id))

    pose_priors = {}
    for image_id, view in view_by_image_id.items():
        image = candidate.image(image_id)
        config.add_image(image_id)
        if view.camera_id in {"top", "side"}:
            config.set_constant_rig_from_world_pose(image.frame_id)
            continue
        config.set_variable_rig_from_world_pose(image.frame_id)
        sigma_mm = (
            8.0
            if view.pose_source in {"aruco", "feature_refined"}
            else 25.0
        )
        pose_priors[image_id] = pycolmap.PosePrior(
            position=_camera_center(view.world_to_camera_matrix),
            position_covariance=np.eye(3, dtype=np.float64)
            * sigma_mm ** 2,
            coordinate_system=(
                pycolmap.PosePriorCoordinateSystem.CARTESIAN
            ),
        )

    for point3d_id in candidate.points3D.keys():
        config.add_variable_point(int(point3d_id))

    options = pycolmap.BundleAdjustmentOptions()
    options.refine_focal_length = False
    options.refine_principal_point = False
    options.refine_extra_params = False
    options.loss_function_type = pycolmap.LossFunctionType.CAUCHY
    options.loss_function_scale = 2.0
    prior_options = pycolmap.PosePriorBundleAdjustmentOptions()
    prior_options.use_robust_loss_on_prior_position = True
    prior_options.prior_position_loss_scale = 2.7954834829151074

    adjuster = pycolmap.create_pose_prior_bundle_adjuster(
        options,
        prior_options,
        config,
        pose_priors,
        candidate,
    )
    summary = adjuster.solve()
    refined_camera_poses: list[dict[str, Any]] = []
    maximum_translation = 0.0
    maximum_rotation = 0.0

    for image_id, view in view_by_image_id.items():
        refined = np.asarray(
            candidate.image(image_id).cam_from_world().matrix(),
            dtype=np.float64,
        )
        refined_matrix = np.eye(4, dtype=np.float64)
        refined_matrix[:3, :] = refined
        original = original_matrices[image_id]
        translation_change = float(
            np.linalg.norm(
                _camera_center(refined_matrix)
                - _camera_center(original)
            )
        )
        rotation_change = _rotation_distance_deg(
            original[:3, :3],
            refined_matrix[:3, :3],
        )
        maximum_translation = max(
            maximum_translation,
            translation_change,
        )
        maximum_rotation = max(maximum_rotation, rotation_change)
        if view.camera_id in {"top", "side"} and (
            translation_change > 1e-6
            or rotation_change > 1e-6
        ):
            raise RuntimeError(
                "受約束姿態精修改變了固定相機世界基準。"
            )
        if view.camera_id == "rotating" and (
            translation_change > maximum_translation_change_mm
            or rotation_change > maximum_rotation_change_deg
        ):
            raise RuntimeError(
                f"旋臂姿態精修偏離 ArUco 先驗過大："
                f"{translation_change:.2f} mm、{rotation_change:.2f}°。"
            )
        view.world_to_camera_matrix[:] = refined_matrix
        refined_camera_poses.append({
            "view_id": view.view_id,
            "camera_id": view.camera_id,
            "world_to_camera_matrix": refined_matrix.tolist(),
            "translation_change_mm": translation_change,
            "rotation_change_deg": rotation_change,
            "refined": bool(
                view.camera_id == "rotating"
                and (
                    translation_change > 1e-9
                    or rotation_change > 1e-9
                )
            ),
        })

    return BundleAdjustmentResult(
        reconstruction=candidate,
        quality={
            "enabled": True,
            "status": "completed",
            "fixed_camera_poses_constant": True,
            "camera_intrinsics_constant": True,
            "world_scale_source": "fixed_aruco_camera_poses",
            "rotating_position_priors": len(pose_priors),
            "maximum_translation_change_mm": maximum_translation,
            "maximum_rotation_change_deg": maximum_rotation,
            "initial_reprojection_error_px": float(
                reconstruction.compute_mean_reprojection_error()
            ),
            "final_reprojection_error_px": float(
                candidate.compute_mean_reprojection_error()
            ),
            "successful_steps": int(
                _summary_value(summary, "num_successful_steps", 0) or 0
            ),
            "unsuccessful_steps": int(
                _summary_value(summary, "num_unsuccessful_steps", 0) or 0
            ),
            "termination_type": str(
                _summary_value(summary, "termination_type", "unknown")
            ),
        },
        refined_camera_poses=refined_camera_poses,
    )


__all__ = [
    "BundleAdjustmentResult",
    "refine_sparse_camera_poses",
]
