from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, product
from typing import Sequence

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
    observations: list[tuple[str, TipCandidate2D]] = []
    observation_views: list[TipCandidateView] = []
    for view in views:
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
    )


def triangulate_tip_hypotheses(
    views: Sequence[TipCandidateView],
    *,
    rejection_threshold_px: float = 8.0,
    maximum_candidates_per_view: int = 6,
    maximum_hypotheses: int = 24,
) -> tuple[TriangulatedTipHypothesis, ...]:
    usable = [item for item in views if item.candidates]
    if len(usable) < 2:
        return ()
    hypotheses: list[TriangulatedTipHypothesis] = []
    for first_index, second_index in combinations(range(len(usable)), 2):
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
            if any(
                np.linalg.norm(
                    hypothesis.point_world_mm - existing.point_world_mm
                ) < 2.0
                for existing in hypotheses
            ):
                continue
            hypotheses.append(hypothesis)
    hypotheses.sort(
        key=lambda item: (
            -item.confidence,
            item.mean_error_px,
            -len(item.observations),
        )
    )
    return tuple(hypotheses[:maximum_hypotheses])


__all__ = [
    "TipCandidateView",
    "TriangulatedTipHypothesis",
    "triangulate_tip_hypotheses",
]
