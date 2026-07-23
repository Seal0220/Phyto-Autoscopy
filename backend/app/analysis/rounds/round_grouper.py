from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Mapping, Sequence

from app.analysis.record_validator import CaptureFrame, parse_capture_timestamp
from app.models.analysis_models import (
    AnalysisRound,
    AnalysisRoundReadiness,
    AnalysisView,
)


@dataclass(frozen=True, slots=True)
class RoundGroupingResult:
    rounds: tuple[AnalysisRound, ...]
    views: tuple[AnalysisView, ...]
    readiness: tuple[AnalysisRoundReadiness, ...]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ready_round_count(self) -> int:
        return sum(
            item.status in {"ready", "ready_tip_only"}
            for item in self.readiness
        )

    @property
    def incomplete_round_count(self) -> int:
        return len(self.readiness) - self.ready_round_count


def _capture_location(
    relative_path: str,
) -> tuple[str, str, str | None] | None:
    parts = PurePosixPath(relative_path).parts
    try:
        modes_index = parts.index("modes")
        rounds_index = parts.index("rounds", modes_index + 2)
    except ValueError:
        return None
    if modes_index + 1 >= len(parts) or rounds_index + 1 >= len(parts):
        return None

    mode_folder = parts[modes_index + 1]
    round_id = parts[rounds_index + 1]
    snapshot_id = next(
        (
            part.split("_", 1)[0]
            for part in parts[rounds_index + 2 :]
            if part.startswith("snapshot.")
        ),
        None,
    )
    if not mode_folder or not round_id.startswith("round."):
        return None
    return mode_folder, round_id, snapshot_id


def _angular_coverage(frames: Sequence[CaptureFrame]) -> float | None:
    angles = sorted({
        float(frame.angle_deg) % 360
        for frame in frames
        if frame.camera_id == "rotating" and frame.angle_deg is not None
    })
    if not angles:
        return None
    if len(angles) == 1:
        return 0.0

    gaps = [
        right - left
        for left, right in zip(angles, angles[1:])
    ]
    gaps.append(angles[0] + 360 - angles[-1])
    return round(360 - max(gaps), 6)


def _round_times(
    frames: Sequence[CaptureFrame],
) -> tuple[str | None, str | None, float | None]:
    parsed: list[tuple[datetime, str]] = []
    for frame in frames:
        try:
            parsed.append((parse_capture_timestamp(frame.timestamp), frame.timestamp))
        except ValueError:
            continue
    if not parsed:
        return None, None, None
    parsed.sort(key=lambda item: item[0])
    duration = max(0.0, (parsed[-1][0] - parsed[0][0]).total_seconds())
    return parsed[0][1], parsed[-1][1], duration


