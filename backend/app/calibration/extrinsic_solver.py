from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Sequence

import cv2
import numpy as np

from app.calibration.observation_graph import observation_graph_status
from app.calibration.motion_model import rotating_camera_pose
from app.calibration.quality_metrics import extrinsic_quality_status
from app.calibration.rotation_axis_solver import fit_rotation_axis
from app.calibration.world_alignment import default_world_alignment


def _camera_from_board(
    detection: dict,
    intrinsics: object,
) -> tuple[np.ndarray, float]:
    objects = np.asarray(detection.get("object_points"), dtype=np.float64).reshape(-1, 3)
    images = np.asarray(detection.get("image_points"), dtype=np.float64).reshape(-1, 1, 2)
    if len(objects) < 6 or len(objects) != len(images):
        raise ValueError("外參觀測的校正板角點資料不足。")
    matrix = _camera_matrix_for_detection(detection, intrinsics)
    distortion = np.asarray(intrinsics.distortion_coefficients, dtype=np.float64)
    if intrinsics.camera_model == "opencv_fisheye":
        pnp_points = cv2.fisheye.undistortPoints(
            images,
            matrix,
            distortion,
            P=matrix,
        )
        effective_distortion = None
    else:
        pnp_points = images
        effective_distortion = distortion
    success, rotation_vector, translation = cv2.solvePnP(
        objects,
        pnp_points,
        matrix,
        effective_distortion,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not success:
        raise ValueError("外參觀測的相機姿態求解失敗。")
    rotation, _ = cv2.Rodrigues(rotation_vector)
    transform = np.eye(4, dtype=np.float64)
    transform[:3, :3] = rotation
    transform[:3, 3] = translation.reshape(3)
    if intrinsics.camera_model == "opencv_fisheye":
        projected, _ = cv2.fisheye.projectPoints(
            objects.reshape(-1, 1, 3),
            rotation_vector,
            translation,
            matrix,
            distortion,
        )
    else:
        projected, _ = cv2.projectPoints(
            objects,
            rotation_vector,
            translation,
            matrix,
            distortion,
        )
    errors = np.linalg.norm(projected.reshape(-1, 2) - images.reshape(-1, 2), axis=1)
    return transform, float(np.sqrt(np.mean(errors * errors)))


def _camera_matrix_for_detection(
    detection: dict,
    intrinsics: object,
) -> np.ndarray:
    matrix = np.asarray(intrinsics.camera_matrix, dtype=np.float64).copy()
    width = int(detection.get("image_width") or intrinsics.width)
    height = int(detection.get("image_height") or intrinsics.height)
    if width <= 0 or height <= 0:
        raise ValueError("外參觀測的影像解析度無效。")
    scale_x = width / float(intrinsics.width)
    scale_y = height / float(intrinsics.height)
    matrix[0, :] *= scale_x
    matrix[1, :] *= scale_y
    matrix[2, :] = [0.0, 0.0, 1.0]
    return matrix


def _vector_from_transform(transform: np.ndarray) -> np.ndarray:
    rotation_vector, _ = cv2.Rodrigues(
        np.asarray(transform[:3, :3], dtype=np.float64)
    )
    return np.concatenate((
        rotation_vector.reshape(3),
        np.asarray(transform[:3, 3], dtype=np.float64).reshape(3),
    ))


def _transform_from_vector(vector: np.ndarray) -> np.ndarray:
    values = np.asarray(vector, dtype=np.float64).reshape(6)
    rotation, _ = cv2.Rodrigues(values[:3])
    transform = np.eye(4, dtype=np.float64)
    transform[:3, :3] = rotation
    transform[:3, 3] = values[3:]
    return transform


def _project_points(
    object_points: np.ndarray,
    camera_from_board: np.ndarray,
    detection: dict,
    intrinsics: object,
) -> np.ndarray:
    rotation_vector, _ = cv2.Rodrigues(camera_from_board[:3, :3])
    translation = camera_from_board[:3, 3].reshape(3, 1)
    matrix = _camera_matrix_for_detection(detection, intrinsics)
    distortion = np.asarray(
        intrinsics.distortion_coefficients,
        dtype=np.float64,
    )
    if intrinsics.camera_model == "opencv_fisheye":
        projected, _ = cv2.fisheye.projectPoints(
            object_points.reshape(-1, 1, 3),
            rotation_vector,
            translation,
            matrix,
            distortion,
        )
    else:
        projected, _ = cv2.projectPoints(
            object_points,
            rotation_vector,
            translation,
            matrix,
            distortion,
        )
    return projected.reshape(-1, 2)


def _average_transform(transforms: Sequence[np.ndarray]) -> np.ndarray:
    if not transforms:
        raise ValueError("缺少可平均的相機轉換觀測。")
    rotation_vectors = [cv2.Rodrigues(value[:3, :3])[0].reshape(3) for value in transforms]
    rotation, _ = cv2.Rodrigues(np.mean(rotation_vectors, axis=0))
    result = np.eye(4, dtype=np.float64)
    result[:3, :3] = rotation
    result[:3, 3] = np.mean([value[:3, 3] for value in transforms], axis=0)
    return result


def _rig_transforms(
    camera_ids: Sequence[str],
    observations: Sequence[object],
    intrinsics: dict[str, object],
) -> tuple[dict[str, np.ndarray], list[float], np.ndarray]:
    pair_transforms: dict[tuple[str, str], list[np.ndarray]] = defaultdict(list)
    errors: list[float] = []
    first_root_from_board = None
    root = camera_ids[0]
    for observation in observations:
        poses: dict[str, np.ndarray] = {}
        for camera_id, detection in observation.detections.items():
            if camera_id not in intrinsics or not detection.get("board_detected"):
                continue
            pose, error = _camera_from_board(detection, intrinsics[camera_id])
            poses[camera_id] = pose
            errors.append(error)
        if first_root_from_board is None and root in poses:
            first_root_from_board = poses[root]
        visible = sorted(poses)
        for index, camera_id in enumerate(visible):
            for other in visible[index + 1:]:
                pair_transforms[(camera_id, other)].append(
                    poses[camera_id] @ np.linalg.inv(poses[other])
                )
    adjacency: dict[str, list[tuple[str, np.ndarray]]] = defaultdict(list)
    for (camera_id, other), transforms in pair_transforms.items():
        camera_from_other = _average_transform(transforms)
        adjacency[camera_id].append((other, camera_from_other))
        adjacency[other].append((camera_id, np.linalg.inv(camera_from_other)))
    rig_from_camera = {root: np.eye(4, dtype=np.float64)}
    queue = deque([root])
    while queue:
        current = queue.popleft()
        for neighbor, current_from_neighbor in adjacency.get(current, []):
            if neighbor in rig_from_camera:
                continue
            rig_from_camera[neighbor] = rig_from_camera[current] @ current_from_neighbor
            queue.append(neighbor)
    if set(rig_from_camera) != set(camera_ids):
        missing = ", ".join(sorted(set(camera_ids) - set(rig_from_camera)))
        raise ValueError(f"相機觀測圖不連通，無法統一外參：{missing}")
    if first_root_from_board is None:
        raise ValueError(f"缺少根相機 {root} 的有效校正板觀測。")
    return rig_from_camera, errors, first_root_from_board


def _initial_board_transforms(
    observations: Sequence[object],
    rig_from_camera: dict[str, np.ndarray],
    intrinsics: dict[str, object],
) -> tuple[list[object], dict[str, np.ndarray]]:
    usable: list[object] = []
    board_transforms: dict[str, np.ndarray] = {}
    for observation in observations:
        candidates: list[np.ndarray] = []
        for camera_id, detection in observation.detections.items():
            if (
                camera_id not in rig_from_camera
                or camera_id not in intrinsics
                or not detection.get("board_detected")
            ):
                continue
            camera_from_board, _ = _camera_from_board(
                detection,
                intrinsics[camera_id],
            )
            candidates.append(
                rig_from_camera[camera_id] @ camera_from_board
            )
        if not candidates:
            continue
        usable.append(observation)
        board_transforms[observation.observation_id] = _average_transform(
            candidates
        )
    return usable, board_transforms


def _optimize_rig_transforms(
    camera_ids: Sequence[str],
    observations: Sequence[object],
    intrinsics: dict[str, object],
    initial_rig_from_camera: dict[str, np.ndarray],
) -> tuple[
    dict[str, np.ndarray],
    dict[str, np.ndarray],
    list[float],
    dict,
]:
    root = camera_ids[0]
    variable_cameras = list(camera_ids[1:])
    usable, initial_boards = _initial_board_transforms(
        observations,
        initial_rig_from_camera,
        intrinsics,
    )
    if not usable:
        raise ValueError("外參觀測沒有可用的校正板姿態。")
    camera_slices: dict[str, slice] = {}
    board_slices: dict[str, slice] = {}
    initial_parts: list[np.ndarray] = []
    offset = 0
    for camera_id in variable_cameras:
        camera_slices[camera_id] = slice(offset, offset + 6)
        initial_parts.append(
            _vector_from_transform(initial_rig_from_camera[camera_id])
        )
        offset += 6
    for observation in usable:
        board_slices[observation.observation_id] = slice(offset, offset + 6)
        initial_parts.append(
            _vector_from_transform(
                initial_boards[observation.observation_id]
            )
        )
        offset += 6
    initial = np.concatenate(initial_parts)

    def unpack(values: np.ndarray):
        cameras = {root: np.eye(4, dtype=np.float64)}
        cameras.update({
            camera_id: _transform_from_vector(values[index])
            for camera_id, index in camera_slices.items()
        })
        boards = {
            observation_id: _transform_from_vector(values[index])
            for observation_id, index in board_slices.items()
        }
        return cameras, boards

    def residuals(values: np.ndarray) -> np.ndarray:
        cameras, boards = unpack(values)
        rows: list[np.ndarray] = []
        for observation in usable:
            rig_from_board = boards[observation.observation_id]
            for camera_id, detection in observation.detections.items():
                if (
                    camera_id not in cameras
                    or camera_id not in intrinsics
                    or not detection.get("board_detected")
                ):
                    continue
                objects = np.asarray(
                    detection.get("object_points"),
                    dtype=np.float64,
                ).reshape(-1, 3)
                images = np.asarray(
                    detection.get("image_points"),
                    dtype=np.float64,
                ).reshape(-1, 2)
                if len(objects) < 6 or len(objects) != len(images):
                    continue
                camera_from_board = (
                    np.linalg.inv(cameras[camera_id]) @ rig_from_board
                )
                projected = _project_points(
                    objects,
                    camera_from_board,
                    detection,
                    intrinsics[camera_id],
                )
                rows.append((projected - images).reshape(-1))
        if not rows:
            raise ValueError("外參觀測沒有可最佳化的角點。")
        return np.concatenate(rows)

    initial_residuals = residuals(initial)
    try:
        from scipy.optimize import least_squares
    except ModuleNotFoundError:
        least_squares = None
    if least_squares is None:
        optimized_values = initial
        optimized_success = False
        optimized_message = (
            "目前執行環境未安裝 scipy，保留 OpenCV PnP 觀測圖初始解；"
            "正式環境必須由 start.bat --setup 安裝完整依賴。"
        )
        optimized_nfev = 0
    else:
        optimized = least_squares(
            residuals,
            initial,
            method="trf",
            loss="soft_l1",
            f_scale=1.0,
            max_nfev=250,
            xtol=1e-10,
            ftol=1e-10,
            gtol=1e-10,
        )
        optimized_values = optimized.x
        optimized_success = bool(optimized.success)
        optimized_message = str(optimized.message)
        optimized_nfev = int(optimized.nfev)
    if not np.isfinite(optimized_values).all():
        raise ValueError("外參全域最佳化產生非有限結果。")
    cameras, boards = unpack(optimized_values)
    final_residuals = residuals(optimized_values).reshape(-1, 2)
    point_errors = np.linalg.norm(final_residuals, axis=1)
    diagnostics = {
        "optimizer": (
            "scipy_least_squares_soft_l1"
            if least_squares is not None
            else "opencv_pnp_observation_graph_fallback"
        ),
        "converged": optimized_success,
        "termination_message": optimized_message,
        "function_evaluations": optimized_nfev,
        "initial_rms_error_px": float(np.sqrt(np.mean(initial_residuals ** 2))),
        "final_rms_error_px": float(np.sqrt(np.mean(final_residuals ** 2))),
        "optimized_camera_count": len(cameras),
        "optimized_board_pose_count": len(boards),
    }
    return cameras, boards, point_errors.astype(float).tolist(), diagnostics


def solve_extrinsic_profile(
    profile: object,
    observations: Sequence[object],
    intrinsics: dict[str, object],
) -> dict:
    accepted = [observation for observation in observations if observation.accepted]
    graph = observation_graph_status(profile.camera_ids, accepted)
    if not graph["connected"]:
        components = "、".join("/".join(item) for item in graph["components"])
        raise ValueError(f"相機觀測圖不連通：{components}。請補拍可共同看到校正板的視角。")
    missing_intrinsics = [
        camera_id
        for camera_id in profile.camera_ids
        if camera_id not in intrinsics or intrinsics[camera_id].status != "valid"
    ]
    if missing_intrinsics:
        raise ValueError(f"以下相機缺少有效內參：{', '.join(missing_intrinsics)}")
    initial_rig_from_camera, _, _ = _rig_transforms(
        profile.camera_ids,
        accepted,
        intrinsics,
    )
    (
        rig_from_camera,
        rig_from_boards,
        reprojection_errors,
        optimization,
    ) = _optimize_rig_transforms(
        profile.camera_ids,
        accepted,
        intrinsics,
        initial_rig_from_camera,
    )
    root_from_board = next(iter(rig_from_boards.values()))
    camera_payloads = []
    world = default_world_alignment(
        profile.world_alignment,
        np.linalg.inv(root_from_board),
    )
    world_from_rig = np.asarray(world.transform_world_from_rig, dtype=np.float64)
    for camera in profile.cameras:
        rig_transform = rig_from_camera[camera.camera_id]
        camera_payloads.append(camera.model_copy(
            update={
                "transform_rig_from_camera": rig_transform.astype(float).tolist(),
                "transform_world_from_camera": (
                    world_from_rig @ rig_transform
                ).astype(float).tolist(),
            },
            deep=True,
        ))
    motion = profile.motion_model
    axis_error = None
    axis_samples = []
    if "rotating" in profile.camera_ids:
        axis = fit_rotation_axis(accepted, intrinsics["rotating"])
        axis_error = float(axis["axis_fit_residual_mm"])
        axis_samples = axis.pop("samples")
        motion = motion.model_copy(
            update={
                **{
                    key: value
                    for key, value in axis.items()
                    if key in motion.model_fields
                },
                "lift_axis_direction": (
                    motion.lift_axis_direction
                    or axis["rotation_axis_direction"]
                ),
                "height_reference_mm": motion.arm_height_mm,
            },
            deep=True,
        )
        for sample in axis_samples:
            predicted = rotating_camera_pose(
                motion,
                sample["angle_deg"],
                motion.arm_height_mm,
            )
            observed = np.asarray(
                sample["observed_world_from_camera"],
                dtype=np.float64,
            )
            sample["predicted_world_from_camera"] = predicted.astype(
                float
            ).tolist()
            sample["position_residual_mm"] = float(
                np.linalg.norm(predicted[:3, 3] - observed[:3, 3])
            )
    mean_error = float(np.mean(reprojection_errors)) if reprojection_errors else float("inf")
    quality_status = extrinsic_quality_status(
        mean_error,
        bool(graph["connected"]),
        axis_error,
    )
    if optimization["optimizer"].endswith("fallback"):
        quality_status = "warning"
    quality = {
        "mean_reprojection_error_px": mean_error,
        "maximum_reprojection_error_px": float(max(reprojection_errors, default=0.0)),
        "camera_pose_consistency_px": float(np.std(reprojection_errors)) if reprojection_errors else 0.0,
        "rotation_axis_fit_error_mm": axis_error,
        "motor_angle_residual_deg": 0.0 if axis_error is not None else None,
        "arm_path_circularity_error_mm": axis_error,
        "world_scale_error_mm": 0.0,
        "board_pose_consistency_px": float(np.std(reprojection_errors)) if reprojection_errors else 0.0,
        "valid_shared_observation_count": len(accepted),
        "observation_graph": graph,
        "valid_image_count_by_camera": {
            camera_id: sum(
                1
                for observation in accepted
                if observation.detections.get(camera_id, {}).get("board_detected")
            )
            for camera_id in profile.camera_ids
        },
        "rotation_samples": axis_samples,
        "global_optimization": optimization,
    }
    return {
        "cameras": camera_payloads,
        "motion_model": motion,
        "world_alignment": world,
        "quality_status": quality_status,
        "quality": quality,
    }
