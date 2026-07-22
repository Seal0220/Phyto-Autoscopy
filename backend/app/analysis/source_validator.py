from __future__ import annotations

import os
import csv
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path

from app.analysis.record_validator import (
    CANONICAL_CAMERA_IDS,
    CaptureFrame,
    CaptureRecordValidation,
    CaptureRecordValidator,
    RecordValidationIssue,
    extract_capture_group,
)


_IMAGE_EXTENSIONS = frozenset({".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff"})
_ANGLE_PATTERN = re.compile(r"(?:^|[_-])angle[_-](-?\d+(?:\.\d+)?)", re.IGNORECASE)
_CYCLE_PATTERN = re.compile(r"(?:^|[/\\_-])cycle[_-]?(\d+)", re.IGNORECASE)


def _inside_allowed_root(path: Path, allowed_roots: Sequence[Path]) -> bool:
    return any(path == root or root in path.parents for root in allowed_roots)


def _angle_from_path(path: Path) -> float | None:
    match = _ANGLE_PATTERN.search(path.as_posix())
    return float(match.group(1)) if match else None


def _cycle_from_path(path: Path) -> int | None:
    match = _CYCLE_PATTERN.search(path.as_posix())
    return int(match.group(1)) if match else None


def _source_metadata(directory: Path) -> dict[Path, dict[str, str]]:
    index: dict[Path, dict[str, str]] = {}
    candidates = []
    current = directory
    for _ in range(6):
        candidates.extend((current / "metadata.csv", current / "angles.csv"))
        if current.parent == current:
            break
        current = current.parent
    for csv_path in dict.fromkeys(candidates):
        if not csv_path.is_file():
            continue
        try:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    path_text = next((
                        str(row.get(key) or "").strip()
                        for key in ("file_path", "image_path", "path", "filename")
                        if str(row.get(key) or "").strip()
                    ), "")
                    if not path_text:
                        continue
                    source_path = Path(path_text)
                    resolved = (
                        source_path.resolve()
                        if source_path.is_absolute()
                        else (csv_path.parent / source_path).resolve()
                    )
                    index[resolved] = {
                        key: str(value or "").strip()
                        for key, value in row.items()
                    }
        except (OSError, UnicodeError, csv.Error):
            continue
    return index


def _scan_directory(
    camera_id: str,
    directory: Path,
    *,
    image_probe,
    first_input_id: int,
    selected_mode_folders: frozenset[str],
) -> tuple[list[CaptureFrame], list[RecordValidationIssue]]:
    frames: list[CaptureFrame] = []
    issues: list[RecordValidationIssue] = []
    metadata = _source_metadata(directory)
    candidates = sorted(
        path
        for path in directory.rglob("*")
        if path.is_file()
        and path.suffix.lower() in _IMAGE_EXTENSIONS
    )
    role_directories_present = any(
        camera_id in {
            part.lower()
            for part in path.relative_to(directory).parts[:-1]
        }
        for path in candidates
    )
    camera_filenames_present = any(
        path.stem.lower() in CANONICAL_CAMERA_IDS
        or any(
            path.stem.lower().startswith(f"{role}_")
            or path.stem.lower().startswith(f"{role}-")
            for role in CANONICAL_CAMERA_IDS
        )
        for path in candidates
    )
    paths = [
        path
        for path in candidates
        if (
            not selected_mode_folders
            or selected_mode_folders.intersection(path.parts)
        )
        and (
            (
                role_directories_present
                and camera_id in {
                    part.lower()
                    for part in path.relative_to(directory).parts[:-1]
                }
            )
            or (
                path.stem.lower() == camera_id
                or path.stem.lower().startswith(f"{camera_id}_")
                or path.stem.lower().startswith(f"{camera_id}-")
            )
            or (
                not role_directories_present
                and not camera_filenames_present
            )
        )
    ]
    for offset, path in enumerate(paths):
        input_id = first_input_id + offset
        try:
            resolution = image_probe(path)
        except Exception as error:
            resolution = None
            issues.append(
                RecordValidationIssue(
                    code="image_probe_failed",
                    message=f"影像檢查失敗：{path.name}（{error}）",
                    camera_id=camera_id,
                    capture_id=input_id,
                    file_path=str(path),
                )
            )
        if resolution is None:
            if not any(issue.capture_id == input_id for issue in issues):
                issues.append(
                    RecordValidationIssue(
                        code="undecodable_capture_file",
                        message=f"影像無法解碼：{path.name}",
                        camera_id=camera_id,
                        capture_id=input_id,
                        file_path=str(path),
                    )
                )
            continue
        metadata_row = metadata.get(path.resolve(), {})
        if not metadata_row:
            matching_names = [
                row
                for metadata_path, row in metadata.items()
                if metadata_path.name == path.name
            ]
            if len(matching_names) == 1:
                metadata_row = matching_names[0]
        angle_text = next((
            metadata_row.get(key, "")
            for key in ("angle_deg", "angle", "motor_position_deg")
            if metadata_row.get(key, "")
        ), "")
        try:
            angle_deg = float(angle_text) if angle_text else _angle_from_path(path)
        except ValueError:
            angle_deg = None
        if camera_id != "rotating":
            angle_deg = None
        if camera_id == "rotating" and angle_deg is None:
            issues.append(
                RecordValidationIssue(
                    code="missing_rotating_angle",
                    message=f"環繞影像缺少 angle_角度：{path.name}",
                    camera_id=camera_id,
                    capture_id=input_id,
                    file_path=str(path),
                )
            )
            continue
        modified = metadata_row.get("timestamp") or datetime.fromtimestamp(
            path.stat().st_mtime,
            tz=timezone.utc,
        ).isoformat()
        relative = path.relative_to(directory).as_posix()
        cycle_text = metadata_row.get("cycle_id", "")
        try:
            cycle_id = int(cycle_text) if cycle_text else _cycle_from_path(path)
        except ValueError:
            cycle_id = _cycle_from_path(path)
        frames.append(
            CaptureFrame(
                capture_id=input_id,
                camera_id=camera_id,
                timestamp=modified,
                file_path=path,
                relative_path=relative,
                cycle_id=cycle_id,
                angle_deg=angle_deg,
                motor_position_deg=angle_deg,
                capture_group=extract_capture_group(relative, camera_id),
                resolution=(int(resolution[0]), int(resolution[1])),
                source_index=input_id,
                original_camera_id=camera_id,
            )
        )
    if not frames:
        issues.append(
            RecordValidationIssue(
                code=f"missing_{camera_id}_frames",
                message=f"{camera_id} 目錄沒有可用影像。",
                camera_id=camera_id,
                file_path=str(directory),
            )
        )
    return frames, issues