def group_analysis_rounds(
    *,
    analysis_id: str,
    record_id: str,
    frames: Sequence[CaptureFrame],
    mode_ids_by_folder: Mapping[str, str],
    method: str,
    enabled_camera_ids: Sequence[str],
    image_hashes: Mapping[int, str] | None = None,
) -> RoundGroupingResult:
    """Group immutable capture inputs by Record, Mode and Round.

    The directory hierarchy is authoritative. Timestamps are quality metadata,
    not a substitute for formal Round membership.
    """

    hashes = image_hashes or {}
    grouped: dict[tuple[str, str], list[tuple[CaptureFrame, str | None]]] = (
        defaultdict(list)
    )
    errors: list[str] = []
    warnings: list[str] = []

    for frame in frames:
        location = _capture_location(frame.relative_path)
        if location is None:
            errors.append(
                f"影像不在正式 Mode／Round／Snapshot 目錄中：{frame.relative_path}"
            )
            continue
        mode_folder, round_id, snapshot_id = location
        mode_id = mode_ids_by_folder.get(mode_folder)
        if mode_id is None:
            errors.append(f"影像所屬擷取模式不存在：{mode_folder}")
            continue
        grouped[(mode_id, round_id)].append((frame, snapshot_id))

    rounds: list[AnalysisRound] = []
    views: list[AnalysisView] = []
    readiness: list[AnalysisRoundReadiness] = []
    required_cameras = {"top", "side"}
    if method == "round_multiview":
        required_cameras.add("rotating")
    required_cameras.intersection_update(enabled_camera_ids)

    for (mode_id, round_id), entries in sorted(grouped.items()):
        round_frames = [entry[0] for entry in entries]
        round_key = f"{record_id}:{mode_id}:{round_id}"
        counts = {
            camera_id: sum(frame.camera_id == camera_id for frame in round_frames)
            for camera_id in ("top", "side", "rotating")
        }
        round_errors = [
            f"缺少{label}影像。"
            for camera_id, label in (
                ("top", "俯視"),
                ("side", "側視"),
                ("rotating", "旋臂"),
            )
            if camera_id in required_cameras and counts[camera_id] == 0
        ]
        round_warnings: list[str] = []
        status = "ready" if not round_errors else "incomplete"
        if method == "round_multiview" and round_id == "round.00":
            if not round_errors:
                status = "ready_tip_only"
            round_warnings.append(
                "連續模式 round.00 不建立完整環繞模型，只執行尖端標記分析。"
            )

        rotating_angles = [
            float(frame.angle_deg)
            for frame in round_frames
            if frame.camera_id == "rotating" and frame.angle_deg is not None
        ]
        if len(rotating_angles) != len({round(value, 6) for value in rotating_angles}):
            round_warnings.append("此輪包含重複旋臂角度，模型建立前會選擇品質較佳影像。")
        coverage = _angular_coverage(round_frames)
        started_at, ended_at, duration_seconds = _round_times(round_frames)

        readiness_item = AnalysisRoundReadiness(
            round_key=round_key,
            mode_id=mode_id,
            round_id=round_id,
            status=status,
            view_count=len(round_frames),
            top_view_count=counts["top"],
            side_view_count=counts["side"],
            rotating_view_count=counts["rotating"],
            angular_coverage_deg=coverage,
            duration_seconds=duration_seconds,
            errors=round_errors,
            warnings=round_warnings,
        )
        readiness.append(readiness_item)
        warnings.extend(
            f"{mode_id} / {round_id}：{message}"
            for message in round_warnings
        )
        rounds.append(
            AnalysisRound(
                analysis_id=analysis_id,
                round_key=round_key,
                record_id=record_id,
                mode_id=mode_id,
                round_id=round_id,
                started_at=started_at,
                ended_at=ended_at,
                duration_seconds=duration_seconds,
                status=status,
                view_count=len(round_frames),
                top_view_count=counts["top"],
                side_view_count=counts["side"],
                rotating_view_count=counts["rotating"],
                angular_coverage_deg=coverage,
                failure_reason="；".join(round_errors) or None,
            )
        )

        for frame, snapshot_id in entries:
            width, height = frame.resolution or (0, 0)
            view_id = (
                f"{mode_id}:{round_id}:{snapshot_id or 'snapshot.unknown'}:"
                f"{frame.camera_id}:{frame.capture_id}"
            )
            views.append(
                AnalysisView(
                    analysis_id=analysis_id,
                    round_key=round_key,
                    view_id=view_id,
                    capture_id=frame.capture_id,
                    camera_id=frame.camera_id,
                    snapshot_id=snapshot_id,
                    timestamp=frame.timestamp,
                    relative_path=frame.relative_path,
                    absolute_path=str(frame.file_path),
                    angle_deg=frame.angle_deg,
                    motor_position_deg=frame.motor_position_deg,
                    image_width=width,
                    image_height=height,
                    image_sha256=hashes.get(frame.capture_id, ""),
                )
            )

    if not grouped:
        errors.append("選取的擷取模式中找不到任何正式 Round。")
    if not any(item.status in {"ready", "ready_tip_only"} for item in readiness):
        errors.append("選取的擷取模式中沒有可分析的 Round。")

    return RoundGroupingResult(
        rounds=tuple(rounds),
        views=tuple(views),
        readiness=tuple(readiness),
        errors=tuple(dict.fromkeys(errors)),
        warnings=tuple(dict.fromkeys(warnings)),
    )
