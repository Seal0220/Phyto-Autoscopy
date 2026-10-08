from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations, product
from typing import Any, Sequence

import numpy as np

from app.analysis.reconstruction.multiview import (
    robust_multiview_triangulate,
)
from app.analysis.tip.candidate_detector import TipCandidate2D


@dataclass(frozen=True, slots=True)
class TipCandidateView:
    view_id: str
    camera_id: str
    projection_matrix: np.ndarray
    camera_center_world_mm: np.ndarray
    candidates: tuple[TipCandidate2D, ...]


@dataclass(frozen=True, slots=True)
class TriangulatedTipHypothesis:
    point_world_mm: np.ndarray
    observations: tuple[tuple[str, TipCandidate2D], ...]
    reprojection_errors_px: tuple[float, ...]
    used_observations: tuple[bool, ...]
    mean_error_px: float
    maximum_error_px: float
    angular_spread_deg: float
    confidence: float
    aggregation_quality: dict[str, Any] = field(default_factory=dict)


def _project(
    projection: np.ndarray,
    point: np.ndarray,
) -> np.ndarray | None:
    homogeneous = np.append(point, 1.0)
    projected = projection @ homogeneous
    if not np.isfinite(projected).all() or projected[2] <= 1e-8:
        return None
    return projected[:2] / projected[2]


def _angular_spread(
    point: np.ndarray,
    centers: Sequence[np.ndarray],
) -> float:
    maximum = 0.0
    for first, second in combinations(centers, 2):
        left = first - point
        right = second - point
        denominator = np.linalg.norm(left) * np.linalg.norm(right)
        if denominator <= 1e-9:
            continue
        cosine = float(np.clip(np.dot(left, right) / denominator, -1.0, 1.0))
        maximum = max(maximum, float(np.degrees(np.arccos(cosine))))
    return maximum


def _nearest_candidate(
    view: TipCandidateView,
    pixel: np.ndarray,
    threshold_px: float,
) -> TipCandidate2D | None:
    if not view.candidates:
        return None
    distances = [
        float(np.hypot(item.x_px - pixel[0], item.y_px - pixel[1]))
        for item in view.candidates
    ]
    index = int(np.argmin(distances))
    return view.candidates[index] if distances[index] <= threshold_px else None


def _hypothesis_from_seed(
    views: Sequence[TipCandidateView],
    seed_indices: tuple[int, int],
    seed_candidates: tuple[TipCandidate2D, TipCandidate2D],
    *,
    rejection_threshold_px: float,
) -> TriangulatedTipHypothesis | None:
    selected_views = [views[index] for index in seed_indices]
    seed_result = robust_multiview_triangulate(
        [item.projection_matrix for item in selected_views],
        [(item.x_px, item.y_px) for item in seed_candidates],
        confidence=[item.confidence for item in seed_candidates],
        rejection_threshold_px=rejection_threshold_px,
    )
    point = seed_result.point
    observations: list[tuple[str, TipCandidate2D]] = [
        (view.view_id, candidate)
        for view, candidate in zip(selected_views, seed_candidates)
    ]
    observation_views: list[TipCandidateView] = list(selected_views)
    for index, view in enumerate(views):
        if index in seed_indices:
            continue
        pixel = _project(view.projection_matrix, point)
        if pixel is None:
            continue
        candidate = _nearest_candidate(
            view,
            pixel,
            rejection_threshold_px * 1.5,
        )
        if candidate is None:
            continue
        observations.append((view.view_id, candidate))
        observation_views.append(view)
    if len(observations) < 2:
        return None

    refined = robust_multiview_triangulate(
        [item.projection_matrix for item in observation_views],
        [
            (candidate.x_px, candidate.y_px)
            for _, candidate in observations
        ],
        confidence=[
            candidate.confidence * candidate.visibility_confidence
            for _, candidate in observations
        ],
        camera_ids=[item.camera_id for item in observation_views],
        rejection_threshold_px=rejection_threshold_px,
    )
    errors = np.asarray(refined.reprojection_errors_px, dtype=np.float64)
    used = np.asarray(refined.used_observations, dtype=bool)
    if used.sum() < 2 or not np.isfinite(errors[used]).all():
        return None
    spread = _angular_spread(
        refined.point,
        [
            view.camera_center_world_mm
            for view, keep in zip(observation_views, used)
            if keep
        ],
    )
    mean_error = float(np.mean(errors[used]))
    maximum_error = float(np.max(errors[used]))
    if maximum_error > rejection_threshold_px:
        return None
    observation_confidence = float(np.mean([
        candidate.confidence * candidate.visibility_confidence
        for (_, candidate), keep in zip(observations, used)
        if keep
    ]))
    spread_score = float(np.clip(spread / 45.0, 0.0, 1.0))
    error_score = float(np.exp(-mean_error / max(rejection_threshold_px, 1.0)))
    view_score = float(np.clip(used.sum() / 5.0, 0.0, 1.0))
    confidence = float(np.clip(
        0.40 * observation_confidence
        + 0.25 * error_score
        + 0.20 * spread_score
        + 0.15 * view_score,
        0.0,
        1.0,
    ))
    return TriangulatedTipHypothesis(
        point_world_mm=refined.point,
        observations=tuple(observations),
        reprojection_errors_px=tuple(float(value) for value in errors),
        used_observations=tuple(bool(value) for value in used),
        mean_error_px=mean_error,
        maximum_error_px=maximum_error,
        angular_spread_deg=spread,
        confidence=confidence,
        aggregation_quality={
            **refined.quality,
            "supporting_camera_counts": {
                camera: sum(
                    view.camera_id == camera and bool(keep)
                    for view, keep in zip(observation_views, used)
                )
                for camera in ("top", "side", "rotating")
            },
        },
    )


