"""Track an operator-identified shoot in fixed-camera image sequences.

The paper's temporal selection principle is used here, with local appearance,
foreground and forward/backward checks. A leaf contour endpoint alone never
establishes shoot identity. Tracking does not require a registered 3DGS model.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import cv2
import numpy as np

from app.analysis.image_probe import read_analysis_image
from app.analysis.segmentation.plant_mask import create_plant_mask
from app.analysis.tip.candidate_detector import TipCandidate2D

TIP_TRACKING_VERSION = 4
PATCH_RADIUS = 15
SEARCH_RADIUS = 64
KEYFRAME_INTERVAL = 12


@dataclass(frozen=True, slots=True)
class TipTrackingFrame:
    view_id: str
    camera_id: str
    image_path: Path
    valid_mask_path: Path


def _read(frame: TipTrackingFrame) -> tuple[np.ndarray, np.ndarray]:
    image = read_analysis_image(frame.image_path, cv2.IMREAD_COLOR)
    valid = read_analysis_image(frame.valid_mask_path, cv2.IMREAD_GRAYSCALE)
    if image is None or valid is None or image.shape[:2] != valid.shape:
        raise ValueError("尖端追蹤缺少一致的變形校正影像與有效像素遮罩。")
    return image, valid


def _foreground_distance(image, valid, point) -> float:
    # A local crop prevents remote lamps/reflections from influencing selection.
    x, y = point
    radius = SEARCH_RADIUS + PATCH_RADIUS
    left, top = max(0, int(x) - radius), max(0, int(y) - radius)
    right, bottom = min(image.shape[1], int(x) + radius + 1), min(image.shape[0], int(y) + radius + 1)
    mask = create_plant_mask(image[top:bottom, left:right], valid_pixel_mask=valid[top:bottom, left:right]).mask
    if not np.any(mask):
        return float("inf")
    distance = cv2.distanceTransform((mask == 0).astype(np.uint8), cv2.DIST_L2, 5)
    return float(distance[int(round(y)) - top, int(round(x)) - left])


def validate_tip_seed(frame: TipTrackingFrame, point: tuple[float, float]) -> dict:
    image, valid = _read(frame)
    x, y = point
    height, width = valid.shape
    if not np.isfinite(point).all() or not (PATCH_RADIUS <= x < width - PATCH_RADIUS
                                          and PATCH_RADIUS <= y < height - PATCH_RADIUS):
        raise ValueError("尖端太接近影像邊界，無法建立可靠的追蹤範圍。")
    patch_valid = cv2.getRectSubPix(valid, (31, 31), (float(x), float(y)))
    if np.any(patch_valid < 250):
        raise ValueError("尖端追蹤範圍包含無效的變形校正像素，請重新標記。")
    foreground_distance = _foreground_distance(image, valid, point)
    if foreground_distance > 8:
        raise ValueError("尖端標記沒有靠近植物組織，請確認沒有標到燈或背景。")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    texture = float(cv2.getRectSubPix(gray, (31, 31), (float(x), float(y))).std())
    if texture < 4:
        raise ValueError("尖端附近缺少可追蹤的影像細節，請重新標記清楚的生長尖端。")
    return {"foreground_distance_px": foreground_distance, "texture_std": texture}


def _match(source, target, point, *, search_center=None, search_radius=SEARCH_RADIUS, patch_radius=PATCH_RADIUS):
    x, y = point
    patch_size = 2 * patch_radius + 1
    patch = cv2.getRectSubPix(source, (patch_size, patch_size), (float(x), float(y)))
    cx, cy = search_center if search_center is not None else point
    left, top = max(0, int(cx) - search_radius - patch_radius), max(0, int(cy) - search_radius - patch_radius)
    right = min(target.shape[1], int(cx) + search_radius + patch_radius + 1)
    bottom = min(target.shape[0], int(cy) + search_radius + patch_radius + 1)
    scores = cv2.matchTemplate(target[top:bottom, left:right], patch, cv2.TM_CCOEFF_NORMED)
    _, score, _, (column, row) = cv2.minMaxLoc(scores)
    alternatives = scores.copy()
    alternatives[max(0, row - 12):row + 13, max(0, column - 12):column + 13] = -1
    margin = float(score - alternatives.max())
    # Parabolic interpolation gives an image coordinate, not a physical accuracy claim.
    offsets = []
    for axis, index, size in ((1, column, scores.shape[1]), (0, row, scores.shape[0])):
        offset = 0.0
        if 0 < index < size - 1:
            values = scores[row, column - 1:column + 2] if axis == 1 else scores[row - 1:row + 2, column]
            denominator = float(values[0] - 2 * values[1] + values[2])
            if denominator < -1e-6:
                offset = float(np.clip(.5 * (values[0] - values[2]) / denominator, -.5, .5))
        offsets.append(offset)
    return (left + column + patch_radius + offsets[0], top + row + patch_radius + offsets[1]), float(score), margin


def _local_flow(source, target, point, *, target_point=None):
    """Follow the marked tissue locally, rather than the whole leaf patch."""
    initial = np.asarray(point, dtype=np.float32).reshape(1, 1, 2)
    options = dict(winSize=(15, 15), maxLevel=3,
                   criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, .01))
    moved, status, _ = cv2.calcOpticalFlowPyrLK(source, target, initial, None, **options)
    if moved is None or not bool(status[0, 0]) or not np.isfinite(moved).all():
        return None, float("inf")
    returned, status, _ = cv2.calcOpticalFlowPyrLK(target, source, moved, None, **options)
    if returned is None or not bool(status[0, 0]) or not np.isfinite(returned).all():
        return None, float("inf")
    result = moved.reshape(2), float(np.linalg.norm(returned - initial))
    if target_point is None or (result[1] <= 1.5 and np.linalg.norm(result[0] - target_point) <= 3):
        return result
    # The coarse pyramid can attach a tiny shoot to a moving arm or leaf.
    # Re-solve locally from the independently matched patch; the same return
    # and location error limits still decide whether the result is usable.
    for level in (1, 0):
        local_options = {**options, "maxLevel": level, "flags": cv2.OPTFLOW_USE_INITIAL_FLOW}
        estimate = np.asarray(target_point, dtype=np.float32).reshape(1, 1, 2)
        refined, status, _ = cv2.calcOpticalFlowPyrLK(source, target, initial, estimate.copy(), **local_options)
        if refined is None or status is None or not status[0, 0] or not np.isfinite(refined).all():
            continue
        reverse, status, _ = cv2.calcOpticalFlowPyrLK(target, source, refined, initial.copy(), **local_options)
        if reverse is None or status is None or not status[0, 0] or not np.isfinite(reverse).all():
            continue
        error = float(np.linalg.norm(reverse - initial))
        if error < result[1] and np.linalg.norm(refined.reshape(2) - target_point) <= 3:
            result = refined.reshape(2), error
    return result


def track_tip_sequence(
    seed: TipTrackingFrame,
    point: tuple[float, float],
    frames: Sequence[TipTrackingFrame],
    *,
    cancel_check: Callable[[], None] | None = None,
    target_hint: tuple[float, float] | None = None,
    identity_seed: tuple[TipTrackingFrame, tuple[float, float]] | None = None,
    identity_verified: bool = False,
) -> tuple[TipCandidate2D | None, dict]:
    options = dict(cancel_check=cancel_check, target_hint=target_hint,
                   identity_seed=identity_seed, identity_verified=identity_verified)
    candidate, quality = _track_tip_sequence(seed, point, frames, **options)
    if candidate is not None or quality.get("reason") != "appearance_ambiguous_or_lost":
        return candidate, quality
    # A growing shoot changes the surrounding leaf patch before its own tissue
    # changes. Retry a smaller patch with stricter appearance/uniqueness checks;
    # keep the same flow, manual identity, visibility and return-error checks.
    recovered, detail = _track_tip_sequence(seed, point, frames, **options,
        patch_radius=7, minimum_correlation=.86, minimum_distinctiveness=.08)
    return (recovered, detail) if recovered is not None else (candidate, quality)


def _track_tip_sequence(
    seed, point, frames, *, cancel_check=None, target_hint=None,
    identity_seed=None, identity_verified=False, patch_radius=PATCH_RADIUS,
    minimum_correlation=.72, minimum_distinctiveness=.045,
):
    validate_tip_seed(seed, point)
    source, _ = _read(seed)
    gray = cv2.cvtColor(source, cv2.COLOR_BGR2GRAY)
    anchor_gray, anchor_point = gray, point
    if identity_seed is not None:
        identity_frame, anchor_point = identity_seed
        if identity_frame.camera_id != seed.camera_id:
            raise ValueError("尖端識別樣板必須來自同一個鏡頭。")
        validate_tip_seed(identity_frame, anchor_point)
        anchor_image, _ = _read(identity_frame)
        if anchor_image.shape != source.shape:
            raise ValueError("尖端識別樣板的影像尺寸不一致。")
        if not identity_verified:
            anchor_gray = cv2.cvtColor(anchor_image, cv2.COLOR_BGR2GRAY)
        else:
            # Only a track certified by this version may become a keyframe.
            # A locally consistent legacy estimate is not an identity proof.
            anchor_point = point
    minimum_score, minimum_margin, maximum_return_error = 1.0, 1.0, 0.0
    maximum_flow_error, maximum_anchor_error = 0.0, 0.0
    maximum_cross_view_error = 0.0
    cross_view_warning = False
    last_view_id = seed.view_id
    skipped_frames = 0
    consecutive_failures = 0
    keyframe_age = 0
    keyframe_updates = 0
    disambiguated_keyframes = 0
    for index, frame in enumerate(frames):
        if cancel_check:
            cancel_check()
        if frame.camera_id != seed.camera_id:
            raise ValueError("尖端追蹤只能延續同一個固定鏡頭。")
        image, valid = _read(frame)
        if image.shape != source.shape:
            return None, {"reason": "image_size_changed", "view_id": frame.view_id}
        target = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        next_point, score, margin = _match(gray, target, point, patch_radius=patch_radius)
        returned, reverse_score, _ = _match(target, gray, next_point, patch_radius=patch_radius)
        return_error = float(np.linalg.norm(np.asarray(returned) - point))
        flow_point, flow_error = _local_flow(gray, target, point,
            target_point=next_point if min(score, reverse_score) >= .9 and margin >= .1 else None)
        local_error = float(np.linalg.norm(flow_point - next_point)) if flow_point is not None else float("inf")
        # Keep the appearance fixed between verified keyframes. Keeping the
        # first 31px patch forever rejects genuine leaf growth; updating it on
        # every capture allows gradual drift. Refresh only with strong local
        # evidence after the fixed keyframe has also passed its identity check.
        anchor_match, anchor_score, anchor_margin = _match(anchor_gray, target, anchor_point,
            search_center=point, patch_radius=patch_radius)
        location = flow_point if flow_point is not None else np.asarray(next_point)
        anchor_error = float(np.linalg.norm(np.asarray(anchor_match) - location))
        hint_error = (float(np.linalg.norm(location - target_hint))
                      if target_hint is not None and index == len(frames) - 1 else 0.)
        strong_image_identity = (min(score, reverse_score, anchor_score) >= .9 and min(margin, anchor_margin) >= .15
                                 and flow_error <= .5 and anchor_error <= 1.5 and local_error <= 1.5)
        strong_local_identity = (min(score, reverse_score) >= .9 and margin >= .15
                                 and flow_error <= .5 and local_error <= 1.5)
        precise_local_identity = (min(score, reverse_score) >= .95 and margin >= .1
                                  and flow_error <= .25 and local_error <= .75)
        # A second similar leaf can make an older patch non-unique. It may
        # still witness identity when its best match agrees with two strong
        # local measurements and the source already has a verified chain.
        chain_disambiguates = ((strong_local_identity or precise_local_identity)
                              and anchor_score >= .8 and anchor_error <= 1.5
                              and (identity_verified or keyframe_updates > 0))
        if (score < minimum_correlation or reverse_score < minimum_correlation
                or margin < minimum_distinctiveness or return_error > 2
                or flow_error > 1.5 or local_error > 3 or anchor_score < minimum_correlation
                or (anchor_margin < minimum_distinctiveness and not chain_disambiguates)
                or anchor_error > 3 or (hint_error > 6 and not strong_image_identity)):
            if index < len(frames) - 1 and consecutive_failures < 8:
                # An arm passing through the side image must not become the
                # new template. Retain the last verified appearance and try
                # the next capture; never publish an occluded-frame estimate.
                consecutive_failures += 1
                skipped_frames += 1
                continue
            return None, {"reason": "appearance_ambiguous_or_lost", "view_id": frame.view_id,
                          "correlation": score, "distinctiveness": margin, "return_error_px": return_error,
                          "reverse_correlation": reverse_score, "anchor_correlation": anchor_score,
                          "anchor_distinctiveness": anchor_margin,
                          "flow_return_error_px": flow_error if np.isfinite(flow_error) else None,
                          "local_patch_error_px": local_error if np.isfinite(local_error) else None,
                          "anchor_error_px": anchor_error, "cross_view_error_px": hint_error,
                          "keyframe_updates": keyframe_updates, "keyframe_age": keyframe_age}
        next_point = tuple(float(value) for value in flow_point)
        try:
            validate_tip_seed(frame, next_point)
        except ValueError as error:
            if index < len(frames) - 1 and consecutive_failures < 8:
                consecutive_failures += 1
                skipped_frames += 1
                continue
            return None, {"reason": "foreground_or_visibility_failed", "view_id": frame.view_id, "detail": str(error)}
        minimum_score = min(minimum_score, score, reverse_score)
        minimum_margin = min(minimum_margin, margin)
        maximum_return_error = max(maximum_return_error, return_error)
        maximum_flow_error = max(maximum_flow_error, flow_error)
        maximum_anchor_error = max(maximum_anchor_error, anchor_error)
        maximum_cross_view_error = max(maximum_cross_view_error, hint_error)
        cross_view_warning |= hint_error > 6
        consecutive_failures = 0
        point, gray, source = next_point, target, image
        last_view_id = frame.view_id
        keyframe_age += 1
        disambiguated_keyframes += int(anchor_margin < .045)
        if keyframe_age >= KEYFRAME_INTERVAL and (strong_local_identity or precise_local_identity):
            anchor_gray, anchor_point = gray, point
            keyframe_age = 0
            keyframe_updates += 1
    confidence = float(np.clip(.7 + .3 * (minimum_score - minimum_correlation) / (1 - minimum_correlation), .7, 1))
    return TipCandidate2D(candidate_id=f"{last_view_id}:tracked_apex", x_px=float(point[0]), y_px=float(point[1]),
                          confidence=confidence, visibility_confidence=confidence, source="shoot_apex"), {
        "version": TIP_TRACKING_VERSION, "frame_count": len(frames), "minimum_correlation": minimum_score,
        "minimum_distinctiveness": minimum_margin, "maximum_return_error_px": maximum_return_error,
        "skipped_occluded_frames": skipped_frames,
        "maximum_flow_return_error_px": maximum_flow_error, "maximum_anchor_error_px": maximum_anchor_error,
        "identity_checks": "local_flow+verified_keyframes+forward_backward",
        "identity_verified": True, "keyframe_updates": keyframe_updates,
        "patch_radius_px": patch_radius,
        "disambiguated_keyframes": disambiguated_keyframes,
        "cross_view_checked": target_hint is not None and bool(frames),
        "cross_view_disagreement": cross_view_warning,
        "maximum_cross_view_error_px": maximum_cross_view_error,
    }
