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

TIP_TRACKING_VERSION = 1
PATCH_RADIUS = 15
SEARCH_RADIUS = 64


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
        raise ValueError("尖端追蹤缺少一致的去畸變影像與有效像素遮罩。")
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
        raise ValueError("尖端追蹤範圍包含無效的去畸變像素，請重新標記。")
    foreground_distance = _foreground_distance(image, valid, point)
    if foreground_distance > 8:
        raise ValueError("尖端標記沒有靠近植物組織，請確認沒有標到燈或背景。")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    texture = float(cv2.getRectSubPix(gray, (31, 31), (float(x), float(y))).std())
    if texture < 4:
        raise ValueError("尖端附近缺少可追蹤的影像細節，請重新標記清楚的生長尖端。")
    return {"foreground_distance_px": foreground_distance, "texture_std": texture}


def _match(source, target, point):
    x, y = point
    patch = cv2.getRectSubPix(source, (31, 31), (float(x), float(y)))
    left, top = max(0, int(x) - SEARCH_RADIUS - PATCH_RADIUS), max(0, int(y) - SEARCH_RADIUS - PATCH_RADIUS)
    right = min(target.shape[1], int(x) + SEARCH_RADIUS + PATCH_RADIUS + 1)
    bottom = min(target.shape[0], int(y) + SEARCH_RADIUS + PATCH_RADIUS + 1)
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
    return (left + column + PATCH_RADIUS + offsets[0], top + row + PATCH_RADIUS + offsets[1]), float(score), margin


def track_tip_sequence(
    seed: TipTrackingFrame,
    point: tuple[float, float],
    frames: Sequence[TipTrackingFrame],
    *,
    cancel_check: Callable[[], None] | None = None,
) -> tuple[TipCandidate2D | None, dict]:
    validate_tip_seed(seed, point)
    source, _ = _read(seed)
    gray = cv2.cvtColor(source, cv2.COLOR_BGR2GRAY)
    minimum_score, minimum_margin, maximum_return_error = 1.0, 1.0, 0.0
    last_view_id = seed.view_id
    skipped_frames = 0
    consecutive_failures = 0
    for index, frame in enumerate(frames):
        if cancel_check:
            cancel_check()
        if frame.camera_id != seed.camera_id:
            raise ValueError("尖端追蹤只能延續同一個固定鏡頭。")
        image, valid = _read(frame)
        if image.shape != source.shape:
            return None, {"reason": "image_size_changed", "view_id": frame.view_id}
        target = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        next_point, score, margin = _match(gray, target, point)
        returned, reverse_score, _ = _match(target, gray, next_point)
        return_error = float(np.linalg.norm(np.asarray(returned) - point))
        if score < .72 or reverse_score < .72 or margin < .045 or return_error > 2:
            if index < len(frames) - 1 and consecutive_failures < 8:
                # An arm passing through the side image must not become the
                # new template. Retain the last verified appearance and try
                # the next capture; never publish an occluded-frame estimate.
                consecutive_failures += 1
                skipped_frames += 1
                continue
            return None, {"reason": "appearance_ambiguous_or_lost", "view_id": frame.view_id,
                          "correlation": score, "distinctiveness": margin, "return_error_px": return_error}
        try:
            validate_tip_seed(frame, next_point)
        except ValueError as error:
            return None, {"reason": "foreground_or_visibility_failed", "view_id": frame.view_id, "detail": str(error)}
        minimum_score = min(minimum_score, score, reverse_score)
        minimum_margin = min(minimum_margin, margin)
        maximum_return_error = max(maximum_return_error, return_error)
        consecutive_failures = 0
        point, gray, source = next_point, target, image
        last_view_id = frame.view_id
    confidence = float(np.clip(.7 + .3 * (minimum_score - .72) / .28, .7, 1))
    return TipCandidate2D(candidate_id=f"{last_view_id}:tracked_apex", x_px=float(point[0]), y_px=float(point[1]),
                          confidence=confidence, visibility_confidence=confidence, source="shoot_apex"), {
        "version": TIP_TRACKING_VERSION, "frame_count": len(frames), "minimum_correlation": minimum_score,
        "minimum_distinctiveness": minimum_margin, "maximum_return_error_px": maximum_return_error,
        "skipped_occluded_frames": skipped_frames,
    }
