from __future__ import annotations

from dataclasses import dataclass
from math import hypot


Point = tuple[float, float]


@dataclass(frozen=True)
class CandidateSelection:
    selected: Point | None
    detection_type: str
    requires_manual_initialization: bool = False


def select_temporal_candidate(
    candidates: list[Point],
    previous_point: Point | None,
) -> CandidateSelection:
    if not candidates:
        return CandidateSelection(None, "Missing")
    if len(candidates) == 1:
        return CandidateSelection(candidates[0], "Automatic")
    if previous_point is None:
        return CandidateSelection(
            None,
            "Missing",
            requires_manual_initialization=True,
        )
    selected = min(
        enumerate(candidates),
        key=lambda item: (
            hypot(
                item[1][0] - previous_point[0],
                item[1][1] - previous_point[1],
            ),
            item[0],
        ),
    )[1]
    return CandidateSelection(selected, "Estimated")
