from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime


INTERPOLATION_BARRIERS = frozenset({
    "camera_disconnected",
    "record_interrupted",
    "unpaired",
    "Invalid",
    "lighting_transition",
    "background_initialization",
})


@dataclass(frozen=True)
class TrackPoint:
    frame_id: int
    timestamp: str | None
    x_px: float | None
    y_px: float | None
    detection_type: str
    valid: bool
    barrier: str | None = None


def _timestamp_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def interpolate_missing_track(
    points: list[TrackPoint],
    *,
    maximum_gap_seconds: float | None,
) -> list[TrackPoint]:
    resolved = list(points)
    index = 0
    while index < len(resolved):
        current = resolved[index]
        if current.x_px is not None or current.y_px is not None:
            index += 1
            continue
        start = index
        while (
            index < len(resolved)
            and resolved[index].x_px is None
            and resolved[index].y_px is None
        ):
            index += 1
        end = index - 1
        before_index = start - 1
        after_index = index
        if before_index < 0 or after_index >= len(resolved):
            continue
        before = resolved[before_index]
        after = resolved[after_index]
        segment = resolved[before_index:after_index + 1]
        if (
            not before.valid
            or not after.valid
            or before.x_px is None
            or before.y_px is None
            or after.x_px is None
            or after.y_px is None
            or any(
                item.barrier in INTERPOLATION_BARRIERS
                or item.detection_type in {"Invalid", "lighting_transition"}
                for item in segment
            )
        ):
            continue
        before_time = _timestamp_seconds(before.timestamp)
        after_time = _timestamp_seconds(after.timestamp)
        if (
            maximum_gap_seconds is not None
            and before_time is not None
            and after_time is not None
            and after_time - before_time > maximum_gap_seconds
        ):
            continue
        denominator = after_index - before_index
        for missing_index in range(start, end + 1):
            ratio = (missing_index - before_index) / denominator
            resolved[missing_index] = replace(
                resolved[missing_index],
                x_px=before.x_px + (after.x_px - before.x_px) * ratio,
                y_px=before.y_px + (after.y_px - before.y_px) * ratio,
                detection_type="Interpolated",
                valid=True,
            )
    return resolved
