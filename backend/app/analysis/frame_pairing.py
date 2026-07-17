from __future__ import annotations

import math
from collections.abc import Sequence

from app.analysis.record_validator import CaptureFrame
from app.models.analysis_models import AnalysisFramePair


def _timestamp_delta_ms(top: CaptureFrame, side: CaptureFrame) -> float:
    return abs((side.timestamp_value - top.timestamp_value).total_seconds()) * 1000.0


def _sort_key(frame: CaptureFrame) -> tuple[object, int, int]:
    return frame.timestamp_value, frame.source_index, frame.capture_id


def _optimal_timestamp_matches(
    top_indices: Sequence[int],
    side_indices: Sequence[int],
    top_frames: Sequence[CaptureFrame],
    side_frames: Sequence[CaptureFrame],
) -> list[tuple[int, int]]:
    """Match the smaller sequence into the larger with minimum total time delta."""

    if not top_indices or not side_indices:
        return []
    top_ordered = tuple(sorted(top_indices, key=lambda index: _sort_key(top_frames[index])))
    side_ordered = tuple(sorted(side_indices, key=lambda index: _sort_key(side_frames[index])))

    if len(top_ordered) <= len(side_ordered):
        smaller = top_ordered
        larger = side_ordered
        smaller_is_top = True
    else:
        smaller = side_ordered
        larger = top_ordered
        smaller_is_top = False

    def match_cost(smaller_index: int, larger_index: int) -> float:
        if smaller_is_top:
            return _timestamp_delta_ms(
                top_frames[smaller[smaller_index]],
                side_frames[larger[larger_index]],
            )
        return _timestamp_delta_ms(
            top_frames[larger[larger_index]],
            side_frames[smaller[smaller_index]],
        )

    extra_larger_frames = len(larger) - len(smaller)
    previous_costs = {
        larger_position: 0.0
        for larger_position in range(extra_larger_frames + 1)
    }
    decisions: dict[tuple[int, int], bool] = {}
    for smaller_position in range(1, len(smaller) + 1):
        current_costs: dict[int, float] = {}
        first_larger_position = smaller_position
        last_larger_position = smaller_position + extra_larger_frames
        for larger_position in range(first_larger_position, last_larger_position + 1):
            matched_cost = previous_costs[larger_position - 1] + match_cost(
                smaller_position - 1,
                larger_position - 1,
            )
            skipped_cost = current_costs.get(larger_position - 1, float("inf"))
            use_match = matched_cost <= skipped_cost
            current_costs[larger_position] = (
                matched_cost if use_match else skipped_cost
            )
            decisions[(smaller_position, larger_position)] = use_match
        previous_costs = current_costs

    positions: list[tuple[int, int]] = []
    smaller_position = len(smaller)
    larger_position = len(larger)
    while smaller_position:
        if decisions[(smaller_position, larger_position)]:
            positions.append((smaller_position - 1, larger_position - 1))
            smaller_position -= 1
        larger_position -= 1
    positions.reverse()
    matches: list[tuple[int, int]] = []
    for smaller_position, larger_position in positions:
        if smaller_is_top:
            matches.append((smaller[smaller_position], larger[larger_position]))
        else:
            matches.append((larger[larger_position], smaller[smaller_position]))
    return matches


def _pair_cycle_id(top: CaptureFrame | None, side: CaptureFrame | None) -> int | None:
    if top is None:
        return side.cycle_id if side else None
    if side is None:
        return top.cycle_id
    if top.cycle_id == side.cycle_id:
        return top.cycle_id
    if top.cycle_id is None:
        return side.cycle_id
    if side.cycle_id is None:
        return top.cycle_id
    return None


