"""Automatically localise fixed cameras from the pot rim and stable texture."""
from __future__ import annotations

import cv2
import numpy as np
from scipy.spatial import cKDTree

from app.analysis.pose_alignment.model_reference import model_camera_pose
from app.analysis.segmentation.plant_mask import create_plant_mask
from app.analysis.reconstruction.multiview import robust_multiview_triangulate

STABLE_FEATURE_VERSION = 1


def augment_stable_tracks(sources, matrix, *, cancel_check=lambda: None):
    """Triangulate extra soil texture using three already registered arm poses.

    These auxiliary anchors do not change the sparse model or its Gaussians.
    They allow a small pot's texture to be extracted at a consistent scale.
    """
    sift, matcher = cv2.SIFT_create(nfeatures=2500, contrastThreshold=.02), cv2.BFMatcher(cv2.NORM_L2)
    prepared = []
    for source in sources:
        cancel_check()
        gray, mask, affine, _ = source["region"]
        keys, descriptors = sift.detectAndCompute(gray, mask)
        inverse = cv2.invertAffineTransform(affine)
        pixels = np.asarray([key.pt for key in keys]).reshape(-1, 2) @ inverse[:, :2].T + inverse[:, 2]
        prepared.append({**source, "keys": keys, "descriptors": descriptors, "key_pixels": pixels,
                         "pixels": list(source["pixels"]), "objects": list(source["objects"]), "point_ids": list(source["point_ids"])})
    next_id, assigned = -1, {}
    for index, source in enumerate(prepared):
        cancel_check()
        if source["descriptors"] is None:
            continue
        delta = lambda target: abs((target["angle_deg"] - source["angle_deg"] + 180) % 360 - 180)
        neighbors = sorted((i for i, target in enumerate(prepared) if i != index and target["descriptors"] is not None
                            and 4 <= delta(target) <= 25), key=lambda i: delta(prepared[i]))[:3]
        tracks = {}
        for neighbor in neighbors:
            target = prepared[neighbor]
            reverse = {m.queryIdx: m.trainIdx for m in matcher.match(target["descriptors"], source["descriptors"])}
            for pair in matcher.knnMatch(source["descriptors"], target["descriptors"], k=2):
                if len(pair) == 2 and pair[0].distance < pair[1].distance * .7 and reverse.get(pair[0].trainIdx) == pair[0].queryIdx:
                    tracks.setdefault(pair[0].queryIdx, []).append((neighbor, pair[0].trainIdx))
        for key, others in tracks.items():
            if len(others) < 2:
                continue
            entries = [(index, key), *others]
            if any(entry in assigned for entry in entries):
                continue
            poses = [np.asarray(prepared[i]["pose"]) for i, _ in entries]
            try:
                result = robust_multiview_triangulate([np.asarray(matrix) @ pose[:3] for pose in poses],
                    [prepared[i]["key_pixels"][k] for i, k in entries], rejection_threshold_px=1.5)
            except ValueError:
                continue
            if not all(result.used_observations):
                continue
            centers = [-pose[:3, :3].T @ pose[:3, 3] for pose in poses]
            rays = [result.point - center for center in centers]
            rays = [ray / max(np.linalg.norm(ray), 1e-8) for ray in rays]
            if max(float(np.rad2deg(np.arccos(np.clip(a @ b, -1, 1)))) for a in rays for b in rays) < 2:
                continue
            for i, k in entries:
                prepared[i]["pixels"].append(prepared[i]["key_pixels"][k])
                prepared[i]["objects"].append(result.point)
                prepared[i]["point_ids"].append(next_id)
                assigned[i, k] = next_id
            next_id -= 1
    return prepared


