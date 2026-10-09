"""Refine the reference geometry before it becomes a selectable 3DGS model."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

import numpy as np

from app.analysis.pose_alignment.model_reference import aggregate_fixed_camera_poses, fit_motor_orbit


REFERENCE_GEOMETRY_VERSION = 3


@dataclass(frozen=True, slots=True)
class ReferenceGeometryResult:
    reconstruction: object
    quality: dict[str, Any]


class _RefinementRejected(ValueError):
    """A measured regression, rather than a cancellation or software error."""

    def __init__(self, message: str, diagnostics: dict[str, Any]):
        super().__init__(message)
        self.diagnostics = diagnostics


def _holdout_observations(reconstruction, by_name, scale_anchor):
    observations = []
    for point_id, point in sorted(reconstruction.points3D.items()):
        if point_id == scale_anchor or point.track.length() < 4:
            continue
        rotating = sorted((element for element in point.track.elements
                           if by_name[reconstruction.image(element.image_id).name]["camera_id"] == "rotating"),
                          key=lambda element: element.image_id)
        if len(rotating) < 3:
            continue
        # A reproducible rotating-view observation from every tenth eligible
        # track. Other observations of this point remain available for depth.
        if point_id % 10:
            continue
        element = rotating[(point_id // 10) % len(rotating)]
        xy = reconstruction.image(element.image_id).point2D(element.point2D_idx).xy.copy()
        observations.append((point_id, element.image_id, element.point2D_idx, xy))
        if len(observations) >= 512:
            break
    return observations


def _heldout_errors(reconstruction, observations):
    errors = []
    for point_id, image_id, _, xy in observations:
        image = reconstruction.image(image_id)
        pose = image.cam_from_world().matrix()
        xyz = pose[:, :3] @ reconstruction.point3D(point_id).xyz + pose[:, 3]
        projected = reconstruction.camera(image.camera_id).img_from_cam(xyz)
        errors.append(float(np.linalg.norm(projected - xy)) if projected is not None else float("inf"))
    return np.asarray(errors)


def _validate_image_geometry(pycolmap, candidate, config, options, by_name, scale_anchor, cancel_check):
    """Hold out image observations; this is not an independent metric truth."""
    observations = _holdout_observations(candidate, by_name, scale_anchor)
    report = {"scope": "same_round_heldout_image_observations", "absolute_accuracy_verified": False,
              "sample_count": len(observations),
              "baseline": "same_training_observations_with_camera_poses_fixed"}
    if len(observations) < 12:
        return {**report, "status": "insufficient_observations"}
    validation = pycolmap.Reconstruction(candidate)
    manager = pycolmap.ObservationManager(validation)
    for _, image_id, point_index, _ in observations:
        manager.delete_observation(image_id, point_index)
    # Both alternatives must estimate point coordinates from the same training
    # observations. Comparing against full-data XYZ would give the baseline
    # access to the very pixels being held out.
    baseline_config = pycolmap.BundleAdjustmentConfig()
    for image_id in validation.reg_image_ids():
        baseline_config.add_image(image_id)
        baseline_config.set_constant_rig_from_world_pose(validation.image(image_id).frame_id)
    for camera_id in validation.cameras:
        baseline_config.set_constant_cam_intrinsics(camera_id)
    for point_id in validation.points3D:
        if point_id == scale_anchor:
            baseline_config.add_constant_point(point_id)
        else:
            baseline_config.add_variable_point(point_id)
    cancel_check()
    baseline_summary = pycolmap.create_default_bundle_adjuster(options, baseline_config, validation).solve()
    if not baseline_summary.is_solution_usable():
        raise _RefinementRejected("保留觀測的基準幾何驗證未取得有效解。",
                                  {"image_validation": {**report, "status": "unusable_baseline"}})
    before = _heldout_errors(validation, observations)
    cancel_check()
    summary = pycolmap.create_default_bundle_adjuster(options, config, validation).solve()
    cancel_check()
    if not summary.is_solution_usable():
        raise _RefinementRejected("保留觀測的姿態驗證未取得有效解。",
                                  {"image_validation": {**report, "status": "unusable_refinement"}})
    after = _heldout_errors(validation, observations)
    if not np.isfinite(before).all() or not np.isfinite(after).all():
        raise _RefinementRejected("保留觀測的姿態驗證出現無效投影。",
                                  {"image_validation": {**report, "status": "invalid_projection"}})
    before_rmse = float(np.sqrt(np.mean(before ** 2)))
    after_rmse = float(np.sqrt(np.mean(after ** 2)))
    maximum_rmse = before_rmse * 1.05 + .05
    report = {**report,
            "initial_rmse_px": before_rmse, "final_rmse_px": after_rmse,
            "maximum_accepted_rmse_px": maximum_rmse,
            "final_mean_px": float(after.mean()), "final_absolute_p95_px": float(np.percentile(after, 95)),
            "final_absolute_max_px": float(after.max())}
    if after_rmse > maximum_rmse:
        raise _RefinementRejected(
            f"姿態精修增加了保留觀測的重投影誤差（{before_rmse:.3f} → {after_rmse:.3f} px）。",
            {"image_validation": {**report, "status": "rejected"}},
        )
    return {**report, "status": "passed"}


def refine_reference_geometry(pycolmap, reconstruction, views, orbit=None, *, cancel_check) -> ReferenceGeometryResult:
    """Keep separately checked original SfM geometry if refinement regresses.

    A failed optional improvement must not discard an otherwise usable image
    reconstruction. Invalid input geometry, cancellation and unexpected
    errors remain fatal; only measured refinement rejection is recoverable.
    """
    try:
        return _refine_reference_geometry(pycolmap, reconstruction, views, orbit, cancel_check=cancel_check)
    except _RefinementRejected as rejected:
        cancel_check()
        original = pycolmap.Reconstruction(reconstruction)
        original.update_point_3d_errors()
        error = float(original.compute_mean_reprojection_error())
        stable_points = sum(point.track.length() >= 3 and np.isfinite(point.xyz).all()
                            and np.isfinite(point.error) and point.error <= 4.
                            for point in original.points3D.values())
        if not np.isfinite(error) or error > 4. or stable_points < 4:
            raise ValueError("姿態精修未通過，原始模型也缺少合格的三維幾何，無法繼續建模。") from rejected
        by_name = {view["image_name"]: view for view in views}
        original_views = []
        for image_id in original.reg_image_ids():
            image = original.image(image_id)
            pose = np.eye(4)
            pose[:3] = image.cam_from_world().matrix()
            if not np.isfinite(pose).all():
                raise ValueError("姿態精修未通過，原始模型姿態亦含無效數值。") from rejected
            original_views.append({**by_name[image.name], "pose": pose.tolist(), "point_count": int(image.num_points3D)})
        original_orbit = fit_motor_orbit(original_views)
        _, consensus = aggregate_fixed_camera_poses(original_views, orbit_radius=original_orbit["radius"])
        cancel_check()
        quality = {
            "version": REFERENCE_GEOMETRY_VERSION, "status": "kept_original", "accepted": False,
            "method": "original_image_sfm_then_motor_regression", "rejection_reason": str(rejected),
            "fallback": "validated_original_sfm", "filtered_observations": 0,
            "fixed_pose_consensus": consensus, "motor_pose_priors_used": False,
            "initial_reprojection_error_px": error, "final_reprojection_error_px": error,
            "published_reprojection_error_px": error,
            "initial_position_rmse_over_radius": original_orbit["position_rmse_over_radius"],
            "final_position_rmse_over_radius": original_orbit["position_rmse_over_radius"],
            "initial_rotation_rmse_deg": original_orbit["rotation_rmse_deg"],
            "final_rotation_rmse_deg": original_orbit["rotation_rmse_deg"],
            "initial_rotation_error_angle_source": "sfm_rotations", "rotation_error_angle_source": "sfm_rotations",
            "angle_calibration": original_orbit["angle_calibration"], "rejected_attempt": rejected.diagnostics,
            "image_validation": rejected.diagnostics["image_validation"],
            "original_geometry_validation": {"status": "passed", "stable_point_count": stable_points,
                                             "mean_reprojection_error_px": error,
                                             "scope": "same_round_sfm_geometry_checks"},
            "rotation_residual_scope": "internal_consistency_against_image_derived_orbit",
            "absolute_accuracy_verified": False, "solver_termination": "not_applied",
        }
        logging.getLogger(__name__).warning("Reference refinement rejected; keeping validated original SfM: %s", rejected)
        return ReferenceGeometryResult(original, quality)


def _refine_reference_geometry(pycolmap, reconstruction, views, orbit=None, *, cancel_check) -> ReferenceGeometryResult:
    """Refine image geometry with one observed pose per fixed camera.

    Recorded motor angles must not pull valid image poses onto an assumed
    orbit. Refine poses and points from image residuals first, then fit the
    orbit and motor calibration to the refined camera rotations.
    """
    cancel_check()
    candidate = pycolmap.Reconstruction(reconstruction)
    candidate.update_point_3d_errors()
    initial_error = float(candidate.compute_mean_reprojection_error())
    if not np.isfinite(initial_error) or int(candidate.num_points3D()) < 4:
        raise ValueError("初始模型缺少有效三維幾何，無法精修相機姿態。")
    by_name = {view["image_name"]: view for view in views}
    images = [candidate.image(image_id) for image_id in candidate.reg_image_ids()]
    rotating = [image for image in images if by_name[image.name]["camera_id"] == "rotating"]
    if len(rotating) < 6:
        raise ValueError("初始模型至少需要六張有效旋臂影像才能精修幾何。")
    centers = np.asarray([image.projection_center() for image in rotating])
    radius = float(np.median(np.linalg.norm(centers - centers.mean(axis=0), axis=1)))
    if not np.isfinite(radius) or radius <= 0:
        raise ValueError("初始模型旋轉軸的尺度無效。")
    fixed, consensus = aggregate_fixed_camera_poses(views, orbit_radius=radius)
    anchor_id = min(image.image_id for image in rotating)
    config = pycolmap.BundleAdjustmentConfig()
    for image in images:
        config.add_image(image.image_id)
        view = by_name[image.name]
        camera = view["camera_id"]
        if camera in fixed:
            candidate.frame(image.frame_id).rig_from_world = pycolmap.Rigid3d(np.asarray(fixed[camera])[:3])
            config.set_constant_rig_from_world_pose(image.frame_id)
        elif not fixed and image.image_id == anchor_id:
            # Preserve the coordinate gauge when no fixed camera registered.
            config.set_constant_rig_from_world_pose(image.frame_id)
        else:
            config.set_variable_rig_from_world_pose(image.frame_id)
    for camera_id in candidate.cameras:
        config.set_constant_cam_intrinsics(camera_id)
    # Averaging a fixed pose can expose a few false tracks or negative depths.
    # Remove them before solving; otherwise they can produce singular steps.
    manager = pycolmap.ObservationManager(candidate)
    filtered_before = manager.filter_all_points3D(4., 1.)
    if int(candidate.num_points3D()) < 4:
        raise ValueError("初始模型的有效特徵不足，無法精修幾何。")
    candidate.update_point_3d_errors()
    pre_solve_error = float(candidate.compute_mean_reprojection_error())
    # Repeated fixed frames represent one physical camera, so freezing them
    # only fixes six gauge freedoms. A stable image-derived point fixes scale;
    # it supplies neither a motor trajectory nor a metric measurement.
    stable_points = [point_id for point_id, point in candidate.points3D.items() if point.track.length() >= 3]
    if not stable_points:
        raise ValueError("初始模型缺少穩定三維參照點，無法固定幾何尺度。")
    fixed_centers = [np.linalg.inv(pose)[:3, 3] for pose in fixed.values()]
    scale_fixed = len(fixed_centers) >= 2 and np.linalg.norm(fixed_centers[0] - fixed_centers[1]) > radius * 1e-5
    scale_anchor = None if scale_fixed else min(stable_points, key=lambda point_id:
                                               candidate.point3D(point_id).error / np.sqrt(candidate.point3D(point_id).track.length()))
    for point_id in candidate.points3D:
        if point_id == scale_anchor:
            config.add_constant_point(point_id)
        else:
            config.add_variable_point(point_id)
    options = pycolmap.BundleAdjustmentOptions()
    options.refine_focal_length = options.refine_principal_point = options.refine_extra_params = False
    options.refine_sensor_from_rig = False
    options.ceres.loss_function_type = pycolmap.LossFunctionType.CAUCHY
    options.ceres.loss_function_scale = 1.
    options.ceres.solver_options.max_num_iterations = 600
    validation_quality = _validate_image_geometry(
        pycolmap, candidate, config, options, by_name, scale_anchor, cancel_check,
    )
    cancel_check()
    adjuster = pycolmap.create_default_bundle_adjuster(options, config, candidate)
    summary = adjuster.solve()
    cancel_check()
    if not summary.is_solution_usable():
        raise _RefinementRejected("初始模型姿態精修未取得有效解。", {"image_validation": validation_quality})
    candidate.update_point_3d_errors()
    final_error = float(candidate.compute_mean_reprojection_error())
    if (not np.isfinite(pre_solve_error) or not np.isfinite(final_error)
            or final_error > min(initial_error, pre_solve_error) * 1.01 + .001):
        raise _RefinementRejected("初始模型姿態精修增加了重投影誤差。", {
            "image_validation": validation_quality, "initial_reprojection_error_px": initial_error,
            "candidate_reprojection_error_px": final_error if np.isfinite(final_error) else None,
        })
    refined_views = []
    for image in images:
        pose = np.eye(4)
        pose[:3] = image.cam_from_world().matrix()
        view = by_name[image.name]
        if not np.isfinite(pose).all():
            raise _RefinementRejected("初始模型精修姿態含無效數值。", {"image_validation": validation_quality})
        if view["camera_id"] in fixed and not np.allclose(pose, fixed[view["camera_id"]], atol=1e-7):
            raise _RefinementRejected("初始模型精修改變了固定相機基準。", {"image_validation": validation_quality})
        refined_views.append({**view, "pose": pose.tolist()})
    try:
        refined_orbit = fit_motor_orbit(refined_views)
    except ValueError as error:
        raise _RefinementRejected(f"精修後的影像軌道無法使用：{error}", {"image_validation": validation_quality}) from error
    filtered_after = manager.filter_all_points3D(4., 1.)
    if int(candidate.num_points3D()) < 4:
        raise _RefinementRejected("初始模型精修後沒有足夠的有效三維點。", {"image_validation": validation_quality})
    candidate.update_point_3d_errors()
    # Initial orbit diagnostics are optional. They never gate the image-only
    # solve, unlike the final calibrated orbit required for downstream use.
    if orbit is None:
        try:
            orbit = fit_motor_orbit(views)
        except ValueError:
            orbit = {}
    quality = {
        "version": REFERENCE_GEOMETRY_VERSION, "status": "completed", "accepted": True,
        "method": "image_bundle_adjustment_then_motor_regression", "initial_reprojection_error_px": initial_error,
        "pre_solve_reprojection_error_px": pre_solve_error,
        "final_reprojection_error_px": final_error,
        "filtered_observations": int(filtered_before + filtered_after),
        "fixed_pose_consensus": consensus, "motor_pose_priors_used": False, "scale_anchor_point_id": scale_anchor,
        "initial_position_rmse_over_radius": orbit.get("position_rmse_over_radius"),
        "final_position_rmse_over_radius": refined_orbit["position_rmse_over_radius"],
        "initial_rotation_rmse_deg": orbit.get("rotation_rmse_deg"),
        "initial_rotation_error_angle_source": orbit.get("rotation_error_angle_source", "recorded_motor_angles"),
        "final_rotation_rmse_deg": refined_orbit["rotation_rmse_deg"],
        "rotation_error_angle_source": "sfm_rotations", "angle_calibration": refined_orbit["angle_calibration"],
        "published_reprojection_error_px": float(candidate.compute_mean_reprojection_error()),
        "image_validation": validation_quality,
        "rotation_residual_scope": "internal_consistency_against_image_derived_orbit",
        "absolute_accuracy_verified": False,
        "solver_termination": str(getattr(getattr(summary, "ceres_summary", summary), "termination_type", "unknown")),
    }
    return ReferenceGeometryResult(candidate, quality)