def pair_capture_frames(
    top_frames: Sequence[CaptureFrame],
    side_frames: Sequence[CaptureFrame],
    rotating_frames: Sequence[CaptureFrame] = (),
    *,
    timestamp_tolerance_ms: float = 1000.0,
    manual_frame_offset: int = 0,
) -> list[AnalysisFramePair]:
    if not math.isfinite(timestamp_tolerance_ms) or timestamp_tolerance_ms < 0:
        raise ValueError("時間戳容差不可小於 0。")
    if isinstance(manual_frame_offset, bool) or not isinstance(manual_frame_offset, int):
        raise TypeError("人工影格偏移量必須是整數。")
    if any(frame.camera_id != "top" for frame in top_frames):
        raise ValueError("top_frames 只能包含俯視影格。")
    if any(frame.camera_id != "side" for frame in side_frames):
        raise ValueError("side_frames 只能包含側視影格。")
    if any(frame.camera_id != "rotating" for frame in rotating_frames):
        raise ValueError("rotating_frames 只能包含環繞影格。")
    top_capture_ids = [frame.capture_id for frame in top_frames]
    side_capture_ids = [frame.capture_id for frame in side_frames]
    rotating_capture_ids = [frame.capture_id for frame in rotating_frames]
    if len(set(top_capture_ids)) != len(top_capture_ids):
        raise ValueError("俯視影格包含重複的捕捉資料 ID。")
    if len(set(side_capture_ids)) != len(side_capture_ids):
        raise ValueError("側視影格包含重複的捕捉資料 ID。")
    if len(set(rotating_capture_ids)) != len(rotating_capture_ids):
        raise ValueError("環繞影格包含重複的捕捉資料 ID。")

    top_ordered = sorted(top_frames, key=_sort_key)
    side_ordered = sorted(side_frames, key=_sort_key)
    matched: list[tuple[CaptureFrame | None, CaptureFrame | None, str]] = []
    used_top: set[int] = set()
    used_side: set[int] = set()

    if manual_frame_offset:
        for top_index, top in enumerate(top_ordered):
            side_index = top_index + manual_frame_offset
            if 0 <= side_index < len(side_ordered):
                matched.append((top, side_ordered[side_index], "manually_aligned"))
                used_top.add(top_index)
                used_side.add(side_index)
    else:
        def add_optimal_matches(
            top_indices: Sequence[int],
            side_indices: Sequence[int],
        ) -> None:
            for top_index, side_index in _optimal_timestamp_matches(
                top_indices,
                side_indices,
                top_ordered,
                side_ordered,
            ):
                top = top_ordered[top_index]
                side = side_ordered[side_index]
                delta_ms = _timestamp_delta_ms(top, side)
                status = (
                    "paired"
                    if delta_ms <= timestamp_tolerance_ms
                    else "outside_tolerance"
                )
                matched.append((top, side, status))
                used_top.add(top_index)
                used_side.add(side_index)

        composite_keys = sorted(
            {
                (frame.capture_group, frame.cycle_id)
                for frame in top_ordered
                if frame.capture_group and frame.cycle_id is not None
            }
            & {
                (frame.capture_group, frame.cycle_id)
                for frame in side_ordered
                if frame.capture_group and frame.cycle_id is not None
            }
        )
        for capture_group, cycle_id in composite_keys:
            add_optimal_matches(
                [
                    index
                    for index, frame in enumerate(top_ordered)
                    if index not in used_top
                    and frame.capture_group == capture_group
                    and frame.cycle_id == cycle_id
                ],
                [
                    index
                    for index, frame in enumerate(side_ordered)
                    if index not in used_side
                    and frame.capture_group == capture_group
                    and frame.cycle_id == cycle_id
                ],
            )

        cycle_ids = sorted(
            {
                frame.cycle_id
                for frame in top_ordered
                if frame.cycle_id is not None
            }
            & {
                frame.cycle_id
                for frame in side_ordered
                if frame.cycle_id is not None
            }
        )
        for cycle_id in cycle_ids:
            add_optimal_matches(
                [
                    index
                    for index, frame in enumerate(top_ordered)
                    if index not in used_top and frame.cycle_id == cycle_id
                ],
                [
                    index
                    for index, frame in enumerate(side_ordered)
                    if index not in used_side and frame.cycle_id == cycle_id
                ],
            )

        capture_groups = sorted(
            {
                frame.capture_group
                for frame in top_ordered
                if frame.capture_group
            }
            & {
                frame.capture_group
                for frame in side_ordered
                if frame.capture_group
            }
        )
        for capture_group in capture_groups:
            add_optimal_matches(
                [
                    index
                    for index, frame in enumerate(top_ordered)
                    if index not in used_top and frame.capture_group == capture_group
                ],
                [
                    index
                    for index, frame in enumerate(side_ordered)
                    if index not in used_side and frame.capture_group == capture_group
                ],
            )

        remaining_top = [
            index for index in range(len(top_ordered)) if index not in used_top
        ]
        remaining_side = [
            index for index in range(len(side_ordered)) if index not in used_side
        ]
        add_optimal_matches(remaining_top, remaining_side)

    for top_index, top in enumerate(top_ordered):
        if top_index not in used_top:
            matched.append((top, None, "side_missing"))
    for side_index, side in enumerate(side_ordered):
        if side_index not in used_side:
            matched.append((None, side, "top_missing"))

    def pair_sort_key(
        item: tuple[CaptureFrame | None, CaptureFrame | None, str],
    ) -> tuple[object, int, int]:
        top, side, _ = item
        timestamps = [
            frame.timestamp_value
            for frame in (top, side)
            if frame is not None
        ]
        source_indices = [
            frame.source_index
            for frame in (top, side)
            if frame is not None
        ]
        capture_ids = [
            frame.capture_id
            for frame in (top, side)
            if frame is not None
        ]
        return min(timestamps), min(source_indices), min(capture_ids)

    if manual_frame_offset:
        top_positions = {id(frame): index for index, frame in enumerate(top_ordered)}
        side_positions = {id(frame): index for index, frame in enumerate(side_ordered)}

        def offset_sort_key(
            item: tuple[CaptureFrame | None, CaptureFrame | None, str],
        ) -> tuple[int, int]:
            top, side, _ = item
            if top is not None:
                return top_positions[id(top)], 0
            assert side is not None
            return side_positions[id(side)] - manual_frame_offset, 1

        matched.sort(key=offset_sort_key)
    else:
        matched.sort(key=pair_sort_key)
    results: list[AnalysisFramePair] = []
    for frame_id, (top, side, status) in enumerate(matched, start=1):
        delta_ms = (
            round(_timestamp_delta_ms(top, side), 6)
            if top is not None and side is not None
            else None
        )
        results.append(
            AnalysisFramePair(
                pair_id=f"pair_{frame_id:06d}",
                frame_id=frame_id,
                cycle_id=_pair_cycle_id(top, side),
                top_capture_id=top.capture_id if top else None,
                side_capture_id=side.capture_id if side else None,
                top_timestamp=top.timestamp if top else None,
                side_timestamp=side.timestamp if side else None,
                timestamp_delta_ms=delta_ms,
                frame_offset=manual_frame_offset,
                pair_status=status,
            )
        )
    if not rotating_frames:
        return results

    rotating_ordered = sorted(rotating_frames, key=_sort_key)
    used_rotating: set[int] = set()
    enriched: list[AnalysisFramePair] = []
    frame_by_id = {
        frame.capture_id: frame
        for frame in (*top_ordered, *side_ordered)
    }
    for pair in results:
        anchor = frame_by_id.get(pair.top_frame_id or -1) or frame_by_id.get(
            pair.side_frame_id or -1
        )
        if anchor is None:
            enriched.append(pair)
            continue

        available = [
            (index, frame)
            for index, frame in enumerate(rotating_ordered)
            if index not in used_rotating
        ]
        matching_levels = (
            [
                item
                for item in available
                if anchor.capture_group
                and item[1].capture_group == anchor.capture_group
                and anchor.cycle_id is not None
                and item[1].cycle_id == anchor.cycle_id
            ],
            [
                item
                for item in available
                if anchor.cycle_id is not None
                and item[1].cycle_id == anchor.cycle_id
            ],
            [
                item
                for item in available
                if anchor.capture_group
                and item[1].capture_group == anchor.capture_group
            ],
            available,
        )
        candidates = next((items for items in matching_levels if items), [])
        if not candidates:
            enriched.append(pair)
            continue
        rotating_index, rotating = min(
            candidates,
            key=lambda item: abs(
                (item[1].timestamp_value - anchor.timestamp_value).total_seconds()
            ),
        )
        delta_ms = abs(
            (rotating.timestamp_value - anchor.timestamp_value).total_seconds()
        ) * 1000.0
        if delta_ms > timestamp_tolerance_ms:
            enriched.append(pair)
            continue
        used_rotating.add(rotating_index)
        enriched.append(
            pair.model_copy(
                update={
                    "rotating_frame_id": rotating.capture_id,
                    "rotating_timestamp": rotating.timestamp,
                    "rotating_angle_deg": rotating.angle_deg,
                    "rotating_timestamp_delta_ms": round(delta_ms, 6),
                }
            )
        )
    return enriched