def pot_rim_region(image, valid):
    """Fit a supported rim; a plain circle never establishes camera azimuth."""
    if image is None or valid is None or image.shape[:2] != valid.shape:
        raise ValueError("盆緣定位缺少完整的影像與有效像素遮罩。")
    scale = min(1., 800 / max(valid.shape))
    small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else image
    small_valid = cv2.resize(valid, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    blue, green, red = cv2.split(small.astype(np.float32))
    rim = (((hsv[:, :, 0] <= 24) | (hsv[:, :, 0] >= 170)) & (hsv[:, :, 1] >= 65)
           & (hsv[:, :, 2] >= 45) & (red > green * 1.25) & (red > blue * 1.3) & (small_valid > 0))
    contours, _ = cv2.findContours(rim.astype(np.uint8) * 255, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    yy, xx = np.nonzero(rim)
    # Leaves can split the visible rim into disconnected arcs. Fit their joint
    # support too, instead of mistaking one short arc for a smaller pot.
    if len(xx) >= 20:
        contours = [np.column_stack([xx, yy]).astype(np.float32), *contours]
    candidates = []
    for contour in contours:
        if len(contour) < 20:
            continue
        try:
            ellipse = cv2.fitEllipse(contour)
        except cv2.error:
            continue
        (cx, cy), (width, height), angle = ellipse
        if min(width, height) < 8 or max(width, height) < 20 or max(width, height) > max(small_valid.shape) * .8:
            continue
        rotation = np.array([[np.cos(np.deg2rad(angle)), np.sin(np.deg2rad(angle))],
                             [-np.sin(np.deg2rad(angle)), np.cos(np.deg2rad(angle))]])
        # Evaluate only coloured rim pixels rather than allocating a full image
        # coordinate grid for every candidate contour.
        offset = rotation @ np.stack([xx - cx, yy - cy])
        normalized = offset / np.array([[width / 2], [height / 2]])
        radius = np.linalg.norm(normalized, axis=0)
        supported = np.abs(radius - 1) < .15
        if np.count_nonzero(supported) < 24:
            continue
        sector = ((np.arctan2(normalized[1], normalized[0]) + np.pi) / (2 * np.pi) * 24).astype(int)
        coverage = len(np.unique(sector[supported]))
        if coverage < 10:
            continue
        candidates.append((coverage * np.sqrt(np.count_nonzero(supported)), ellipse, rotation))
    if not candidates:
        raise ValueError("影像缺少可辨識且分布足夠的盆緣，無法自動建立穩定特徵區。")
    _, ellipse, rotation = max(candidates, key=lambda item: item[0])
    (cx, cy), (width, height), _ = ellipse
    cx, cy, width, height = np.asarray([cx, cy, width, height]) / scale
    linear = np.diag([256 / width, 256 / height]) @ rotation
    affine = np.column_stack([linear, np.array([192, 192]) - linear @ [cx, cy]])
    gray = cv2.warpAffine(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), affine, (384, 384))
    colour = cv2.warpAffine(image, affine, (384, 384))
    mask = cv2.warpAffine(valid, affine, (384, 384), flags=cv2.INTER_NEAREST)
    plant = create_plant_mask(colour, valid_pixel_mask=mask).mask
    blue, green, red = cv2.split(colour.astype(np.float32))
    # Connected pale soil highlights can belong to the broad plant foreground
    # mask. Grow the exclusion from chromatic leaf tissue only, keeping soil.
    tissue = (plant > 0) & (2 * green - red - blue > 4) & (green >= red * .9)
    excluded = cv2.dilate(tissue.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    yy, xx = np.indices(mask.shape)
    mask[(np.hypot(xx - 192, yy - 192) > 128 * 1.12) | excluded] = 0
    return gray, mask, affine, {"ellipse": [[float(cx), float(cy)], [float(width), float(height)], ellipse[2]],
                              "stable_pixels": int(np.count_nonzero(mask))}


def stable_camera_pose(objects, pixels, matrix, *, maximum_error_px=3):
    """Hold out independent matches so optimisation cannot validate itself."""
    objects, pixels = np.asarray(objects, float), np.asarray(pixels, float)
    if len(objects) < 16 or len(objects) != len(pixels):
        raise ValueError("穩定盆緣與土壤特徵不足，尚無法自動對齊相機。")
    holdout = np.arange(len(objects)) % 4 == 0
    pose, quality = model_camera_pose(objects[~holdout], pixels[~holdout], matrix, maximum_error_px)
    if len(quality["inlier_indices"]) < 10:
        raise ValueError("自動相機對齊的穩定內點不足。")
    camera = objects[holdout] @ pose[:3, :3].T + pose[:3, 3]
    projected = camera @ np.asarray(matrix).T
    errors = np.linalg.norm(projected[:, :2] / projected[:, 2:] - pixels[holdout], axis=1)
    if np.any(camera[:, 2] <= 0) or not np.isfinite(errors).all() or np.percentile(errors, 75) > maximum_error_px:
        raise ValueError("自動相機對齊未通過保留特徵的重投影檢查。")
    return pose, {**quality, "method": "pot_rim_normalized_stable_texture_pnp",
                  "version": STABLE_FEATURE_VERSION, "holdout_count": int(holdout.sum()),
                  "holdout_p75_error_px": float(np.percentile(errors, 75)), "absolute_accuracy_verified": False}


def localise_stable_camera(target_image, target_valid, matrix, sources, *, cancel_check=lambda: None):
    """sources contain original image pixels linked to real SfM 3D tracks."""
    target_gray, target_mask, target_affine, rim_quality = pot_rim_region(target_image, target_valid)
    sift = cv2.SIFT_create(nfeatures=2500, contrastThreshold=.02)
    target_keys, target_descriptors = sift.detectAndCompute(target_gray, target_mask)
    if target_descriptors is None or len(target_keys) < 16:
        raise ValueError("盆緣與土壤區缺少可配對的影像細節。")
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    matches = {}
    for source in sources:
        cancel_check()
        try:
            gray, mask, affine, _ = source.get("region") or pot_rim_region(source["image"], source["valid"])
        except ValueError:
            continue
        keys, descriptors = sift.detectAndCompute(gray, mask)
        if descriptors is None or len(keys) < 2 or len(source["pixels"]) < 4:
            continue
        projected = np.asarray(source["pixels"]) @ affine[:, :2].T + affine[:, 2]
        distance, point_indexes = cKDTree(projected).query([key.pt for key in keys])
        reverse = matcher.match(target_descriptors, descriptors)
        reverse_indexes = {match.queryIdx: match.trainIdx for match in reverse}
        for pair in matcher.knnMatch(descriptors, target_descriptors, k=2):
            if len(pair) != 2:
                continue
            best, second = pair
            if (distance[best.queryIdx] > 3 or best.distance >= second.distance * .7
                    or reverse_indexes.get(best.trainIdx) != best.queryIdx):
                continue
            point_index = int(point_indexes[best.queryIdx])
            point_id = int(source["point_ids"][point_index])
            previous = matches.get(best.trainIdx)
            if previous is None or best.distance < previous[0]:
                matches[best.trainIdx] = (best.distance, point_id, source["objects"][point_index])
    # One image feature and one physical SfM point may each occur only once.
    ordered, point_ids = [], set()
    inverse = cv2.invertAffineTransform(target_affine)
    for index, (distance, point_id, point) in sorted(matches.items(), key=lambda item: item[1][0]):
        if point_id in point_ids:
            continue
        point_ids.add(point_id)
        pixel = inverse[:, :2] @ target_keys[index].pt + inverse[:, 2]
        ordered.append((point, pixel))
    if len(ordered) < 16:
        raise ValueError(f"盆緣與土壤僅有 {len(ordered)} 組可靠三維特徵配對（至少需 16 組），已保留模型與尖端追蹤。")
    pose, quality = stable_camera_pose([item[0] for item in ordered], [item[1] for item in ordered], matrix)
    return pose, {**quality, "rim": rim_quality, "matched_point_count": len(ordered)}
