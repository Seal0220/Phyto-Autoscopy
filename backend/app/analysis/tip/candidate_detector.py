from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np

from app.analysis.image_probe import read_analysis_image
from app.analysis.checkpoints import StepJournal, step_signature

from app.analysis.segmentation.plant_mask import create_plant_mask


@dataclass(frozen=True, slots=True)
class TipCandidate2D:
    candidate_id: str
    x_px: float
    y_px: float
    confidence: float
    visibility_confidence: float
    source: str


@dataclass(frozen=True, slots=True)
class TipCandidateDetection:
    candidates: tuple[TipCandidate2D, ...]
    plant_mask: np.ndarray
    skeleton: np.ndarray
    heatmap: np.ndarray
    mask_confidence: float
    foreground_ratio: float


def _read_image(path: Path, flags: int) -> np.ndarray:
    image = read_analysis_image(path, flags)
    if image is None:
        raise ValueError(f"尖端候選影像無法解碼：{path.name}")
    return image


def _skeletonize(mask: np.ndarray) -> np.ndarray:
    ximgproc = getattr(cv2, "ximgproc", None)
    if ximgproc is not None and hasattr(ximgproc, "thinning"):
        return ximgproc.thinning(mask)
    working = mask.copy()
    skeleton = np.zeros_like(mask)
    element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    while cv2.countNonZero(working) > 0:
        eroded = cv2.erode(working, element)
        opened = cv2.dilate(eroded, element)
        skeleton = cv2.bitwise_or(
            skeleton,
            cv2.subtract(working, opened),
        )
        working = eroded
    return skeleton


def _endpoint_pixels(skeleton: np.ndarray) -> list[tuple[int, int]]:
    binary = (skeleton > 0).astype(np.uint8)
    neighbours = cv2.filter2D(
        binary,
        cv2.CV_16U,
        np.ones((3, 3), dtype=np.uint8),
        borderType=cv2.BORDER_CONSTANT,
    )
    ys, xs = np.nonzero((binary > 0) & (neighbours == 2))
    return [(int(x), int(y)) for x, y in zip(xs, ys)]


def _contour_candidates(mask: np.ndarray) -> list[tuple[int, int]]:
    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    candidates: list[tuple[int, int]] = []
    for contour in contours:
        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue
        polygon = cv2.approxPolyDP(contour, max(2.0, perimeter * 0.012), True)
        candidates.extend(
            (int(point[0][0]), int(point[0][1]))
            for point in polygon
        )
    return candidates


def _candidate_heatmap(
    shape: tuple[int, int],
    candidates: tuple[TipCandidate2D, ...],
) -> np.ndarray:
    heat = np.zeros(shape, dtype=np.float32)
    radius = max(3, int(min(shape) * 0.015))
    for candidate in candidates:
        cv2.circle(
            heat,
            (int(round(candidate.x_px)), int(round(candidate.y_px))),
            radius,
            float(candidate.confidence),
            thickness=-1,
        )
    sigma = max(2.0, min(shape) * 0.012)
    heat = cv2.GaussianBlur(heat, (0, 0), sigmaX=sigma, sigmaY=sigma)
    maximum = float(heat.max())
    if maximum > 0:
        heat = heat / maximum
    return cv2.applyColorMap(
        np.clip(heat * 255.0, 0, 255).astype(np.uint8),
        cv2.COLORMAP_TURBO,
    )


