from __future__ import annotations

import csv
import json
import math
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


CANONICAL_CAMERA_IDS = frozenset({"top", "side", "rotating"})
ACTIVE_RECORD_STATUSES = frozenset({"manual", "running", "paused", "stopping"})
SUCCESS_CAPTURE_STATUSES = frozenset({"success"})

_DRIVE_PATH_PATTERN = re.compile(r"^[A-Za-z]:[/\\]")
_CAPTURE_FILE_PATTERN = re.compile(
    r"^cycle_(?P<cycle>\d+)_capture_(?P<capture>\d+)(?:_angle_.+)?$",
    re.IGNORECASE,
)
_CAMERA_FILE_PREFIX_PATTERN = re.compile(
    r"^(?:top|side|rotating)[_-]",
    re.IGNORECASE,
)

ImageProbe = Callable[[Path], tuple[int, int] | None]


@dataclass(frozen=True, slots=True)
class CaptureFrame:
    capture_id: int
    camera_id: str
    timestamp: str
    file_path: Path
    relative_path: str
    cycle_id: int | None = None
    angle_deg: float | None = None
    motor_position_deg: float | None = None
    capture_group: str | None = None
    resolution: tuple[int, int] | None = None
    source_index: int = 0
    original_camera_id: str | None = None

    @property
    def timestamp_value(self) -> datetime:
        return parse_capture_timestamp(self.timestamp)


@dataclass(frozen=True, slots=True)
class RecordValidationIssue:
    code: str
    message: str
    camera_id: str | None = None
    capture_id: int | None = None
    file_path: str | None = None


@dataclass(frozen=True, slots=True)
class CaptureRecordValidation:
    record_id: str
    record_status: str
    record_path: Path
    ready: bool
    frames: tuple[CaptureFrame, ...]
    issues: tuple[RecordValidationIssue, ...]
    not_ready_reasons: tuple[str, ...]
    camera_resolutions: Mapping[str, tuple[int, int]]
    metadata_path: Path | None
    record_metadata: Mapping[str, Any]
    source_frame_count: int
    rejected_frame_count: int
    pairable_frame_count: int
    total_frame_count: int
    rotating_pairable_frame_count: int = 0

    @property
    def top_frames(self) -> tuple[CaptureFrame, ...]:
        return tuple(frame for frame in self.frames if frame.camera_id == "top")

    @property
    def side_frames(self) -> tuple[CaptureFrame, ...]:
        return tuple(frame for frame in self.frames if frame.camera_id == "side")

    @property
    def rotating_frames(self) -> tuple[CaptureFrame, ...]:
        return tuple(frame for frame in self.frames if frame.camera_id == "rotating")

    @property
    def top_frame_count(self) -> int:
        return len(self.top_frames)

    @property
    def side_frame_count(self) -> int:
        return len(self.side_frames)

    @property
    def rotating_frame_count(self) -> int:
        return len(self.rotating_frames)

    @property
    def camera_directories(self) -> dict[str, str]:
        directories: dict[str, str] = {}
        for camera_id in CANONICAL_CAMERA_IDS:
            camera_paths = [
                frame.file_path.parent
                for frame in self.frames
                if frame.camera_id == camera_id
            ]
            if not camera_paths:
                continue
            common = Path(camera_paths[0])
            while any(common not in path.parents and path != common for path in camera_paths):
                if common == self.record_path:
                    break
                common = common.parent
            directories[camera_id] = str(common)
        return directories


