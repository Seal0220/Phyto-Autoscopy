from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from app.analysis.tip.candidate_matcher import TriangulatedTipHypothesis
from app.analysis.tip.skeleton_extractor import SkeletonEndpoint


@dataclass(frozen=True, slots=True)
class OptimizedTipMarker:
    position_world_mm: np.ndarray
    hypothesis: TriangulatedTipHypothesis
    confidence: float
    source: str
    distance_to_model_mm: float | None
    distance_to_skeleton_mm: float | None
    temporal_distance_mm: float | None
    selected_endpoint_id: str | None
    quality: dict[str, float | int | str | None]


def optimize_tip_marker(
    hypotheses: Sequence[TriangulatedTipHypothesis],
    *,
    skeleton_endpoints: Sequence[SkeletonEndpoint] = (),
    previous_position_mm: np.ndarray | None = None,
) -> OptimizedTipMarker:
    if not hypotheses:
        raise ValueError("沒有可用的多視角尖端標記假設。")
    best = None
    for hypothesis in hypotheses:
        endpoint = None
        endpoint_distance = None
        if skeleton_endpoints:
            distances = [
                float(np.linalg.norm(item.position_mm - hypothesis.point_world_mm))
                for item in skeleton_endpoints
            ]
            endpoint_index = int(np.argmin(distances))
            endpoint = skeleton_endpoints[endpoint_index]
            endpoint_distance = distances[endpoint_index]
        temporal_distance = (
            float(np.linalg.norm(hypothesis.point_world_mm - previous_position_mm))
            if previous_position_mm is not None
            else None
        )
        reprojection_cost = hypothesis.mean_error_px / 8.0
        endpoint_cost = (
            min(endpoint_distance / 15.0, 3.0)
            if endpoint_distance is not None
            else 0.6
        )
        main_axis_cost = 1.0 - endpoint.main_axis_score if endpoint else 0.5
        temporal_cost = (
            min(temporal_distance / 80.0, 2.0)
            if temporal_distance is not None
            else 0.0
        )
        visibility_cost = 1.0 - hypothesis.confidence
        cost = (
            0.48 * reprojection_cost
            + 0.23 * endpoint_cost
            + 0.13 * main_axis_cost
            + 0.06 * temporal_cost
            + 0.10 * visibility_cost
        )
        candidate = (cost, hypothesis, endpoint, endpoint_distance, temporal_distance)
        if best is None or candidate[0] < best[0]:
            best = candidate
    assert best is not None
    cost, hypothesis, endpoint, endpoint_distance, temporal_distance = best
    position = hypothesis.point_world_mm.copy()
    if endpoint is not None and endpoint_distance is not None and endpoint_distance <= 20.0:
        blend = float(np.clip(hypothesis.confidence, 0.45, 0.9))
        position = blend * position + (1.0 - blend) * endpoint.position_mm
    model_score = (
        float(np.exp(-endpoint_distance / 15.0))
        if endpoint_distance is not None
        else 0.5
    )
    temporal_score = (
        float(np.exp(-temporal_distance / 100.0))
        if temporal_distance is not None
        else 0.75
    )
    confidence = float(np.clip(
        0.58 * hypothesis.confidence
        + 0.27 * model_score
        + 0.10 * temporal_score
        + 0.05 * min(hypothesis.angular_spread_deg / 45.0, 1.0),
        0,
        1,
    ))
    return OptimizedTipMarker(
        position_world_mm=position,
        hypothesis=hypothesis,
        confidence=confidence,
        source=(
            "multiview_joint"
            if endpoint is not None
            or sum(hypothesis.used_observations) > 2
            else "top_side_triangulation"
        ),
        distance_to_model_mm=endpoint_distance,
        distance_to_skeleton_mm=endpoint_distance,
        temporal_distance_mm=temporal_distance,
        selected_endpoint_id=endpoint.endpoint_id if endpoint else None,
        quality={
            "joint_cost": float(cost),
            "angular_spread_deg": hypothesis.angular_spread_deg,
            "supporting_view_count": int(sum(hypothesis.used_observations)),
            "selected_endpoint_id": endpoint.endpoint_id if endpoint else None,
        },
    )


__all__ = ["OptimizedTipMarker", "optimize_tip_marker"]
