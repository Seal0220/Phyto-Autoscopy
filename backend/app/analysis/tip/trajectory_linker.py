from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Sequence

import numpy as np

from app.models.analysis_models import (
    AnalysisRound,
    TipLandmark,
    TipTrajectoryPoint,
)


_ROUND_NUMBER = re.compile(r"(\d+)")


@dataclass(frozen=True, slots=True)
class TipTrajectoryResult:
    points: tuple[TipTrajectoryPoint, ...]
    quality: dict[str, Any]


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _round_number(value: str) -> int:
    match = _ROUND_NUMBER.search(value)
    return int(match.group(1)) if match else 0


def _round_order(item: AnalysisRound) -> tuple[float, int, str]:
    timestamp = _parse_timestamp(item.started_at)
    return (
        timestamp.timestamp() if timestamp is not None else float("inf"),
        _round_number(item.round_id),
        item.round_id,
    )


def _position(landmark: TipLandmark | None) -> np.ndarray | None:
    if landmark is None or not landmark.valid:
        return None
    values = (landmark.x_mm, landmark.y_mm, landmark.z_mm)
    if any(value is None for value in values):
        return None
    point = np.asarray(values, dtype=np.float64)
    return point if np.all(np.isfinite(point)) else None


def _detection_type(landmark: TipLandmark | None) -> str:
    if landmark is None or not landmark.valid:
        return "invalid"
    if landmark.manually_corrected or landmark.source == "manual":
        return "manual"
    if landmark.detection_type in {
        "measured",
        "estimated",
        "interpolated",
        "manual",
    }:
        return landmark.detection_type
    if landmark.source in {"model_skeleton", "temporal_estimate"}:
        return "estimated"
    return "measured"


def _seconds_between(
    current: str | None,
    previous: str | None,
) -> float | None:
    current_time = _parse_timestamp(current)
    previous_time = _parse_timestamp(previous)
    if current_time is None or previous_time is None:
        return None
    try:
        seconds = (current_time - previous_time).total_seconds()
    except TypeError:
        return None
    return seconds if seconds > 0 else None


def _nutation_metrics(
    positions: Sequence[np.ndarray],
    timestamps: Sequence[str | None],
) -> dict[str, float | str | None]:
    if len(positions) < 2:
        return {
            "rotation_direction": None,
            "nutation_radius_mm": None,
            "nutation_period_seconds": None,
        }
    xy = np.asarray([item[:2] for item in positions], dtype=np.float64)
    center = xy.mean(axis=0)
    radial = np.linalg.norm(xy - center, axis=1)
    radius = float(np.max(radial))
    signed_area = float(np.sum(
        xy[:-1, 0] * xy[1:, 1]
        - xy[:-1, 1] * xy[1:, 0]
    ))
    direction = (
        "counterclockwise"
        if signed_area > 1e-6
        else "clockwise"
        if signed_area < -1e-6
        else "stationary"
    )
    period = None
    if len(positions) >= 4 and timestamps and timestamps[0]:
        elapsed_values = [
            _seconds_between(item, timestamps[0])
            if index > 0
            else 0.0
            for index, item in enumerate(timestamps)
        ]
        elapsed = np.asarray(
            elapsed_values,
            dtype=np.float64,
        ) if all(item is not None for item in elapsed_values) else None
    else:
        elapsed = None
    if elapsed is not None:
        intervals = np.diff(elapsed)
        if np.all(intervals > 0):
            signal = (xy[:, 0] - center[0]) + (xy[:, 1] - center[1])
            signal = signal - signal.mean()
            energy = float(np.dot(signal, signal))
            if energy > 1e-9:
                correlation = np.correlate(signal, signal, mode="full")
                correlation = correlation[len(signal) - 1:] / energy
                if len(correlation) > 2:
                    lag = int(np.argmax(correlation[2:]) + 2)
                    if correlation[lag] > 0.2:
                        period = float(np.median(intervals) * lag)
    return {
        "rotation_direction": direction,
        "nutation_radius_mm": radius,
        "nutation_period_seconds": period,
    }


