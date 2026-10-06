from __future__ import annotations

from app.analysis.tip.trajectory_linker import (
    link_tip_trajectory,
    order_analysis_rounds,
)
from app.models.analysis_models import AnalysisRound, TipLandmark


def _round(round_id: str, timestamp: str) -> AnalysisRound:
    return AnalysisRound(
        analysis_id="analysis",
        round_key=f"record:mode:{round_id}",
        record_id="record",
        mode_id="mode",
        round_id=round_id,
        started_at=timestamp,
        status="ready_tip_only",
    )


def test_temporal_prior_uses_capture_time_not_lexicographic_round_id() -> None:
    later = _round("round.10", "2026-07-22T10:10:00Z")
    earlier = _round("round.2", "2026-07-22T10:02:00Z")

    assert order_analysis_rounds((later, earlier)) == (earlier, later)


def test_single_missing_tip_is_interpolated_only_with_reliable_motion() -> None:
    rounds = [
        _round(f"round.{index:02d}", f"2026-07-22T10:00:{index * 10:02d}Z")
        for index in range(5)
    ]
    landmarks = [
        TipLandmark(
            analysis_id="analysis",
            tip_id=f"tip.{index}",
            round_key=item.round_key,
            record_id="record",
            mode_id="mode",
            round_id=item.round_id,
            x_mm=float(index) if index != 2 else None,
            y_mm=0.0 if index != 2 else None,
            z_mm=400.0 if index != 2 else None,
            confidence=0.9 if index != 2 else 0.0,
            valid=index != 2,
            source="fixed_triangulation" if index != 2 else "invalid",
            detection_type="measured" if index != 2 else "invalid",
        )
        for index, item in enumerate(rounds)
    ]

    result = link_tip_trajectory(rounds, landmarks)
    assert result.points[2].detection_type == "interpolated"
    assert result.points[2].x_mm == 2.0

    blocked = link_tip_trajectory(
        rounds,
        landmarks,
        blocked_interpolation_round_keys={rounds[2].round_key},
    )
    assert blocked.points[2].detection_type == "invalid"
    assert blocked.points[2].x_mm is None