def validate_analysis_sources(
    camera_sources: Mapping[str, object],
    *,
    method: str,
    allowed_roots: Sequence[Path],
    image_probe=None,
    selected_mode_folders: Sequence[str] = (),
) -> CaptureRecordValidation:
    """Normalize explicit camera directories into the Record validation shape."""

    required = (
        ("top", "side", "rotating")
        if method == "top_side_rotating"
        else ("top", "side")
    )
    roots = tuple(root.resolve() for root in allowed_roots)
    validator = CaptureRecordValidator(image_probe=image_probe)
    frames: list[CaptureFrame] = []
    issues: list[RecordValidationIssue] = []
    resolutions: dict[str, tuple[int, int]] = {}
    first_input_id = 1
    resolved_directories: list[Path] = []
    mode_folders = frozenset(
        str(folder).strip()
        for folder in selected_mode_folders
        if str(folder).strip()
    )

    for camera_id in required:
        source = camera_sources.get(camera_id)
        path_text = str(getattr(source, "path", "") or "").strip()
        directory = Path(path_text).expanduser().resolve() if path_text else None
        if directory is None or not directory.is_dir():
            issues.append(
                RecordValidationIssue(
                    code="missing_camera_directory",
                    message=f"找不到 {camera_id} 影像目錄。",
                    camera_id=camera_id,
                    file_path=path_text,
                )
            )
            continue
        if not _inside_allowed_root(directory, roots):
            issues.append(
                RecordValidationIssue(
                    code="unsafe_camera_directory",
                    message=f"{camera_id} 影像目錄超出允許的資料範圍。",
                    camera_id=camera_id,
                    file_path=str(directory),
                )
            )
            continue
        resolved_directories.append(directory)
        camera_frames, camera_issues = _scan_directory(
            camera_id,
            directory,
            image_probe=validator.image_probe,
            first_input_id=first_input_id,
            selected_mode_folders=mode_folders,
        )
        frames.extend(camera_frames)
        issues.extend(camera_issues)
        first_input_id = max(
            [first_input_id, *(frame.capture_id + 1 for frame in camera_frames)]
        )
        camera_resolutions = {
            frame.resolution
            for frame in camera_frames
            if frame.resolution is not None
        }
        if len(camera_resolutions) == 1:
            resolutions[camera_id] = next(iter(camera_resolutions))
        elif len(camera_resolutions) > 1:
            issues.append(
                RecordValidationIssue(
                    code="inconsistent_camera_resolution",
                    message=f"{camera_id} 影像包含不一致的解析度。",
                    camera_id=camera_id,
                )
            )

    from app.analysis.frame_pairing import pair_capture_frames

    top_frames = [frame for frame in frames if frame.camera_id == "top"]
    side_frames = [frame for frame in frames if frame.camera_id == "side"]
    rotating_frames = [frame for frame in frames if frame.camera_id == "rotating"]
    pairs = (
        pair_capture_frames(top_frames, side_frames, rotating_frames)
        if top_frames and side_frames
        else []
    )
    pairable_count = sum(
        pair.pair_status in {"paired", "manually_aligned"}
        for pair in pairs
    )
    rotating_pairable_count = sum(
        pair.pair_status in {"paired", "manually_aligned"}
        and pair.rotating_frame_id is not None
        for pair in pairs
    )
    if top_frames and side_frames and pairable_count == 0:
        issues.append(
            RecordValidationIssue(
                code="no_pairable_frames",
                message="俯視與側視影像沒有可用的同步配對。",
            )
        )
    if method == "top_side_rotating" and rotating_pairable_count == 0:
        issues.append(
            RecordValidationIssue(
                code="no_pairable_rotating_frames",
                message="環繞影像沒有可加入雙鏡頭影格群組的同步配對。",
            )
        )
    common_root = (
        Path(os.path.commonpath([str(path) for path in resolved_directories]))
        if resolved_directories
        else roots[0]
    )
    messages = tuple(dict.fromkeys(issue.message for issue in issues))
    return CaptureRecordValidation(
        record_id="",
        record_status="custom",
        record_path=common_root,
        ready=not messages,
        frames=tuple(frames),
        issues=tuple(issues),
        not_ready_reasons=messages,
        camera_resolutions=resolutions,
        metadata_path=None,
        record_metadata={},
        source_frame_count=len(frames),
        rejected_frame_count=sum(
            issue.capture_id is not None
            for issue in issues
        ),
        pairable_frame_count=pairable_count,
        total_frame_count=len(pairs),
        rotating_pairable_frame_count=rotating_pairable_count,
    )


__all__ = ["validate_analysis_sources"]