def parse_capture_timestamp(value: object) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("拍攝時間不可為空。")
    normalized = f"{text[:-1]}+00:00" if text.endswith(("Z", "z")) else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"拍攝時間格式無效：{text}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def extract_capture_group(file_path: str | Path, camera_id: object) -> str | None:
    """Return a stable group key without accepting absolute or traversal paths."""

    text = str(file_path).strip().replace("\\", "/")
    if not text or "\x00" in text or text.startswith("/") or _DRIVE_PATH_PATTERN.match(text):
        return None
    pure_path = PurePosixPath(text)
    if any(part in {"", ".", ".."} for part in pure_path.parts):
        return None

    camera_name = str(camera_id or "").strip().lower()
    if camera_name not in CANONICAL_CAMERA_IDS:
        return None
    parent_parts = [
        part
        for part in pure_path.parent.parts
        if part.lower() != camera_name
    ]
    stem = _CAMERA_FILE_PREFIX_PATTERN.sub("", pure_path.stem)
    capture_match = _CAPTURE_FILE_PATTERN.match(stem)
    if capture_match:
        stem = (
            f"cycle_{int(capture_match.group('cycle')):06d}/"
            f"capture_{int(capture_match.group('capture')):06d}"
        )
    group_parts = [*parent_parts, stem]
    return "/".join(part for part in group_parts if part) or None


def _default_image_probe(path: Path) -> tuple[int, int] | None:
    try:
        import cv2  # type: ignore
        import numpy as np

        encoded = np.fromfile(path, dtype=np.uint8)
        if encoded.size == 0:
            return None
        image = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
        if image is None or image.ndim < 2:
            return None
        height, width = image.shape[:2]
        if width <= 0 or height <= 0:
            return None
        return int(width), int(height)
    except (ImportError, OSError, ValueError):
        return None


def _get_value(source: object, name: str, default: object = None) -> object:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _parse_cycle_id(value: object) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        cycle_id = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"循環 ID 格式無效：{value}") from exc
    if cycle_id < 0:
        raise ValueError(f"循環 ID 不可小於 0：{value}")
    return cycle_id


def _parse_optional_float(value: object, label: str) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}格式無效：{value}") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{label}必須是有限數值。")
    return parsed


def _resolve_capture_path(record_path: Path, file_path: object) -> tuple[Path, str]:
    text = str(file_path or "").strip()
    if not text or "\x00" in text:
        raise ValueError("影像路徑不可為空。")
    candidate = Path(text)
    resolved = (
        candidate.resolve()
        if candidate.is_absolute()
        else (record_path / candidate).resolve()
    )
    try:
        relative = resolved.relative_to(record_path)
    except ValueError as exc:
        raise ValueError("影像路徑超出紀錄目錄。") from exc
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError("影像路徑包含不安全的路徑片段。")
    return resolved, relative.as_posix()


def _load_record_metadata(record_path: Path) -> tuple[dict[str, Any], Path | None, str | None]:
    metadata_path = next(
        (
            candidate
            for candidate in (record_path / "record.json", record_path / "session.json")
            if candidate.is_file()
        ),
        None,
    )
    if metadata_path is None:
        return {}, None, "找不到紀錄 Metadata（record.json 或 session.json）。"
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {}, metadata_path, f"紀錄 Metadata 無法讀取：{exc}"
    if not isinstance(payload, dict):
        return {}, metadata_path, "紀錄 Metadata 根節點必須是物件。"
    return payload, metadata_path, None


def _load_csv_captures(record_path: Path) -> tuple[list[dict[str, object]], str | None]:
    metadata_path = record_path / "metadata.csv"
    if not metadata_path.is_file():
        return [], "找不到影像索引 metadata.csv。"
    try:
        with metadata_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                return [], "metadata.csv 缺少欄位標題。"
            required = {"camera_id", "timestamp", "file_path", "status"}
            missing = required.difference(reader.fieldnames)
            if missing:
                return [], f"metadata.csv 缺少必要欄位：{', '.join(sorted(missing))}。"
            captures: list[dict[str, object]] = []
            for source_index, row in enumerate(reader, start=1):
                captures.append({**row, "id": source_index})
            return captures, None
    except (OSError, UnicodeError, csv.Error) as exc:
        return [], f"metadata.csv 無法讀取：{exc}"


def _deduplicate_messages(issues: Iterable[RecordValidationIssue]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(issue.message for issue in issues))


