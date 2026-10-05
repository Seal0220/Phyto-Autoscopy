from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import math
from uuid import uuid4
from pathlib import Path

import cv2
import numpy as np

from app.analysis.image_probe import read_analysis_image
from app.analysis.gpu_operations import cuda_hamming_matches, detect_orb_features
from app.analysis.checkpoints import StepJournal, step_signature

from app.analysis.pose_alignment.models import (
    CameraPoseResult,
    PoseAlignmentResult,
)
from app.analysis.pose_alignment.pipeline import _quality_summary
from app.analysis.pose_alignment.sfm_refinement import (
    fill_rotating_results,
)


class StereoPoseEstimationError(ValueError):
    """Expected lack of usable stereo geometry, recoverable with human input."""


def _value(item: object, key: str, default=None):
    return item.get(key, default) if isinstance(item, Mapping) else getattr(item, key, default)


def _gray(frame: object) -> np.ndarray | None:
    try:
        return read_analysis_image(Path(_value(frame, "file_path")), cv2.IMREAD_GRAYSCALE)
    except OSError:
        return None


def _features(frame: object, count: int):
    image = _gray(frame)
    if image is None:
        return None
    path = Path(_value(frame, "file_path"))
    root = next((parent for parent in path.parents if parent.name.startswith("analysis_")), None)
    stat = path.stat()
    signature = step_signature({"version": cv2.__version__, "count": count, "path": str(path),
                                "size": stat.st_size, "mtime": stat.st_mtime_ns})
    if root is not None:
        with StepJournal(root) as journal:
            saved = journal.get("extracting_features", str(path), signature)
            if saved is not None:
                with np.load(saved["arrays"], allow_pickle=False) as arrays:
                    keypoints = [cv2.KeyPoint(float(row[0]), float(row[1]), float(row[2]), float(row[3]),
                                             float(row[4]), int(row[5]), int(row[6])) for row in arrays["keypoints"]]
                    return image, keypoints, arrays["descriptors"]
    keypoints, descriptors, backend = detect_orb_features(image, count)
    if descriptors is None or len(keypoints) < 8:
        return None
    if root is not None:
        destination = root / "checkpoints" / "orb_features" / f"{signature}.npz"
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("wb") as handle:
                np.savez_compressed(handle, descriptors=descriptors, keypoints=np.asarray([
                    [*point.pt, point.size, point.angle, point.response, point.octave, point.class_id] for point in keypoints
                ]))
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        with StepJournal(root) as journal:
            journal.save("extracting_features", str(path), signature,
                         {"arrays": str(destination), "backend": backend}, outputs=[destination])
    return image, keypoints, descriptors


def _matches(first: np.ndarray, second: np.ndarray) -> list[cv2.DMatch]:
    gpu_matches = cuda_hamming_matches(first, second)
    if gpu_matches is not None:
        return gpu_matches
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    forward = matcher.knnMatch(first, second, k=2)
    backward = matcher.knnMatch(second, first, k=2)
    reverse = {
        pair[0].queryIdx: pair[0].trainIdx
        for pair in backward
        if len(pair) == 2 and pair[0].distance < 0.75 * pair[1].distance
    }
    return [
        pair[0]
        for pair in forward
        if len(pair) == 2
        and pair[0].distance < 0.75 * pair[1].distance
        and reverse.get(pair[0].trainIdx) == pair[0].queryIdx
    ]


def _matrix(intrinsics: object, image: np.ndarray) -> np.ndarray:
    matrix = np.asarray(_value(intrinsics, "camera_matrix"), dtype=np.float64).reshape(3, 3).copy()
    height, width = image.shape[:2]
    matrix[0] *= width / float(_value(intrinsics, "width"))
    matrix[1] *= height / float(_value(intrinsics, "height"))
    return matrix