def triangulate_tip_hypotheses(
    views: Sequence[TipCandidateView],
    *,
    rejection_threshold_px: float = 8.0,
    maximum_candidates_per_view: int = 6,
    maximum_hypotheses: int = 24,
) -> tuple[TriangulatedTipHypothesis, ...]:
    camera_order = {"top": 0, "side": 1, "rotating": 2}
    usable = sorted(
        (item for item in views if item.candidates),
        key=lambda item: (camera_order.get(item.camera_id, 3), item.view_id),
    )
    if len(usable) < 2:
        return ()
    hypotheses: list[TriangulatedTipHypothesis] = []
    # All camera pairs can seed a hypothesis. This keeps rotating observations
    # active when one fixed-view tip is occluded instead of using them only as
    # a local verification pass after fixed stereo.
    seed_indices = []
    for camera in dict.fromkeys(view.camera_id for view in usable):
        indices = [i for i, view in enumerate(usable) if view.camera_id == camera]
        limit = 8 if camera == "rotating" else 3
        if len(indices) <= limit:
            seed_indices.extend(indices)
            continue
        best = max(indices, key=lambda i: max(c.confidence * c.visibility_confidence for c in usable[i].candidates))
        selected = [best]
        if camera == "rotating":
            while len(selected) < limit:
                remaining = [i for i in indices if i not in selected]
                selected.append(max(remaining, key=lambda i: min(np.linalg.norm(usable[i].camera_center_world_mm - usable[j].camera_center_world_mm) for j in selected)))
        else:
            selected.extend(i for i in (indices[0], indices[-1]) if i not in selected)
            for index in indices:
                if len(selected) >= limit:
                    break
                if index not in selected:
                    selected.append(index)
        seed_indices.extend(selected)
    # Bound hypothesis generation, then fit every matching observation from
    # every view. Adding hundreds of repeated frames no longer grows as N^3.
    for first_index, second_index in combinations(seed_indices, 2):
        first = usable[first_index]
        second = usable[second_index]
        baseline = np.linalg.norm(
            first.camera_center_world_mm - second.camera_center_world_mm
        )
        if baseline < 5.0:
            continue
        for first_candidate, second_candidate in product(
            first.candidates[:maximum_candidates_per_view],
            second.candidates[:maximum_candidates_per_view],
        ):
            try:
                hypothesis = _hypothesis_from_seed(
                    usable,
                    (first_index, second_index),
                    (first_candidate, second_candidate),
                    rejection_threshold_px=rejection_threshold_px,
                )
            except (ValueError, np.linalg.LinAlgError):
                continue
            if hypothesis is None:
                continue
            hypotheses.append(hypothesis)
    hypotheses.sort(
        key=lambda item: (
            -sum(count > 0 for count in item.aggregation_quality["supporting_camera_counts"].values()),
            -sum(item.used_observations),
            -item.confidence,
            item.mean_error_px,
        )
    )
    distinct: list[TriangulatedTipHypothesis] = []
    for hypothesis in hypotheses:
        if any(
            np.linalg.norm(
                hypothesis.point_world_mm - existing.point_world_mm
            ) < 2.0
            for existing in distinct
        ):
            continue
        distinct.append(hypothesis)
        if len(distinct) >= maximum_hypotheses:
            break
    return tuple(distinct)


__all__ = [
    "TipCandidateView",
    "TriangulatedTipHypothesis",
    "triangulate_tip_hypotheses",
]
