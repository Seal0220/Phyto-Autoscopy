"""Measure saved fixed-camera image tips without editing their reference models."""
from __future__ import annotations

import numpy as np

from app.analysis.reconstruction.multiview import robust_multiview_triangulate


METRIC_TIP_VERSION = 1


def measure_image_tip(landmark, views, poses, intrinsics, *, maximum_error_px=5.):
    if not landmark.image_tip_confirmed:
        return landmark
    by_view = {view.view_id: view for view in views}
    by_pose = {pose.view_id: pose for pose in poses if pose.valid}
    observations = landmark.image_observations
    quality = {"version": METRIC_TIP_VERSION, "coordinate_unit": "millimetre",
               "absolute_accuracy_verified": False}
    try:
        selected = [by_view[item["view_id"]] for item in observations]
        if (len(selected) != 2 or {view.camera_id for view in selected} != {"top", "side"}
                or len({view.snapshot_id or view.timestamp for view in selected}) != 1):
            raise ValueError("毫米量測需要同一組俯視與側視的尖端標記。")
        projections, matrices, cameras = [], [], []
        for observation, view in zip(observations, selected):
            pose = by_pose.get(view.view_id)
            if pose is None or pose.rotation_matrix is None or pose.translation_vector_mm is None:
                quality["status"] = "missing_camera_pose"
                raise ValueError("固定鏡頭量測校正尚未通過，已保留影像尖端。")
            camera = view.camera_id
            matrix = np.column_stack((pose.rotation_matrix, pose.translation_vector_mm))
            pixels = [observation["x_px"], observation["y_px"]]
            if (not np.isfinite(pixels).all() or not 0 <= pixels[0] < view.image_width
                    or not 0 <= pixels[1] < view.image_height):
                raise ValueError("尖端量測標記超出影像範圍。")
            projections.append(np.asarray(intrinsics[camera]["undistorted_camera_matrix"]) @ matrix)
            matrices.append(matrix)
            cameras.append(camera)
        result = robust_multiview_triangulate(projections,
            [(item["x_px"], item["y_px"]) for item in observations],
            camera_ids=cameras, rejection_threshold_px=maximum_error_px)
        errors = np.asarray(result.reprojection_errors_px)
        if (not all(result.used_observations) or not np.isfinite(errors).all()
                or max(errors) > maximum_error_px
                or any((matrix @ np.append(result.point, 1.))[2] <= 0 for matrix in matrices)):
            raise ValueError("尖端標記未通過雙鏡頭重投影或正深度檢查，已保留影像標記。")
        quality.update(status="accepted", aggregation=result.quality,
                       reprojection_errors_px=errors.tolist(), maximum_error_px=float(maximum_error_px))
        return landmark.model_copy(update={"valid": True, "x_mm": float(result.point[0]),
            "y_mm": float(result.point[1]), "z_mm": float(result.point[2]),
            "mean_reprojection_error_px": float(errors.mean()), "maximum_reprojection_error_px": float(errors.max()),
            "detection_type": "manual" if landmark.manually_corrected else "triangulated",
            "failure_reason": None, "tracking": {**landmark.tracking, "metric_measurement": quality}})
    except (KeyError, ValueError) as error:
        quality.setdefault("status", "rejected")
        quality["reason"] = str(error)
        return landmark.model_copy(update={"valid": False, "x_mm": None, "y_mm": None, "z_mm": None,
            "mean_reprojection_error_px": None, "maximum_reprojection_error_px": None,
            "failure_reason": str(error), "tracking": {**landmark.tracking, "metric_measurement": quality}})
