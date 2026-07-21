from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import cv2
import numpy as np

from app.analysis.pose_alignment.aruco_world import marker_world_corners
from app.analysis.pose_alignment.models import CameraPoseResult


def _value(source: object, name: str, default=None):
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _load_image(path: Path) -> np.ndarray | None:
    try:
        encoded = np.fromfile(path, dtype=np.uint8)
    except OSError:
        return None
    if encoded.size == 0:
        return None
    return cv2.imdecode(encoded, cv2.IMREAD_COLOR)


def _scaled_camera_matrix(
    intrinsics: object,
    width: int,
    height: int,
) -> np.ndarray:
    matrix = np.asarray(
        _value(intrinsics, "camera_matrix"),
        dtype=np.float64,
    ).reshape(3, 3)
    calibration_width = float(_value(intrinsics, "width"))
    calibration_height = float(_value(intrinsics, "height"))
    scale_x = float(width) / calibration_width
    scale_y = float(height) / calibration_height
    scaled = matrix.copy()
    scaled[0, 0] *= scale_x
    scaled[0, 1] *= scale_x
    scaled[0, 2] *= scale_x
    scaled[1, 0] *= scale_y
    scaled[1, 1] *= scale_y
    scaled[1, 2] *= scale_y
    return scaled


def _aruco_dictionary(name: str):
    dictionary_id = getattr(cv2.aruco, name, None)
    if dictionary_id is None:
        raise ValueError(f"OpenCV 不支援 ArUco Dictionary：{name}")
    return cv2.aruco.getPredefinedDictionary(dictionary_id)


def _detect_markers(
    image: np.ndarray,
    dictionary_name: str,
) -> tuple[list[np.ndarray], np.ndarray | None]:
    dictionary = _aruco_dictionary(dictionary_name)
    if hasattr(cv2.aruco, "ArucoDetector"):
        parameters = cv2.aruco.DetectorParameters()
        detector = cv2.aruco.ArucoDetector(dictionary, parameters)
        corners, ids, _ = detector.detectMarkers(image)
        return corners, ids
    parameters = cv2.aruco.DetectorParameters_create()
    corners, ids, _ = cv2.aruco.detectMarkers(
        image,
        dictionary,
        parameters=parameters,
    )
    return corners, ids


def _undistort_fisheye_points(
    points: np.ndarray,
    camera_matrix: np.ndarray,
    distortion: np.ndarray,
) -> np.ndarray:
    return cv2.fisheye.undistortPoints(
        points.reshape(-1, 1, 2),
        camera_matrix,
        distortion.reshape(4, 1),
        R=np.eye(3, dtype=np.float64),
        P=camera_matrix,
    ).reshape(-1, 2)


