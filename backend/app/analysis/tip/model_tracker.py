"""Follow a manually identified tip in each immutable model's own frame."""
from __future__ import annotations

from itertools import combinations

import numpy as np

from app.analysis.reconstruction.multiview import robust_multiview_triangulate
from app.analysis.tip.temporal_tracker import track_tip_sequence
from app.analysis.pose_alignment.model_reference import aggregate_fixed_camera_poses

MODEL_TIP_TRACKING_VERSION = 2


def model_tip_projection(annotation, reference, view_id, camera_id, matrix):
    """Use any registered view as an independent image check, never as truth."""
    if not annotation or annotation.get("status") not in {"manual", "tracked"}:
        return None
    orbit = reference.get("orbit") or {}
    if orbit.get("rotation_rmse_deg", float("inf")) > 2 or orbit.get("position_rmse_over_radius", float("inf")) > .035:
        return None  # Unstable geometry must not pull a correct image marker.
    xyz = np.asarray(annotation.get("relative_xyz"), dtype=float)
    if xyz.shape != (3,) or not np.isfinite(xyz).all():
        return None
    views = reference.get("views", [])
    pose = next((v["pose"] for v in views if v["view_id"] == view_id and v.get("pose") is not None), None)
    if pose is None and camera_id in {"top", "side"}:
        try:
            fixed, _ = aggregate_fixed_camera_poses(views, orbit_radius=orbit.get("radius", 1.))
            pose = fixed.get(camera_id)
        except ValueError:
            return None
    if pose is None:
        return None
    pose = np.asarray(pose)
    if pose.shape != (4, 4) or not np.isfinite(pose).all():
        return None
    pixel = np.asarray(matrix) @ (pose[:3] @ np.append(xyz, 1))
    return tuple(pixel[:2] / pixel[2]) if np.isfinite(pixel).all() and pixel[2] > 1e-8 else None


def _angle(view):
    value = view.get("motor_position_deg")
    if value is None:
        value = view.get("angle_deg")
    return float(value) % 360 if value is not None and np.isfinite(value) else None


def track_model_tip(source, target, point, matrix, frame_for, *, cancel_check=lambda: None):
    """Match comparable arm angles, then triangulate in the new SfM frame.

    Relative coordinates and Gaussian IDs cannot be copied between rounds.
    This annotation never supplies millimetre trajectory coordinates.
    """
    xyz, matrix = np.asarray(point, dtype=float), np.asarray(matrix, dtype=float)
    if xyz.shape != (3,) or matrix.shape != (3, 3) or not np.isfinite(xyz).all() or not np.isfinite(matrix).all():
        raise ValueError("模型尖端追蹤缺少有效的參考位置或內參。")
    sources = [v for v in source.get("views", []) if v.get("camera_id") == "rotating"
               and v.get("pose") is not None and _angle(v) is not None]
    targets = [v for v in target.get("views", []) if v.get("camera_id") == "rotating"
               and v.get("pose") is not None and _angle(v) is not None]
    sources.sort(key=_angle)
    if len(sources) > 12:
        sources = [sources[i] for i in np.linspace(0, len(sources) - 1, 12, dtype=int)]
    matches, attempted, seen = [], [], set()
    for view in sources:
        cancel_check()
        nearest = min(targets, key=lambda v: abs((_angle(v) - _angle(view) + 180) % 360 - 180), default=None)
        if nearest is None or nearest["view_id"] in seen:
            continue
        if abs((_angle(nearest) - _angle(view) + 180) % 360 - 180) > 3:
            continue
        seen.add(nearest["view_id"])
        old_pose, pose = np.asarray(view["pose"], dtype=float), np.asarray(nearest["pose"], dtype=float)
        if old_pose.shape != (4, 4) or pose.shape != (4, 4) or not np.isfinite(old_pose).all() or not np.isfinite(pose).all():
            continue
        pixel = matrix @ (old_pose[:3] @ np.append(xyz, 1))
        if pixel[2] <= 0:
            continue
        try:
            candidate, quality = track_tip_sequence(frame_for(view["view_id"]), tuple(pixel[:2] / pixel[2]),
                                                    [frame_for(nearest["view_id"])], cancel_check=cancel_check)
        except (ValueError, OSError) as error:
            attempted.append({"view_id": nearest["view_id"], "reason": str(error)})
            continue
        attempted.append({"view_id": nearest["view_id"], **quality})
        if candidate is not None:
            matches.append({"view_id": nearest["view_id"], "pose": pose, "projection": matrix @ pose[:3],
                            "pixel": [candidate.x_px, candidate.y_px], "confidence": candidate.confidence})
    if len(matches) < 2:
        raise ValueError("模型尖端缺少兩個通過外觀追蹤的懸臂視角，可在本輪重新標記。")
    # Start with the widest baseline instead of adjacent, nearly identical views.
    centre = lambda m: -m["pose"][:3, :3].T @ m["pose"][:3, 3]
    first, second = max(combinations(range(len(matches)), 2),
                        key=lambda pair: np.linalg.norm(centre(matches[pair[0]]) - centre(matches[pair[1]])))
    matches = [matches[first], matches[second], *(m for i, m in enumerate(matches) if i not in {first, second})]
    result = robust_multiview_triangulate([m["projection"] for m in matches], [m["pixel"] for m in matches],
        confidence=[m["confidence"] for m in matches], rejection_threshold_px=3, seed_policy="consensus")
    accepted = [m for m, used in zip(matches, result.used_observations) if used]
    if len(accepted) < max(2, len(matches) // 2 + 1):
        raise ValueError("模型尖端的多視角觀測缺少一致多數，本輪保留為待標記。")
    rays = [result.point - centre(m) for m in accepted]
    rays = [ray / np.linalg.norm(ray) for ray in rays if np.linalg.norm(ray) > 1e-8]
    parallax = max((float(np.rad2deg(np.arccos(np.clip(a @ b, -1, 1)))) for a, b in combinations(rays, 2)), default=0)
    if parallax < 1.5:
        raise ValueError("模型尖端追蹤的視差不足，已保留為待人工標記。")
    return {"status": "tracked", "source": "temporal_tracking", "coordinate_space": "model",
            "relative_xyz": result.point.tolist(), "confidence": min(m["confidence"] for m in accepted),
            "observations": [{"view_id": m["view_id"], "x_px": m["pixel"][0], "y_px": m["pixel"][1]} for m in accepted],
            "quality": {"version": MODEL_TIP_TRACKING_VERSION, "parallax_deg": parallax,
                        "absolute_accuracy_verified": False, **result.quality, "views": attempted}}