def _normalized(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    return cv2.undistortPoints(
        points.reshape(-1, 1, 2).astype(np.float64),
        matrix,
        None,
    ).reshape(-1, 2)


def _pair_candidates(frames: Sequence[object]) -> list[tuple[object, object]]:
    tops = [item for item in frames if _value(item, "camera_id") == "top"]
    sides = [item for item in frames if _value(item, "camera_id") == "side"]
    by_snapshot: dict[tuple[str, str], list[object]] = {}
    for side in sides:
        key = (
            str(_value(side, "round_key") or ""),
            str(_value(side, "snapshot_id") or ""),
        )
        by_snapshot.setdefault(key, []).append(side)
    paired = [
        (top, side)
        for top in tops
        for side in by_snapshot.get((
            str(_value(top, "round_key") or ""),
            str(_value(top, "snapshot_id") or ""),
        ), [])
        if _value(top, "snapshot_id")
    ]
    if not paired:
        sides_by_round: dict[str, list[object]] = {}
        for side in sides:
            sides_by_round.setdefault(str(_value(side, "round_key") or ""), []).append(side)
        paired = [
            (top, side)
            for round_key, round_sides in sides_by_round.items()
            for top, side in zip(
                (item for item in tops if str(_value(item, "round_key") or "") == round_key),
                round_sides,
            )
        ]
    return paired[:24]


def _stereo_landmarks(
    top: object,
    side: object,
    intrinsics: Mapping[str, object],
    settings: Mapping[str, object],
    fixed_poses: Mapping[str, np.ndarray] | None = None,
    *,
    diagnostics: dict[str, object] | None = None,
    debug_path: Path | None = None,
    manual_points: tuple[np.ndarray, np.ndarray] | None = None,
):
    diagnostics = diagnostics if diagnostics is not None else {}
    diagnostics.update(matched_features=0, geometric_inliers=0, rejection_reason=None)
    if manual_points is None:
        top_data = _features(top, int(settings["feature_count"]))
        side_data = _features(side, int(settings["feature_count"]))
    else:
        images = (_gray(top), _gray(side))
        if any(image is None for image in images):
            raise ValueError("人工配對影像無法讀取，請重新讀取後再試。")
        top_data, side_data = [
            (image, [cv2.KeyPoint(float(x), float(y), 1) for x, y in points], None)
            for image, points in zip(images, manual_points)
        ]
    diagnostics["top_features"] = len(top_data[1]) if top_data is not None else 0
    diagnostics["side_features"] = len(side_data[1]) if side_data is not None else 0
    if top_data is None or side_data is None:
        diagnostics["rejection_reason"] = "影像讀取或特徵擷取失敗"
        return None
    top_image, top_points, top_descriptors = top_data
    side_image, side_points, side_descriptors = side_data
    matches = (
        _matches(top_descriptors, side_descriptors) if manual_points is None
        else [cv2.DMatch(index, index, 0) for index in range(len(manual_points[0]))]
    )
    diagnostics["matched_features"] = len(matches)
    diagnostics["required_inliers"] = int(settings["minimum_stereo_inliers"])
    if debug_path is not None:
        # This is the actual descriptor matching result, before geometric filtering.
        debug = cv2.drawMatches(
            top_image, top_points, side_image, side_points, matches[:100], None,
            flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS,
        )
        success, encoded = cv2.imencode(".jpg", debug)
        if success:
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            encoded.tofile(debug_path)
    if len(matches) < int(settings["minimum_stereo_inliers"]):
        diagnostics["rejection_reason"] = "共同特徵配對不足"
        return None
    top_pixels = np.asarray([top_points[item.queryIdx].pt for item in matches], dtype=np.float64)
    side_pixels = np.asarray([side_points[item.trainIdx].pt for item in matches], dtype=np.float64)
    top_matrix = _matrix(intrinsics["top"], top_image)
    side_matrix = _matrix(intrinsics["side"], side_image)
    top_normalized = _normalized(top_pixels, top_matrix)
    side_normalized = _normalized(side_pixels, side_matrix)
    if fixed_poses is None:
        focal = min(top_matrix[0, 0], top_matrix[1, 1], side_matrix[0, 0], side_matrix[1, 1])
        threshold = float(settings["maximum_epipolar_error_px"]) / focal
        essential, mask = cv2.findEssentialMat(
            top_normalized,
            side_normalized,
            np.eye(3),
            method=cv2.RANSAC,
            prob=0.999,
            threshold=threshold,
        )
        if essential is None or mask is None:
            diagnostics["rejection_reason"] = "極線幾何估計失敗"
            return None
        _, rotation, translation, mask = cv2.recoverPose(
            essential,
            top_normalized,
            side_normalized,
            np.eye(3),
            mask=mask,
        )
        translation = translation.reshape(3) * float(settings["baseline_mm"])
        # The platform directly beneath the top camera is world Z=0. Flip two
        # axes so Z points upward while retaining a right-handed coordinate system.
        top_pose = np.eye(4, dtype=np.float64)
        top_pose[:3, :3] = np.diag([1.0, -1.0, -1.0])
        top_pose[2, 3] = float(settings["top_height_mm"])
        relative = np.eye(4, dtype=np.float64)
        relative[:3, :3] = rotation
        relative[:3, 3] = translation
        side_pose = relative @ top_pose
    else:
        top_pose = fixed_poses["top"]
        side_pose = fixed_poses["side"]
        relative = side_pose @ np.linalg.inv(top_pose)
        shift = relative[:3, 3]
        essential = np.asarray([
            [0, -shift[2], shift[1]],
            [shift[2], 0, -shift[0]],
            [-shift[1], shift[0], 0],
        ]) @ relative[:3, :3]
        top_h = np.column_stack((top_normalized, np.ones(len(matches))))
        side_h = np.column_stack((side_normalized, np.ones(len(matches))))
        residual = np.abs(np.sum(side_h * (top_h @ essential.T), axis=1))
        denominator = np.linalg.norm((top_h @ essential.T)[:, :2], axis=1)
        mask = (residual / np.maximum(denominator, 1e-12) < float(settings["maximum_epipolar_error_px"]) / min(top_matrix[0, 0], side_matrix[0, 0])).astype(np.uint8).reshape(-1, 1)
    inlier_indices = np.flatnonzero(mask.reshape(-1))
    diagnostics["geometric_inliers"] = len(inlier_indices)
    if len(inlier_indices) < int(settings["minimum_stereo_inliers"]):
        diagnostics["rejection_reason"] = "相機姿態幾何內點不足"
        return None
    top_rays = top_normalized[inlier_indices]
    side_rays = side_normalized[inlier_indices]
    world_points = cv2.triangulatePoints(
        top_pose[:3],
        side_pose[:3],
        top_rays.T,
        side_rays.T,
    )
    w = world_points[3]
    finite = np.abs(w) > 1e-9
    points = np.full((len(w), 3), np.nan, dtype=np.float64)
    points[finite] = (world_points[:3, finite] / w[finite]).T
    top_cam = (top_pose[:3, :3] @ points.T).T + top_pose[:3, 3]
    side_cam = (side_pose[:3, :3] @ points.T).T + side_pose[:3, 3]
    valid = finite & (top_cam[:, 2] > 0) & (side_cam[:, 2] > 0)
    reprojection_errors = []
    for camera_points, pixels, matrix in (
        (top_cam, top_pixels[inlier_indices], top_matrix),
        (side_cam, side_pixels[inlier_indices], side_matrix),
    ):
        projection = (matrix @ camera_points.T).T
        projection = projection[:, :2] / np.maximum(projection[:, 2:3], 1e-9)
        error = np.linalg.norm(projection - pixels, axis=1)
        reprojection_errors.append(error)
        valid &= np.isfinite(error) & (error <= float(settings["maximum_stereo_reprojection_error_px"]))
    if int(valid.sum()) < int(settings["minimum_stereo_inliers"]):
        diagnostics["reprojection_inliers"] = int(valid.sum())
        diagnostics["rejection_reason"] = "正深度或重投影檢查未通過"
        return None
    top_center = np.linalg.inv(top_pose)[:3, 3]
    side_center = np.linalg.inv(side_pose)[:3, 3]
    top_vectors = points[valid] - top_center
    side_vectors = points[valid] - side_center
    cosine = np.sum(top_vectors * side_vectors, axis=1) / np.maximum(
        np.linalg.norm(top_vectors, axis=1)
        * np.linalg.norm(side_vectors, axis=1),
        1e-9,
    )
    parallax_deg = float(np.median(np.degrees(np.arccos(np.clip(cosine, -1, 1)))))
    side_axis = np.linalg.inv(side_pose)[:3, 2]
    side_elevation_deg = abs(math.degrees(math.atan2(
        float(side_axis[2]),
        float(np.linalg.norm(side_axis[:2])),
    )))
    diagnostics.update(parallax_deg=parallax_deg, side_elevation_deg=side_elevation_deg)
    if (
        parallax_deg < float(settings["minimum_parallax_deg"])
        or side_elevation_deg > float(settings["maximum_side_elevation_deg"])
    ):
        diagnostics["rejection_reason"] = (
            "視差角不足" if parallax_deg < float(settings["minimum_parallax_deg"])
            else "側視相機仰角超出限制"
        )
        return None
    indices = inlier_indices[valid]
    return {
        "poses": {"top": top_pose, "side": side_pose},
        "landmarks": points[valid],
        "top_indices": [matches[index].queryIdx for index in indices],
        "side_indices": [matches[index].trainIdx for index in indices],
        "top_features": top_data,
        "side_features": side_data,
        "inliers": int(valid.sum()),
        "parallax_deg": parallax_deg,
        "side_elevation_deg": side_elevation_deg,
        "reprojection_rmse_px": float(np.sqrt(np.mean(
            np.concatenate([errors[valid] for errors in reprojection_errors]) ** 2
        ))),
    }


def estimate_fixed_stereo_pose(
    frames: Sequence[object],
    intrinsics: Mapping[str, object],
    settings: Mapping[str, object],
    cancel_check: Callable[[], None] | None = None,
    *,
    debug_directory: Path | None = None,
    progress_callback: Callable[[int, int, object, object, dict[str, object]], None] | None = None,
) -> tuple[dict[str, list[list[float]]], dict[str, object]]:
    best = None
    candidates = _pair_candidates(frames)
    attempts = []
    for index, (top, side) in enumerate(candidates, start=1):
        if cancel_check is not None:
            cancel_check()
        diagnostics: dict[str, object] = {"pair_index": index, "pair_count": len(candidates)}
        if progress_callback is not None:
            progress_callback(index, len(candidates), top, side, diagnostics)
        debug_path = debug_directory / f"pair_{index:03d}.jpg" if debug_directory else None
        try:
            candidate = _stereo_landmarks(
                top, side, intrinsics, settings,
                diagnostics=diagnostics, debug_path=debug_path,
            )
        except (cv2.error, ValueError) as error:
            candidate = None
            diagnostics["rejection_reason"] = f"姿態估計運算失敗：{error}"
        attempts.append(dict(diagnostics))
        if debug_path is not None and debug_path.is_file():
            diagnostics["match_image_path"] = str(debug_path)
        if progress_callback is not None:
            progress_callback(index, len(candidates), top, side, diagnostics)
        if candidate is not None and (best is None or candidate["inliers"] > best["inliers"]):
            best = candidate
    if best is None:
        strongest = max(attempts, key=lambda item: int(item.get("matched_features", 0)), default={})
        raise StereoPoseEstimationError(
            f"無法建立無標記雙鏡頭姿態：已檢查 {len(candidates)} 組影像，"
            f"共同特徵配對最多 {strongest.get('matched_features', 0)} 組，"
            f"需要至少 {settings['minimum_stereo_inliers']} 個有效幾何內點。"
            f"主要原因：{strongest.get('rejection_reason') or '沒有可配對的俯視與側視影像'}。"
            "此階段尚未執行尖端偵測。"
        )
    return _stereo_pose_result(best, settings)


def estimate_manual_stereo_pose(top, side, intrinsics, settings, correspondences):
    """Use human correspondences, retaining depth, reprojection and parallax checks."""
    points = tuple(np.asarray([
        [pair[camera]["x_px"], pair[camera]["y_px"]] for pair in correspondences
    ], dtype=np.float64) for camera in ("top", "side"))
    manual_settings = {**settings, "minimum_stereo_inliers": 8}
    diagnostics = {}
    best = _stereo_landmarks(top, side, intrinsics, manual_settings,
                             diagnostics=diagnostics, manual_points=points)
    if best is None:
        raise ValueError(
            f"人工配對未通過幾何檢查：{diagnostics.get('rejection_reason') or '配對不足'}。"
            "請修正對應位置，至少保留 8 組有效配對。"
        )
    poses, quality = _stereo_pose_result(best, manual_settings)
    quality.update(estimation_source="manual_correspondences", manual_correspondence_count=len(correspondences))
    return poses, quality


def _stereo_pose_result(best, settings):
    side_center = np.linalg.inv(best["poses"]["side"])[:3, 3]
    estimated_side_height_mm = float(side_center[2])
    estimated_side_horizontal_distance_mm = float(np.linalg.norm(side_center[:2]))
    quality = {
        "stereo_inliers": best["inliers"],
        "stereo_reprojection_rmse_px": best["reprojection_rmse_px"],
        "stereo_parallax_deg": best["parallax_deg"],
        "side_elevation_deg": best["side_elevation_deg"],
        "baseline_mm": float(settings["baseline_mm"]),
        "top_height_mm": float(settings["top_height_mm"]),
        "estimated_side_height_mm": estimated_side_height_mm,
        "estimated_side_horizontal_distance_mm": estimated_side_horizontal_distance_mm,
        "scale_source": "measured_stereo_baseline",
    }
    if settings.get("side_height_mm") is not None:
        measured_height = float(settings["side_height_mm"])
        quality["side_height_mm"] = measured_height
        quality["side_height_error_mm"] = abs(
            estimated_side_height_mm - measured_height
        )
    if settings.get("side_horizontal_distance_mm") is not None:
        measured_distance = float(settings["side_horizontal_distance_mm"])
        quality["side_horizontal_distance_mm"] = measured_distance
        quality["side_horizontal_distance_error_mm"] = abs(
            estimated_side_horizontal_distance_mm - measured_distance
        )
    return (
        {key: matrix.tolist() for key, matrix in best["poses"].items()},
        quality,
    )


def _base_pose(frame: object) -> dict[str, object]:
    angle = _value(frame, "angle_deg")
    if angle is None:
        angle = _value(frame, "motor_position_deg")
    return {
        "input_id": int(_value(frame, "capture_id")),
        "camera_id": str(_value(frame, "camera_id")),
        "relative_path": str(_value(frame, "relative_path")),
        "timestamp": _value(frame, "timestamp"),
        "motor_angle_deg": angle,
    }


def align_markerless_camera_poses(
    frames: Sequence[object],
    intrinsics: Mapping[str, object],
    settings: Mapping[str, object],
    fixed_poses: Mapping[str, list[list[float]]],
    *,
    required_camera_ids: Sequence[str],
    cancel_check: Callable[[], None] | None = None,
) -> PoseAlignmentResult:
    fixed = {key: np.asarray(value, dtype=np.float64).reshape(4, 4) for key, value in fixed_poses.items()}
    poses: list[CameraPoseResult] = []
    for frame in frames:
        camera_id = _value(frame, "camera_id")
        if camera_id not in {"top", "side"}:
            continue
        matrix = fixed[camera_id]
        poses.append(CameraPoseResult(
            **_base_pose(frame),
            source="rig_stereo",
            resolved=True,
            world_to_camera_matrix=matrix.tolist(),
            camera_to_world_matrix=np.linalg.inv(matrix).tolist(),
        ))
    rotating_frames = sorted(
        (frame for frame in frames if _value(frame, "camera_id") == "rotating"),
        key=lambda frame: (str(_value(frame, "timestamp") or ""), int(_value(frame, "capture_id"))),
    )
    best_landmarks = None
    for top, side in _pair_candidates(frames):
        if cancel_check is not None:
            cancel_check()
        try:
            candidate = _stereo_landmarks(top, side, intrinsics, settings, fixed)
        except (cv2.error, ValueError):
            continue
        if candidate is not None and (best_landmarks is None or candidate["inliers"] > best_landmarks["inliers"]):
            best_landmarks = candidate
    rotating_poses: list[CameraPoseResult] = []
    for frame in rotating_frames:
        if cancel_check is not None:
            cancel_check()
        base = _base_pose(frame)
        if best_landmarks is None:
            rotating_poses.append(CameraPoseResult(**base, failure_reason="本輪雙鏡頭特徵不足，無法求得旋臂姿態。"))
            continue
        target = _features(frame, int(settings["feature_count"]))
        if target is None:
            rotating_poses.append(CameraPoseResult(**base, failure_reason="旋臂影像不可讀或缺少特徵。"))
            continue
        image, _, descriptors = target
        points_3d: list[np.ndarray] = []
        points_2d: list[tuple[float, float]] = []
        seen_target: set[int] = set()
        for camera_id in ("top", "side"):
            source = best_landmarks[f"{camera_id}_features"]
            lookup = dict(zip(best_landmarks[f"{camera_id}_indices"], best_landmarks["landmarks"]))
            for match in _matches(source[2], descriptors):
                if match.queryIdx not in lookup or match.trainIdx in seen_target:
                    continue
                seen_target.add(match.trainIdx)
                points_3d.append(lookup[match.queryIdx])
                points_2d.append(target[1][match.trainIdx].pt)
        minimum = int(settings["minimum_rotating_inliers"])
        if len(points_3d) < minimum:
            rotating_poses.append(CameraPoseResult(**base, sfm_match_count=len(points_3d), failure_reason="旋臂與固定雙鏡頭的共同特徵不足。"))
            continue
        camera_matrix = _matrix(intrinsics["rotating"], image)
        try:
            ok, rotation_vector, translation, inliers = cv2.solvePnPRansac(
                np.asarray(points_3d, dtype=np.float64),
                np.asarray(points_2d, dtype=np.float64),
                camera_matrix,
                None,
                iterationsCount=200,
                reprojectionError=float(settings["maximum_pnp_reprojection_error_px"]),
                confidence=0.999,
                flags=cv2.SOLVEPNP_EPNP,
            )
        except cv2.error:
            ok, inliers = False, None
        if not ok or inliers is None or len(inliers) < minimum:
            rotating_poses.append(CameraPoseResult(**base, sfm_match_count=len(points_3d), failure_reason="旋臂無標記 PnP 內點不足。"))
            continue
        object_inliers = np.asarray(points_3d, dtype=np.float64)[inliers.reshape(-1)]
        image_inliers = np.asarray(points_2d, dtype=np.float64)[inliers.reshape(-1)]
        if hasattr(cv2, "solvePnPRefineLM"):
            try:
                rotation_vector, translation = cv2.solvePnPRefineLM(
                    object_inliers,
                    image_inliers,
                    camera_matrix,
                    None,
                    rotation_vector,
                    translation,
                )
            except cv2.error:
                pass
        projected, _ = cv2.projectPoints(
            object_inliers,
            rotation_vector,
            translation,
            camera_matrix,
            None,
        )
        error = float(np.sqrt(np.mean(np.sum(
            (projected.reshape(-1, 2) - image_inliers) ** 2,
            axis=1,
        ))))
        if not np.isfinite(error) or error > float(settings["maximum_pnp_reprojection_error_px"]):
            rotating_poses.append(CameraPoseResult(**base, sfm_match_count=int(len(inliers)), failure_reason="旋臂姿態重投影誤差過大。"))
            continue
        rotation, _ = cv2.Rodrigues(rotation_vector)
        matrix = np.eye(4, dtype=np.float64)
        matrix[:3, :3] = rotation
        matrix[:3, 3] = translation.reshape(3)
        rotating_poses.append(CameraPoseResult(
            **base,
            source="sfm",
            resolved=True,
            world_to_camera_matrix=matrix.tolist(),
            camera_to_world_matrix=np.linalg.inv(matrix).tolist(),
            sfm_match_count=int(len(inliers)),
            feature_reprojection_error_px=error,
        ))
    if settings.get("use_motor_interpolation", True) and rotating_poses:
        rotating_poses = fill_rotating_results(
            rotating_frames,
            rotating_poses,
            intrinsics["rotating"],
            int(settings["minimum_rotating_inliers"]),
            cancel_check,
        )
    poses.extend(rotating_poses)
    quality = _quality_summary(poses, required_camera_ids, {})
    return PoseAlignmentResult(
        pose_estimation_version="markerless_stereo_v1",
        aruco_alignment_status=quality.status,
        camera_poses=poses,
        fixed_camera_poses=dict(fixed_poses),
        quality=quality,
    )