def _detect_tip_candidates(
    image_path: Path,
    *,
    valid_mask_path: Path | None = None,
    candidate_prefix: str = "candidate",
    maximum_candidates: int = 12,
) -> TipCandidateDetection:
    image = _read_image(image_path, cv2.IMREAD_COLOR)
    valid_mask = (
        _read_image(valid_mask_path, cv2.IMREAD_GRAYSCALE)
        if valid_mask_path is not None
        else None
    )
    segmentation = create_plant_mask(
        image,
        valid_pixel_mask=valid_mask,
    )
    skeleton = _skeletonize(segmentation.mask)
    endpoints = _endpoint_pixels(skeleton)
    raw = [(x, y, "skeleton_endpoint") for x, y in endpoints]
    raw.extend(
        (x, y, "geometric_endpoint")
        for x, y in _contour_candidates(segmentation.mask)
    )
    if not raw:
        return TipCandidateDetection(
            candidates=(),
            plant_mask=segmentation.mask,
            skeleton=skeleton,
            heatmap=np.zeros((*segmentation.mask.shape, 3), dtype=np.uint8),
            mask_confidence=segmentation.confidence,
            foreground_ratio=segmentation.foreground_ratio,
        )

    height, width = segmentation.mask.shape
    distance = cv2.distanceTransform(segmentation.mask, cv2.DIST_L2, 5)
    distance_scale = max(float(np.percentile(distance[distance > 0], 85)), 1.0)
    scored = []
    for x, y, source in raw:
        border_distance = min(x, y, width - 1 - x, height - 1 - y)
        visibility = float(np.clip(border_distance / max(min(width, height) * 0.08, 1.0), 0, 1))
        radius_score = float(np.clip(distance[y, x] / distance_scale, 0, 1))
        source_score = 1.0 if source == "skeleton_endpoint" else 0.68
        confidence = float(np.clip(
            0.38 * source_score
            + 0.25 * segmentation.confidence
            + 0.20 * visibility
            + 0.17 * radius_score,
            0,
            1,
        ))
        scored.append((confidence, visibility, x, y, source))
    scored.sort(reverse=True)

    minimum_separation = max(5.0, min(width, height) * 0.025)
    retained: list[tuple[float, float, int, int, str]] = []
    for item in scored:
        _, _, x, y, _ = item
        if any(
            np.hypot(x - selected[2], y - selected[3]) < minimum_separation
            for selected in retained
        ):
            continue
        retained.append(item)
        if len(retained) >= maximum_candidates:
            break
    candidates = tuple(
        TipCandidate2D(
            candidate_id=f"{candidate_prefix}:{index:02d}",
            x_px=float(x),
            y_px=float(y),
            confidence=confidence,
            visibility_confidence=visibility,
            source=source,
        )
        for index, (confidence, visibility, x, y, source) in enumerate(
            retained,
            start=1,
        )
    )
    return TipCandidateDetection(
        candidates=candidates,
        plant_mask=segmentation.mask,
        skeleton=skeleton,
        heatmap=_candidate_heatmap(segmentation.mask.shape, candidates),
        mask_confidence=segmentation.confidence,
        foreground_ratio=segmentation.foreground_ratio,
    )


def detect_tip_candidates(
    image_path: Path,
    *,
    valid_mask_path: Path | None = None,
    candidate_prefix: str = "candidate",
    maximum_candidates: int = 12,
    checkpoint_root: Path | None = None,
) -> TipCandidateDetection:
    if checkpoint_root is None:
        return _detect_tip_candidates(image_path, valid_mask_path=valid_mask_path,
                                      candidate_prefix=candidate_prefix, maximum_candidates=maximum_candidates)
    paths = [image_path, *([valid_mask_path] if valid_mask_path is not None else [])]
    signature = step_signature({"version": 1, "count": maximum_candidates,
                                "inputs": [(str(path), path.stat().st_size, path.stat().st_mtime_ns) for path in paths]})
    with StepJournal(checkpoint_root) as journal:
        saved = journal.get("detecting_tip_candidates", candidate_prefix, signature)
        if saved is not None:
            with np.load(saved["arrays"], allow_pickle=False) as arrays:
                return TipCandidateDetection(
                    candidates=tuple(TipCandidate2D(**item) for item in saved["candidates"]),
                    plant_mask=arrays["plant_mask"], skeleton=arrays["skeleton"], heatmap=arrays["heatmap"],
                    mask_confidence=saved["mask_confidence"], foreground_ratio=saved["foreground_ratio"],
                )
        result = _detect_tip_candidates(image_path, valid_mask_path=valid_mask_path,
                                        candidate_prefix=candidate_prefix, maximum_candidates=maximum_candidates)
        destination = checkpoint_root / "checkpoints" / "tip_candidates" / f"{step_signature(candidate_prefix)}.npz"
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("wb") as handle:
                np.savez_compressed(handle, plant_mask=result.plant_mask, skeleton=result.skeleton, heatmap=result.heatmap)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        journal.save("detecting_tip_candidates", candidate_prefix, signature, {
            "arrays": str(destination), "candidates": [asdict(item) for item in result.candidates],
            "mask_confidence": result.mask_confidence, "foreground_ratio": result.foreground_ratio,
        }, outputs=[destination])
        return result


__all__ = [
    "TipCandidate2D",
    "TipCandidateDetection",
    "detect_tip_candidates",
]
