"""A model coordinate frame, fitted motor orbit and metric camera registration."""
from __future__ import annotations

from collections.abc import Mapping, Sequence

import cv2
import numpy as np

from app.analysis.pose_alignment.models import CameraPoseResult, PoseAlignmentResult
from app.analysis.pose_alignment.pipeline import _quality_summary


def fit_motor_orbit(views: Sequence[Mapping]) -> dict:
    registered = [v for v in views if v.get("camera_id") == "rotating"
                  and v.get("pose") is not None and v.get("angle_deg") is not None]
    if len(registered) < 6:
        raise ValueError("旋臂模型至少需要六個不同角度的有效姿態，才能估計旋轉軸。")
    poses = np.asarray([v["pose"] for v in registered], dtype=np.float64)
    centers = np.linalg.inv(poses)[:, :3, 3]
    angles = np.deg2rad([v["angle_deg"] for v in registered])
    # A circular trajectory is linear in cos/sin of the measured motor angle.
    design = np.column_stack((np.ones(len(angles)), np.cos(angles), np.sin(angles)))
    if np.linalg.cond(design) > 20:
        raise ValueError("旋臂角度分布不足，無法可靠估計旋轉軸。")
    center, cosine, sine = np.linalg.lstsq(design, centers, rcond=None)[0]
    radius = (np.linalg.norm(cosine) + np.linalg.norm(sine)) / 2
    if not np.isfinite(radius) or radius < 1e-8:
        raise ValueError("旋臂相機沒有可用的環繞位移。")
    axis = np.cross(cosine, sine)
    axis /= max(np.linalg.norm(axis), 1e-12)
    shape_error = max(abs(np.linalg.norm(cosine) - np.linalg.norm(sine)) / radius,
                      abs(np.dot(cosine, sine)) / radius**2)
    residual = float(np.sqrt(np.mean(np.sum((design @ np.vstack((center, cosine, sine)) - centers)**2, axis=1))))
    if shape_error > .1 or residual / radius > .1:
        raise ValueError("模型相機軌跡與馬達圓周不一致，請檢查旋臂影像、角度或相機安裝。")
    camera_to_world = np.linalg.inv(poses)
    # Average the motor-normalized orientations instead of anchoring the whole
    # trajectory to one noisy SfM image.
    zero_rotations = [cv2.Rodrigues(-axis * (angle - angles[0]))[0] @ pose[:3, :3]
                      for angle, pose in zip(angles, camera_to_world)]
    left, _, right = np.linalg.svd(np.sum(zero_rotations, axis=0))
    mean_rotation = left @ np.diag([1., 1., np.linalg.det(left @ right)]) @ right
    cosine_direction = cosine / np.linalg.norm(cosine)
    sine_direction = np.cross(axis, cosine_direction)
    base = np.eye(4)
    base[:3, :3] = mean_rotation
    base[:3, 3] = center + radius * (np.cos(angles[0]) * cosine_direction + np.sin(angles[0]) * sine_direction)
    orientation_errors = []
    for angle, pose in zip(angles, poses):
        rotation = cv2.Rodrigues(axis * (angle - angles[0]))[0]
        delta = (rotation @ base[:3, :3]).T @ np.linalg.inv(pose)[:3, :3]
        orientation_errors.append(np.rad2deg(np.arccos(np.clip((np.trace(delta) - 1) / 2, -1, 1))))
    orientation_error = float(np.sqrt(np.mean(np.square(orientation_errors))))
    # The fitted orbit supplies initial poses to subsequent constrained bundle
    # adjustment. Keep its residuals visible rather than treating it as ground truth.
    if orientation_error > 10:
        raise ValueError("旋臂姿態旋轉與馬達角度不一致，無法沿用旋轉軸。")
    return {"center": center.tolist(), "direction": axis.tolist(), "radius": float(radius),
            "angle_deg": float(np.rad2deg(angles[0])), "base_camera_to_world": base.tolist(),
            "position_rmse_over_radius": residual / radius, "rotation_rmse_deg": orientation_error,
            "quality_warnings": ["旋臂軸線含 SfM 估計誤差，後續姿態仍需多視角精修。"] if residual / radius > .05 or orientation_error > 3 else [],
            "source": "rotating_sfm_and_motor_angles", "coordinate_unit": "relative"}