def link_tip_trajectory(
    rounds: Sequence[AnalysisRound],
    landmarks: Sequence[TipLandmark],
) -> TipTrajectoryResult:
    """Link formal tip markers without crossing modes or filling gaps."""

    landmark_by_round = {
        item.round_key: item
        for item in landmarks
    }
    rounds_by_mode: dict[str, list[AnalysisRound]] = {}
    for item in rounds:
        rounds_by_mode.setdefault(item.mode_id, []).append(item)

    points: list[TipTrajectoryPoint] = []
    mode_quality: dict[str, dict[str, Any]] = {}
    for mode_id, mode_rounds in sorted(rounds_by_mode.items()):
        ordered = sorted(mode_rounds, key=_round_order)
        first_valid_position: np.ndarray | None = None
        first_timestamp: str | None = None
        previous_position: np.ndarray | None = None
        previous_timestamp: str | None = None
        previous_speed: float | None = None
        previous_direction: np.ndarray | None = None
        previous_was_valid = False
        path_length = 0.0
        valid_count = 0
        valid_positions: list[np.ndarray] = []
        valid_timestamps: list[str | None] = []
        speeds: list[float] = []
        accelerations: list[float] = []
        curvatures: list[float] = []

        for point_index, round_item in enumerate(ordered):
            landmark = landmark_by_round.get(round_item.round_key)
            position = _position(landmark)
            valid = position is not None
            timestamp = (
                landmark.timestamp
                if landmark is not None and landmark.timestamp
                else round_item.started_at
            )
            elapsed = (
                _seconds_between(timestamp, first_timestamp)
                if first_timestamp is not None
                else 0.0 if timestamp else None
            )
            adjacent_distance = None
            speed = None
            acceleration = None
            direction = None
            curvature = None
            missing_segment = not valid

            if valid and first_valid_position is None:
                first_valid_position = position.copy()
                first_timestamp = timestamp
                elapsed = 0.0 if timestamp else None

            if valid and previous_was_valid and previous_position is not None:
                delta = position - previous_position
                adjacent_distance = float(np.linalg.norm(delta))
                delta_seconds = _seconds_between(timestamp, previous_timestamp)
                if adjacent_distance > 0:
                    direction = delta / adjacent_distance
                if delta_seconds is not None:
                    speed = adjacent_distance / delta_seconds
                    if previous_speed is not None:
                        acceleration = (speed - previous_speed) / delta_seconds
                if direction is not None and previous_direction is not None:
                    cosine = float(np.clip(
                        np.dot(previous_direction, direction),
                        -1.0,
                        1.0,
                    ))
                    mean_distance = max(adjacent_distance, 1e-9)
                    curvature = float(np.arccos(cosine) / mean_distance)
                path_length += adjacent_distance
            elif valid and point_index > 0:
                missing_segment = True

            displacement = (
                position - first_valid_position
                if valid and first_valid_position is not None
                else None
            )
            points.append(TipTrajectoryPoint(
                analysis_id=round_item.analysis_id,
                record_id=round_item.record_id,
                mode_id=mode_id,
                round_key=round_item.round_key,
                round_id=round_item.round_id,
                point_index=point_index,
                timestamp=timestamp,
                x_mm=float(position[0]) if valid else None,
                y_mm=float(position[1]) if valid else None,
                z_mm=float(position[2]) if valid else None,
                confidence=landmark.confidence if landmark is not None else 0.0,
                valid=valid,
                detection_type=_detection_type(landmark),
                visible_view_count=(
                    landmark.visible_view_count if landmark is not None else 0
                ),
                mean_reprojection_error_px=(
                    landmark.mean_reprojection_error_px
                    if landmark is not None
                    else None
                ),
                manually_corrected=(
                    landmark.manually_corrected
                    if landmark is not None
                    else False
                ),
                elapsed_seconds=elapsed,
                adjacent_distance_mm=adjacent_distance,
                speed_mm_per_second=speed,
                acceleration_mm_per_second2=acceleration,
                direction_x=float(direction[0]) if direction is not None else None,
                direction_y=float(direction[1]) if direction is not None else None,
                direction_z=float(direction[2]) if direction is not None else None,
                horizontal_displacement_mm=(
                    float(np.linalg.norm(displacement[:2]))
                    if displacement is not None
                    else None
                ),
                vertical_displacement_mm=(
                    float(displacement[2])
                    if displacement is not None
                    else None
                ),
                path_length_mm=path_length if valid else None,
                curvature_per_mm=curvature,
                missing_segment=missing_segment,
            ))
            if valid:
                valid_count += 1
                valid_positions.append(position.copy())
                valid_timestamps.append(timestamp)
                if speed is not None:
                    speeds.append(speed)
                if acceleration is not None:
                    accelerations.append(acceleration)
                if curvature is not None:
                    curvatures.append(curvature)
                previous_position = position
                previous_timestamp = timestamp
                previous_speed = speed
                previous_direction = direction
            else:
                previous_position = None
                previous_timestamp = None
                previous_speed = None
                previous_direction = None
            previous_was_valid = valid

        total_count = len(ordered)
        net_displacement = (
            float(np.linalg.norm(valid_positions[-1] - valid_positions[0]))
            if len(valid_positions) >= 2
            else 0.0 if valid_positions else None
        )
        final_displacement = (
            valid_positions[-1] - valid_positions[0]
            if len(valid_positions) >= 2
            else np.zeros(3, dtype=np.float64)
            if valid_positions
            else None
        )
        mode_points = [
            item
            for item in points
            if item.mode_id == mode_id
        ]
        missing_segment_count = sum(
            not item.valid
            and (
                index == 0
                or mode_points[index - 1].valid
            )
            for index, item in enumerate(mode_points)
        )
        mode_quality[mode_id] = {
            "point_count": total_count,
            "valid_point_count": valid_count,
            "missing_point_count": total_count - valid_count,
            "valid_measurement_ratio": (
                valid_count / total_count if total_count else 0.0
            ),
            "path_length_mm": path_length,
            "net_displacement_mm": net_displacement,
            "horizontal_displacement_mm": (
                float(np.linalg.norm(final_displacement[:2]))
                if final_displacement is not None
                else None
            ),
            "vertical_growth_mm": (
                float(final_displacement[2])
                if final_displacement is not None
                else None
            ),
            "mean_speed_mm_per_second": (
                float(np.mean(speeds)) if speeds else None
            ),
            "maximum_speed_mm_per_second": (
                float(np.max(speeds)) if speeds else None
            ),
            "mean_acceleration_mm_per_second2": (
                float(np.mean(accelerations)) if accelerations else None
            ),
            "mean_curvature_per_mm": (
                float(np.mean(curvatures)) if curvatures else None
            ),
            "missing_segment_count": missing_segment_count,
            "support_approach_distance_mm": None,
            **_nutation_metrics(valid_positions, valid_timestamps),
        }

    total = len(points)
    valid_total = sum(item.valid for item in points)
    return TipTrajectoryResult(
        points=tuple(points),
        quality={
            "mode_count": len(mode_quality),
            "point_count": total,
            "valid_point_count": valid_total,
            "missing_point_count": total - valid_total,
            "valid_measurement_ratio": valid_total / total if total else 0.0,
            "interpolation_applied": False,
            "modes": mode_quality,
        },
    )


__all__ = ["TipTrajectoryResult", "link_tip_trajectory"]
