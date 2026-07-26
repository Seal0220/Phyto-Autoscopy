from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.analysis.intrinsics.resolution_adapter import (
    build_intrinsics_snapshot,
)
from app.analysis.intrinsics.undistortion import FisheyeRemapCache
from app.analysis.pose_alignment.pose_estimator import estimate_aruco_pose


CAMERA_LABELS = {
    "top": "俯視角",
    "side": "側視角",
    "rotating": "旋臂視角",
}


def _value(source: object, name: str, default=None):
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _read_image(path: Path) -> np.ndarray | None:
    try:
        encoded = np.fromfile(path, dtype=np.uint8)
    except OSError:
        return None
    if encoded.size == 0:
        return None
    return cv2.imdecode(encoded, cv2.IMREAD_COLOR)


def _sample_views(
    views: Sequence[object],
    maximum_samples: int,
) -> list[object]:
    ordered = sorted(
        views,
        key=lambda view: (
            str(_value(view, "timestamp", "")),
            int(_value(view, "capture_id", 0)),
        ),
    )
    if len(ordered) <= maximum_samples:
        return ordered
    if maximum_samples <= 1:
        return [ordered[len(ordered) // 2]]
    indexes = {
        round(index * (len(ordered) - 1) / (maximum_samples - 1))
        for index in range(maximum_samples)
    }
    return [ordered[index] for index in sorted(indexes)]


def _snapshot_for_image(
    intrinsics: object,
    image_size: tuple[int, int],
) -> dict[str, Any]:
    if isinstance(intrinsics, Mapping):
        snapshot = dict(intrinsics)
        snapshot_size = (
            int(snapshot.get("analysis_image_width", 0)),
            int(snapshot.get("analysis_image_height", 0)),
        )
        if snapshot_size != image_size:
            raise ValueError(
                "抽樣影像解析度與已固化的內參快照不一致。"
            )
        return snapshot
    return build_intrinsics_snapshot(
        intrinsics,
        image_size,
    )


def sample_aruco_readiness(
    views: Sequence[object],
    intrinsics_by_camera: Mapping[str, object],
    aruco_settings: object,
    *,
    enabled_camera_ids: Sequence[str],
    minimum_pnp_inliers: int,
    maximum_reprojection_error_px: float,
    maximum_samples_per_camera: int = 3,
) -> dict[str, Any]:
    remap_cache = FisheyeRemapCache()
    grouped_views = {
        camera_id: [
            view
            for view in views
            if str(_value(view, "camera_id")) == camera_id
        ]
        for camera_id in enabled_camera_ids
    }
    camera_results: dict[str, dict[str, Any]] = {}
    sampled_image_count = 0
    detected_sample_count = 0
    resolved_sample_count = 0

    for camera_id in enabled_camera_ids:
        intrinsics = intrinsics_by_camera.get(camera_id)
        samples = _sample_views(
            grouped_views.get(camera_id, []),
            maximum_samples_per_camera,
        )
        failures: list[str] = []
        detections: list[dict[str, Any]] = []
        if intrinsics is None:
            failures.append("尚未建立有效內參，無法進行抽樣偵測。")

        candidate_samples = samples if intrinsics is not None else []
        for view in candidate_samples:
            image = _read_image(Path(str(_value(view, "absolute_path"))))
            if image is None:
                failures.append("抽樣影像無法讀取。")
                continue
            height, width = image.shape[:2]
            try:
                snapshot = _snapshot_for_image(
                    intrinsics,
                    (width, height),
                )
                undistorted, _ = remap_cache.undistort(image, snapshot)
                pose, detection = estimate_aruco_pose(
                    {
                        "capture_id": int(_value(view, "capture_id")),
                        "camera_id": camera_id,
                        "relative_path": str(_value(view, "relative_path")),
                        "timestamp": _value(view, "timestamp"),
                        "angle_deg": _value(view, "angle_deg"),
                        "motor_position_deg": _value(
                            view,
                            "motor_position_deg",
                        ),
                    },
                    {
                        "camera_matrix": snapshot[
                            "undistorted_camera_matrix"
                        ],
                        "distortion_coefficients": [
                            0.0,
                            0.0,
                            0.0,
                            0.0,
                            0.0,
                        ],
                        "camera_model": "opencv",
                        "width": width,
                        "height": height,
                    },
                    aruco_settings,
                    minimum_pnp_inliers=minimum_pnp_inliers,
                    maximum_reprojection_error_px=(
                        maximum_reprojection_error_px
                    ),
                    image_override=undistorted,
                )
            except (cv2.error, TypeError, ValueError) as error:
                failures.append(f"抽樣偵測失敗：{error}")
                continue

            sampled_image_count += 1
            if detection.get("marker_count", 0) > 0:
                detected_sample_count += 1
            if pose.resolved:
                resolved_sample_count += 1
            elif pose.failure_reason:
                failures.append(pose.failure_reason)
            detections.append({
                "view_id": str(_value(view, "view_id", "")),
                "marker_ids": list(detection.get("marker_ids", [])),
                "marker_count": int(detection.get("marker_count", 0)),
                "pose_resolved": bool(pose.resolved),
                "reprojection_error_px": (
                    pose.aruco_reprojection_error_px
                ),
                "status": detection.get("status", "unknown"),
            })

        camera_resolved_count = sum(
            int(item["pose_resolved"])
            for item in detections
        )
        camera_detected_count = sum(
            int(item["marker_count"] > 0)
            for item in detections
        )
        if camera_resolved_count > 0:
            status = "resolved"
        elif camera_detected_count > 0:
            status = "markers_detected"
        elif samples:
            status = "markers_missing"
        else:
            status = "unavailable"
            failures.append("沒有可供抽樣的影像。")
        camera_results[camera_id] = {
            "camera_label": CAMERA_LABELS.get(camera_id, camera_id),
            "status": status,
            "sampled_image_count": len(detections),
            "detected_sample_count": camera_detected_count,
            "resolved_sample_count": camera_resolved_count,
            "failures": list(dict.fromkeys(failures)),
            "samples": detections,
        }

    if (
        enabled_camera_ids
        and all(
            item["status"] == "resolved"
            for item in camera_results.values()
        )
    ):
        sample_status = "resolved"
    elif resolved_sample_count > 0:
        sample_status = "partial"
    elif detected_sample_count > 0:
        sample_status = "markers_detected"
    elif sampled_image_count > 0:
        sample_status = "markers_missing"
    else:
        sample_status = "unavailable"

    return {
        "sample_status": sample_status,
        "sampled_image_count": sampled_image_count,
        "detected_sample_count": detected_sample_count,
        "resolved_sample_count": resolved_sample_count,
        "cameras": camera_results,
    }


__all__ = ["sample_aruco_readiness"]