def model_camera_pose(points_3d, points_2d, camera_matrix, threshold_px: float) -> tuple[np.ndarray, dict]:
    objects = np.asarray(points_3d, dtype=np.float64).reshape(-1, 3)
    pixels = np.asarray(points_2d, dtype=np.float64).reshape(-1, 2)
    if len(objects) < 4 or len(objects) != len(pixels) or not np.isfinite(objects).all() or not np.isfinite(pixels).all():
        raise ValueError("模型對齊至少需要四組有效的三維與影像對應點。")
    if np.linalg.matrix_rank(objects - objects.mean(axis=0), tol=1e-8) < 2:
        raise ValueError("模型參照點不可集中在同一直線，請改選分散的位置。")
    matrix = np.asarray(camera_matrix, dtype=np.float64).reshape(3, 3)
    if len(objects) == 4:
        result = cv2.solvePnPGeneric(objects, pixels, matrix, None, flags=cv2.SOLVEPNP_AP3P)
        candidates = list(zip(result[1], result[2])) if result[0] else []
    else:
        ok, rvec, tvec, _ = cv2.solvePnPRansac(objects, pixels, matrix, None,
            flags=cv2.SOLVEPNP_EPNP, iterationsCount=300, reprojectionError=threshold_px, confidence=.999)
        candidates = [(rvec, tvec)] if ok else []
    valid = []
    best_indices = []
    for rvec, tvec in candidates:
        rotation = cv2.Rodrigues(rvec)[0]
        projected = cv2.projectPoints(objects, rvec, tvec, matrix, None)[0].reshape(-1, 2)
        depth = (objects @ rotation.T + np.asarray(tvec).reshape(3))[:, 2]
        errors = np.linalg.norm(projected - pixels, axis=1)
        indices = np.flatnonzero((errors <= threshold_px) & (depth > 1e-8))
        if len(indices) > len(best_indices):
            best_indices = indices.tolist()
        if len(indices) < 4:
            continue
        rvec, tvec = cv2.solvePnPRefineLM(objects[indices], pixels[indices], matrix, None, rvec, tvec)
        pose = np.eye(4)
        pose[:3, :3] = cv2.Rodrigues(rvec)[0]
        pose[:3, 3] = tvec.reshape(3)
        projected = cv2.projectPoints(objects, rvec, tvec, matrix, None)[0].reshape(-1, 2)
        errors = np.linalg.norm(projected - pixels, axis=1)
        depth = (objects @ pose[:3, :3].T + pose[:3, 3])[:, 2]
        indices = np.flatnonzero((errors <= threshold_px) & (depth > 1e-8))
        if len(indices) < 4:
            continue
        if any(np.allclose(pose, item[0], atol=1e-5) for item in valid):
            continue
        valid.append((pose, {"inlier_indices": indices.tolist(),
                             "rmse_px": float(np.sqrt(np.mean(errors[indices]**2)))}))
    if not valid:
        raise ValueError(f"模型對齊未通過幾何檢查：有效參照點 {len(best_indices)}/{len(objects)} 組，至少需要四組。")
    valid.sort(key=lambda item: item[1]["rmse_px"])
    if len(valid) > 1 and valid[1][1]["rmse_px"] <= valid[0][1]["rmse_px"] + .5:
        raise ValueError("模型對齊存在多個相機姿態解，請再加一組分散的參照點。")
    return valid[0]