class CaptureRecordValidator:
    def __init__(self, image_probe: ImageProbe | None = None) -> None:
        self.image_probe = image_probe or _default_image_probe

    def validate(
        self,
        record: object,
        captures: Iterable[object] | None = None,
        *,
        timestamp_tolerance_ms: float = 1000.0,
        manual_frame_offset: int = 0,
        required_camera_ids: Iterable[str] = ("top", "side"),
    ) -> CaptureRecordValidation:
        required_cameras = frozenset(required_camera_ids)
        if not required_cameras or not required_cameras.issubset(CANONICAL_CAMERA_IDS):
            raise ValueError("必要相機只能使用 top、side、rotating。")
        record_id = str(
            _get_value(record, "record_id", _get_value(record, "session_id", ""))
        ).strip()
        record_status = str(_get_value(record, "status", "unknown")).strip().lower()
        raw_record_path = str(_get_value(record, "record_path", "")).strip()
        record_path = Path(raw_record_path).resolve()
        issues: list[RecordValidationIssue] = []

        if not record_id:
            issues.append(RecordValidationIssue("missing_record_id", "紀錄缺少 ID。"))
        if not raw_record_path:
            issues.append(
                RecordValidationIssue(
                    "missing_record_directory",
                    "紀錄缺少儲存目錄。",
                )
            )
        elif not record_path.is_dir():
            issues.append(
                RecordValidationIssue(
                    "missing_record_directory",
                    f"找不到紀錄目錄：{record_path}",
                )
            )
        if record_status in ACTIVE_RECORD_STATUSES:
            issues.append(
                RecordValidationIssue(
                    "record_active",
                    "紀錄仍在擷取中，結束後才能進行分析。",
                )
            )

        record_metadata, metadata_path, metadata_error = _load_record_metadata(record_path)
        if metadata_error:
            issues.append(RecordValidationIssue("invalid_record_metadata", metadata_error))
        metadata_record_id = str(
            record_metadata.get("record_id") or record_metadata.get("session_id") or ""
        ).strip()
        if metadata_record_id and record_id and metadata_record_id != record_id:
            issues.append(
                RecordValidationIssue(
                    "record_id_mismatch",
                    "紀錄 Metadata 的 ID 與資料庫紀錄不一致。",
                )
            )

        capture_sources: list[object]
        if captures is None:
            capture_sources, csv_error = _load_csv_captures(record_path)
            if csv_error:
                issues.append(RecordValidationIssue("invalid_capture_index", csv_error))
        else:
            capture_sources = list(captures)
            if not (record_path / "metadata.csv").is_file():
                issues.append(
                    RecordValidationIssue(
                        "missing_capture_metadata",
                        "找不到影像索引 metadata.csv。",
                    )
                )

        frames: list[CaptureFrame] = []
        source_frame_count = 0
        for source_index, capture in enumerate(capture_sources, start=1):
            camera_id = str(_get_value(capture, "camera_id", "")).strip().lower()
            if camera_id not in CANONICAL_CAMERA_IDS or camera_id not in required_cameras:
                continue
            original_camera_id = camera_id
            source_frame_count += 1
            raw_capture_id = _get_value(capture, "id", source_index)
            try:
                capture_id = int(raw_capture_id)
            except (TypeError, ValueError):
                capture_id = source_index
                issues.append(
                    RecordValidationIssue(
                        "invalid_capture_id",
                        f"第 {source_index} 筆影像的 ID 無效。",
                        camera_id=camera_id,
                    )
                )

            capture_status = str(_get_value(capture, "status", "")).strip().lower()
            raw_file_path = _get_value(capture, "file_path", "")
            if capture_status not in SUCCESS_CAPTURE_STATUSES:
                issues.append(
                    RecordValidationIssue(
                        "capture_failed",
                        f"影像 {capture_id} 的擷取狀態不是 success。",
                        camera_id=camera_id,
                        capture_id=capture_id,
                        file_path=str(raw_file_path),
                    )
                )
                continue

            try:
                file_path, relative_path = _resolve_capture_path(record_path, raw_file_path)
            except ValueError as exc:
                issues.append(
                    RecordValidationIssue(
                        "unsafe_capture_path",
                        f"影像 {capture_id} 的路徑無效：{exc}",
                        camera_id=camera_id,
                        capture_id=capture_id,
                        file_path=str(raw_file_path),
                    )
                )
                continue
            if not file_path.is_file():
                issues.append(
                    RecordValidationIssue(
                        "missing_capture_file",
                        f"找不到影像檔案：{relative_path}",
                        camera_id=camera_id,
                        capture_id=capture_id,
                        file_path=relative_path,
                    )
                )
                continue

            timestamp = str(_get_value(capture, "timestamp", "")).strip()
            try:
                parse_capture_timestamp(timestamp)
            except ValueError as exc:
                issues.append(
                    RecordValidationIssue(
                        "invalid_capture_timestamp",
                        f"影像 {capture_id} 的{exc}",
                        camera_id=camera_id,
                        capture_id=capture_id,
                        file_path=relative_path,
                    )
                )
                continue

            try:
                cycle_id = _parse_cycle_id(_get_value(capture, "cycle_id"))
            except ValueError as exc:
                issues.append(
                    RecordValidationIssue(
                        "invalid_cycle_id",
                        f"影像 {capture_id} 的{exc}",
                        camera_id=camera_id,
                        capture_id=capture_id,
                        file_path=relative_path,
                    )
                )
                continue

            try:
                angle_deg = _parse_optional_float(
                    _get_value(capture, "angle_deg"),
                    "拍攝角度",
                )
                motor_position_deg = _parse_optional_float(
                    _get_value(capture, "motor_position_deg"),
                    "馬達位置",
                )
            except ValueError as exc:
                issues.append(
                    RecordValidationIssue(
                        "invalid_capture_angle",
                        f"影像 {capture_id} 的{exc}",
                        camera_id=camera_id,
                        capture_id=capture_id,
                        file_path=relative_path,
                    )
                )
                continue
            if camera_id == "rotating" and angle_deg is None:
                issues.append(
                    RecordValidationIssue(
                        "missing_rotating_angle",
                        f"環繞影像 {capture_id} 缺少拍攝角度。",
                        camera_id=camera_id,
                        capture_id=capture_id,
                        file_path=relative_path,
                    )
                )
                continue

            try:
                resolution = self.image_probe(file_path)
            except Exception as exc:
                issues.append(
                    RecordValidationIssue(
                        "image_probe_failed",
                        f"影像檢查失敗：{relative_path}（{exc}）",
                        camera_id=camera_id,
                        capture_id=capture_id,
                        file_path=relative_path,
                    )
                )
                continue
            if resolution is None:
                issues.append(
                    RecordValidationIssue(
                        "undecodable_capture_file",
                        f"影像無法解碼：{relative_path}",
                        camera_id=camera_id,
                        capture_id=capture_id,
                        file_path=relative_path,
                    )
                )
                continue
            try:
                width, height = (int(value) for value in resolution)
            except (TypeError, ValueError):
                issues.append(
                    RecordValidationIssue(
                        "invalid_capture_resolution",
                        f"影像解析度無效：{relative_path}",
                        camera_id=camera_id,
                        capture_id=capture_id,
                        file_path=relative_path,
                    )
                )
                continue
            if width <= 0 or height <= 0:
                issues.append(
                    RecordValidationIssue(
                        "invalid_capture_resolution",
                        f"影像解析度無效：{relative_path}",
                        camera_id=camera_id,
                        capture_id=capture_id,
                        file_path=relative_path,
                    )
                )
                continue

            frames.append(
                CaptureFrame(
                    capture_id=capture_id,
                    camera_id=camera_id,
                    timestamp=timestamp,
                    file_path=file_path,
                    relative_path=relative_path,
                    cycle_id=cycle_id,
                    angle_deg=angle_deg,
                    motor_position_deg=motor_position_deg,
                    capture_group=extract_capture_group(relative_path, original_camera_id),
                    resolution=(width, height),
                    source_index=source_index,
                    original_camera_id=original_camera_id,
                )
            )

        camera_resolutions: dict[str, tuple[int, int]] = {}
        for camera_id in sorted(CANONICAL_CAMERA_IDS):
            resolutions = {
                frame.resolution
                for frame in frames
                if frame.camera_id == camera_id and frame.resolution is not None
            }
            if len(resolutions) == 1:
                camera_resolutions[camera_id] = next(iter(resolutions))
            elif len(resolutions) > 1:
                issues.append(
                    RecordValidationIssue(
                        "inconsistent_camera_resolution",
                        f"{camera_id} 影像包含不一致的解析度。",
                        camera_id=camera_id,
                    )
                )

        top_frames = [frame for frame in frames if frame.camera_id == "top"]
        side_frames = [frame for frame in frames if frame.camera_id == "side"]
        rotating_frames = [frame for frame in frames if frame.camera_id == "rotating"]
        if "top" in required_cameras and not top_frames:
            issues.append(RecordValidationIssue("missing_top_frames", "紀錄缺少俯視影像。"))
        if "side" in required_cameras and not side_frames:
            issues.append(RecordValidationIssue("missing_side_frames", "紀錄缺少側視影像。"))
        if "rotating" in required_cameras and not rotating_frames:
            issues.append(
                RecordValidationIssue("missing_rotating_frames", "紀錄缺少環繞影像。")
            )

        pairable_frame_count = 0
        rotating_pairable_frame_count = 0
        total_frame_count = 0
        if top_frames and side_frames:
            from app.analysis.frame_pairing import pair_capture_frames

            pairs = pair_capture_frames(
                top_frames,
                side_frames,
                rotating_frames,
                timestamp_tolerance_ms=timestamp_tolerance_ms,
                manual_frame_offset=manual_frame_offset,
            )
            pairable_frame_count = sum(
                pair.pair_status in {"paired", "manually_aligned"}
                for pair in pairs
            )
            total_frame_count = len(pairs)
            rotating_pairable_frame_count = sum(
                pair.pair_status in {"paired", "manually_aligned"}
                and pair.rotating_frame_id is not None
                for pair in pairs
            )
            if pairable_frame_count == 0:
                issues.append(
                    RecordValidationIssue(
                        "no_pairable_frames",
                        "俯視與側視影像沒有可用的同步配對。",
                    )
                )
            if (
                "rotating" in required_cameras
                and rotating_pairable_frame_count == 0
            ):
                issues.append(
                    RecordValidationIssue(
                        "no_pairable_rotating_frames",
                        "環繞影像沒有可加入雙鏡頭影格群組的同步配對。",
                    )
                )

        rejected_frame_count = source_frame_count - len(frames)
        not_ready_reasons = _deduplicate_messages(issues)
        return CaptureRecordValidation(
            record_id=record_id,
            record_status=record_status,
            record_path=record_path,
            ready=not not_ready_reasons,
            frames=tuple(frames),
            issues=tuple(issues),
            not_ready_reasons=not_ready_reasons,
            camera_resolutions=camera_resolutions,
            metadata_path=metadata_path,
            record_metadata=record_metadata,
            source_frame_count=source_frame_count,
            rejected_frame_count=rejected_frame_count,
            pairable_frame_count=pairable_frame_count,
            total_frame_count=total_frame_count,
            rotating_pairable_frame_count=rotating_pairable_frame_count,
        )


def validate_capture_record(
    record: object,
    captures: Iterable[object] | None = None,
    *,
    image_probe: ImageProbe | None = None,
    timestamp_tolerance_ms: float = 1000.0,
    manual_frame_offset: int = 0,
    required_camera_ids: Iterable[str] = ("top", "side"),
) -> CaptureRecordValidation:
    return CaptureRecordValidator(image_probe=image_probe).validate(
        record,
        captures,
        timestamp_tolerance_ms=timestamp_tolerance_ms,
        manual_frame_offset=manual_frame_offset,
        required_camera_ids=required_camera_ids,
    )