def _rigid_matrices(
    rotation_vector: np.ndarray,
    translation_vector: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    rotation, _ = cv2.Rodrigues(rotation_vector)
    world_to_camera = np.eye(4, dtype=np.float64)
    world_to_camera[:3, :3] = rotation
    world_to_camera[:3, 3] = translation_vector.reshape(3)
    return world_to_camera, np.linalg.inv(world_to_camera)


def _project_points(
    object_points: np.ndarray,
    rotation_vector: np.ndarray,
    translation_vector: np.ndarray,
    camera_matrix: np.ndarray,
    distortion: np.ndarray,
    camera_model: str,
) -> np.ndarray:
    if camera_model == "opencv_fisheye":
        projected, _ = cv2.fisheye.projectPoints(
            object_points.reshape(-1, 1, 3),
            rotation_vector,
            translation_vector,
            camera_matrix,
            distortion.reshape(4, 1),
        )
    else:
        projected, _ = cv2.projectPoints(
            object_points,
            rotation_vector,
            translation_vector,
            camera_matrix,
            distortion,
        )
    return projected.reshape(-1, 2)


def estimate_aruco_pose(
    frame: object,
    intrinsics: object,
    aruco_settings: object,
    *,
    minimum_pnp_inliers: int,
    maximum_reprojection_error_px: float,
) -> tuple[CameraPoseResult, dict]:
    input_id = int(_value(frame, "capture_id"))
    camera_id = str(_value(frame, "camera_id"))
    relative_path = str(_value(frame, "relative_path"))
    timestamp = _value(frame, "timestamp")
    motor_angle = _value(frame, "angle_deg")
    if motor_angle is None:
        motor_angle = _value(frame, "motor_position_deg")
    base = {
        "input_id": input_id,
        "camera_id": camera_id,
        "relative_path": relative_path,
        "timestamp": timestamp,
        "motor_angle_deg": motor_angle,
    }
    image = _load_image(Path(_value(frame, "file_path")))
    if image is None:
        return (
            CameraPoseResult(
                **base,
                failure_reason="影像無法讀取。",
            ),
            {**base, "marker_ids": [], "status": "image_unreadable"},
        )

    try:
        corners, detected_ids = _detect_markers(
            image,
            str(_value(aruco_settings, "dictionary")),
        )
    except (AttributeError, cv2.error, ValueError) as exc:
        return (
            CameraPoseResult(
                **base,
                failure_reason=f"ArUco 偵測器無法使用：{exc}",
            ),
            {**base, "marker_ids": [], "status": "detector_unavailable"},
        )

    configured = marker_world_corners(aruco_settings)
    object_groups: list[np.ndarray] = []
    image_groups: list[np.ndarray] = []
    visible_ids: list[int] = []
    if detected_ids is not None:
        for marker_corners, marker_id_value in zip(
            corners,
            detected_ids.reshape(-1),
            strict=True,
        ):
            marker_id = int(marker_id_value)
            if marker_id not in configured:
                continue
            visible_ids.append(marker_id)
            object_groups.append(configured[marker_id])
            image_groups.append(
                np.asarray(marker_corners, dtype=np.float64).reshape(4, 2)
            )

    detection = {
        **base,
        "marker_ids": visible_ids,
        "marker_count": len(visible_ids),
        "corners_px": [group.tolist() for group in image_groups],
        "status": "detected" if visible_ids else "markers_missing",
    }
    if not visible_ids:
        return (
            CameraPoseResult(
                **base,
                failure_reason="影像中未偵測到世界基準 ArUco。",
            ),
            detection,
        )

    object_points = np.concatenate(object_groups).astype(np.float64)
    image_points = np.concatenate(image_groups).astype(np.float64)
    height, width = image.shape[:2]
    camera_matrix = _scaled_camera_matrix(intrinsics, width, height)
    distortion = np.asarray(
        _value(intrinsics, "distortion_coefficients"),
        dtype=np.float64,
    ).reshape(-1)
    camera_model = str(_value(intrinsics, "camera_model"))
    solve_points = image_points
    solve_distortion: np.ndarray | None = distortion
    if camera_model == "opencv_fisheye":
        try:
            solve_points = _undistort_fisheye_points(
                image_points,
                camera_matrix,
                distortion,
            )
        except cv2.error as exc:
            return (
                CameraPoseResult(
                    **base,
                    visible_marker_ids=visible_ids,
                    visible_marker_count=len(visible_ids),
                    failure_reason=f"魚眼影像去畸變失敗：{exc}",
                ),
                {**detection, "status": "undistortion_failed"},
            )
        solve_distortion = None

    try:
        planar_layout = float(np.ptp(object_points[:, 2])) <= 1e-6
        pnp_flag = (
            getattr(
                cv2,
                "SOLVEPNP_IPPE",
                cv2.SOLVEPNP_ITERATIVE,
            )
            if planar_layout
            else cv2.SOLVEPNP_ITERATIVE
        )
        success, rotation_vector, translation_vector, inliers = cv2.solvePnPRansac(
            object_points,
            solve_points,
            camera_matrix,
            solve_distortion,
            flags=pnp_flag,
            iterationsCount=200,
            reprojectionError=float(maximum_reprojection_error_px),
            confidence=0.999,
        )
    except cv2.error as exc:
        return (
            CameraPoseResult(
                **base,
                visible_marker_ids=visible_ids,
                visible_marker_count=len(visible_ids),
                failure_reason=f"ArUco PnP 求解失敗：{exc}",
            ),
            {**detection, "status": "pnp_failed"},
        )
    inlier_count = int(len(inliers)) if inliers is not None else 0
    if not success or inlier_count < minimum_pnp_inliers:
        return (
            CameraPoseResult(
                **base,
                visible_marker_ids=visible_ids,
                visible_marker_count=len(visible_ids),
                pnp_inlier_count=inlier_count,
                failure_reason=(
                    "ArUco PnP 內點不足："
                    f"{inlier_count}/{minimum_pnp_inliers}。"
                ),
            ),
            {**detection, "status": "pnp_inliers_insufficient"},
        )

    if hasattr(cv2, "solvePnPRefineLM"):
        try:
            rotation_vector, translation_vector = cv2.solvePnPRefineLM(
                object_points,
                solve_points,
                camera_matrix,
                solve_distortion,
                rotation_vector,
                translation_vector,
            )
        except cv2.error:
            pass
    projected = _project_points(
        object_points,
        rotation_vector,
        translation_vector,
        camera_matrix,
        distortion,
        camera_model,
    )
    reprojection_error = float(
        np.sqrt(np.mean(np.sum((projected - image_points) ** 2, axis=1)))
    )
    world_to_camera, camera_to_world = _rigid_matrices(
        rotation_vector,
        translation_vector,
    )
    z_direction = str(_value(aruco_settings, "z_axis_direction"))
    camera_height = float(camera_to_world[2, 3])
    camera_on_expected_side = (
        camera_height > 0
        if z_direction == "up"
        else camera_height < 0
    )
    resolved = (
        reprojection_error <= maximum_reprojection_error_px
        and camera_on_expected_side
    )
    failure_reason = None
    warnings: list[str] = []
    if not camera_on_expected_side:
        failure_reason = (
            "ArUco PnP 得到的相機位置位於世界基準背面，"
            "請確認 標籤朝向與 Z 軸方向。"
        )
        warnings.append(failure_reason)
    elif not resolved:
        failure_reason = (
            f"ArUco 重投影誤差 {reprojection_error:.3f} px 超過上限 "
            f"{maximum_reprojection_error_px:.3f} px。"
        )
        warnings.append(failure_reason)
    detection.update(
        {
            "status": (
                "resolved"
                if resolved
                else "camera_on_wrong_world_side"
                if not camera_on_expected_side
                else "reprojection_error_exceeded"
            ),
            "pnp_inlier_count": inlier_count,
            "reprojection_error_px": reprojection_error,
        }
    )
    return (
        CameraPoseResult(
            **base,
            source="aruco" if resolved else "unresolved",
            resolved=resolved,
            world_to_camera_matrix=world_to_camera.tolist() if resolved else None,
            camera_to_world_matrix=camera_to_world.tolist() if resolved else None,
            visible_marker_ids=visible_ids,
            visible_marker_count=len(visible_ids),
            pnp_inlier_count=inlier_count,
            aruco_reprojection_error_px=reprojection_error,
            quality_warnings=warnings,
            failure_reason=failure_reason,
        ),
        detection,
    )