def metric_model_registration(reference: Mapping, fixed: Mapping, settings: Mapping) -> dict:
    poses = {camera: np.asarray(fixed[camera], dtype=np.float64).reshape(4, 4) for camera in ("top", "side")}
    centers = {camera: np.linalg.inv(pose)[:3, 3] for camera, pose in poses.items()}
    distance = np.linalg.norm(centers["side"] - centers["top"])
    if distance < 1e-8 or not np.isfinite(distance):
        raise ValueError("模型中的雙鏡頭位置無法建立尺度。")
    scale = float(settings["baseline_mm"]) / distance
    orbit = reference["orbit"]
    axis = np.asarray(orbit["direction"])
    top_direction = np.linalg.inv(poses["top"])[:3, 2]
    if np.dot(axis, top_direction) > 0:
        axis = -axis
    inclination = float(np.rad2deg(np.arccos(np.clip(-np.dot(axis, top_direction), -1, 1))))
    if inclination > 25:
        raise ValueError("俯視相機與模型旋轉軸不一致，請確認參照點。")
    horizontal = centers["side"] - centers["top"]
    horizontal -= np.dot(horizontal, axis) * axis
    if np.linalg.norm(horizontal) < 1e-8:
        raise ValueError("雙鏡頭與旋轉軸的幾何配置退化。")
    horizontal /= np.linalg.norm(horizontal)
    rotation = np.vstack((horizontal, np.cross(axis, horizontal), axis))
    axis_center = np.asarray(orbit["center"])
    shift = -scale * rotation @ axis_center
    shift[2] += float(settings["top_height_mm"]) - (scale * rotation @ centers["top"] + shift)[2]

    def transform(pose):
        pose = np.asarray(pose)
        result = np.eye(4)
        result[:3, :3] = pose[:3, :3] @ rotation.T
        result[:3, 3] = scale * pose[:3, 3] - result[:3, :3] @ shift
        return result.tolist()

    base_pose = transform(np.linalg.inv(np.asarray(orbit["base_camera_to_world"])))
    metric_orbit = {**orbit, "center": (scale * rotation @ axis_center + shift).tolist(),
                    "direction": (rotation @ np.asarray(orbit["direction"])).tolist(),
                    "radius": scale * orbit["radius"], "coordinate_unit": "millimetre",
                    "base_camera_to_world": np.linalg.inv(base_pose).tolist()}
    transformed = {camera: transform(pose) for camera, pose in poses.items()}
    side_axis = np.linalg.inv(np.asarray(transformed["side"]))[:3, 2]
    elevation = float(np.rad2deg(np.arctan2(abs(side_axis[2]), np.linalg.norm(side_axis[:2]))))
    if elevation > float(settings["maximum_side_elevation_deg"]):
        raise ValueError("側視相機對齊模型後的仰俯角超出設定，請確認參照點。")
    quality = {"scale_source": "model_reference_and_measured_stereo_baseline",
               "baseline_mm": float(settings["baseline_mm"]), "relative_to_mm_scale": scale,
               "rotation_axis": metric_orbit, "model_to_world": {"scale": scale, "rotation": rotation.tolist(), "translation": shift.tolist()},
               "top_axis_inclination_deg": inclination, "side_elevation_deg": elevation,
               "coordinate_frame": "rotation_axis_with_measured_top_height"}
    return {"poses": transformed, "quality": quality, "orbit": metric_orbit,
            "reference_poses": {v["view_id"]: transform(v["pose"]) for v in reference["views"] if v.get("pose") is not None}}


def align_model_camera_poses(frames: Sequence[Mapping], registration: Mapping, *, required_camera_ids: Sequence[str]) -> PoseAlignmentResult:
    orbit = registration["orbit"]
    axis, center = np.asarray(orbit["direction"]), np.asarray(orbit["center"])
    base = np.asarray(orbit["base_camera_to_world"])
    poses = []
    for frame in frames:
        camera = frame["camera_id"]
        angle = frame.get("angle_deg")
        if angle is None:
            angle = frame.get("motor_position_deg")
        pose = None
        source = "unresolved"
        if camera in registration["poses"]:
            pose, source = np.asarray(registration["poses"][camera]), "rig_stereo"
        elif frame.get("view_id") in registration["reference_poses"]:
            pose, source = np.asarray(registration["reference_poses"][frame["view_id"]]), "sfm"
        elif camera == "rotating" and angle is not None:
            rotation = cv2.Rodrigues(axis * np.deg2rad(float(angle) - orbit["angle_deg"]))[0]
            camera_to_world = np.eye(4)
            camera_to_world[:3, :3] = rotation @ base[:3, :3]
            camera_to_world[:3, 3] = center + rotation @ (base[:3, 3] - center)
            pose, source = np.linalg.inv(camera_to_world), "motor_prior"
        poses.append(CameraPoseResult(input_id=frame["capture_id"], camera_id=camera,
            relative_path=frame["relative_path"], timestamp=frame.get("timestamp"), motor_angle_deg=angle,
            source=source, resolved=pose is not None, world_to_camera_matrix=pose.tolist() if pose is not None else None,
            camera_to_world_matrix=np.linalg.inv(pose).tolist() if pose is not None else None,
            sfm_match_count=1 if source == "sfm" else 0,
            quality_warnings=list(orbit.get("quality_warnings", [])) if camera == "rotating" else [],
            failure_reason=None if pose is not None else "缺少模型姿態或馬達角度。"))
    quality = _quality_summary(poses, required_camera_ids, {})
    return PoseAlignmentResult(pose_estimation_version="rotating_model_reference_v1",
        aruco_alignment_status=quality.status, camera_poses=poses, fixed_camera_poses=registration["poses"], quality=quality)
