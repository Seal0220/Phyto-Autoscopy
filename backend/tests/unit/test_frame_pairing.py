from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.analysis.frame_pairing import pair_capture_frames
from app.analysis.record_validator import (
    CaptureFrame,
    extract_capture_group,
    validate_capture_record,
)


def _frame(
    capture_id: int,
    camera_id: str,
    second: float,
    *,
    cycle_id: int | None = None,
    angle_deg: float | None = None,
    capture_group: str | None = None,
) -> CaptureFrame:
    whole_second = int(second)
    microsecond = int(round((second - whole_second) * 1_000_000))
    timestamp = f"2026-07-17T00:00:{whole_second:02d}.{microsecond:06d}+00:00"
    return CaptureFrame(
        capture_id=capture_id,
        camera_id=camera_id,
        timestamp=timestamp,
        file_path=Path(f"/{camera_id}/{capture_id}.jpg"),
        relative_path=f"{camera_id}/{capture_id}.jpg",
        cycle_id=cycle_id,
        angle_deg=angle_deg,
        capture_group=capture_group,
        resolution=(1280, 720),
        source_index=capture_id,
        original_camera_id=camera_id,
    )


def _record(tmp_path: Path, status: str = "completed") -> dict[str, str]:
    record_path = tmp_path / "session_test"
    record_path.mkdir()
    (record_path / "session.json").write_text(
        json.dumps(
            {
                "session_id": "session_test",
                "status": status,
            }
        ),
        encoding="utf-8",
    )
    (record_path / "metadata.csv").write_text(
        "camera_id,timestamp,file_path,status,cycle_id\n",
        encoding="utf-8",
    )
    return {
        "record_id": "session_test",
        "status": status,
        "record_path": str(record_path),
    }


def _capture(
    capture_id: int,
    camera_id: str,
    timestamp: str,
    file_path: str,
    *,
    cycle_id: int | None = None,
    status: str = "success",
    angle_deg: float | None = None,
) -> dict[str, object]:
    return {
        "id": capture_id,
        "record_id": "session_test",
        "cycle_id": cycle_id,
        "camera_id": camera_id,
        "timestamp": timestamp,
        "file_path": file_path,
        "status": status,
        "angle_deg": angle_deg,
    }


def test_capture_group_is_safe_and_camera_independent() -> None:
    top = "modes/01_seconds/top/cycle_000003_capture_000007_angle_030.00.jpg"
    side = "modes/01_seconds/side/cycle_000003_capture_000007_angle_030.00.jpg"

    assert extract_capture_group(top, "top") == (
        "modes/01_seconds/cycle_000003/capture_000007"
    )
    assert extract_capture_group(side, "side") == (
        "modes/01_seconds/cycle_000003/capture_000007"
    )
    assert extract_capture_group("../top/000001.jpg", "top") is None
    assert extract_capture_group("C:/captures/top/000001.jpg", "top") is None


def test_validator_reads_three_canonical_camera_roles(tmp_path) -> None:
    record = _record(tmp_path)
    record_path = Path(record["record_path"])
    original_metadata = (record_path / "session.json").read_bytes()
    top_path = record_path / "top" / "000001.jpg"
    side_path = record_path / "side" / "000001.jpg"
    rotating_path = record_path / "rotating" / "000001.jpg"
    top_path.parent.mkdir()
    side_path.parent.mkdir()
    rotating_path.parent.mkdir()
    top_path.write_bytes(b"top")
    side_path.write_bytes(b"side")
    rotating_path.write_bytes(b"rotating")
    captures = [
        _capture(
            1,
            "top",
            "2026-07-17T00:00:00+00:00",
            "top/000001.jpg",
        ),
        _capture(
            2,
            "side",
            "2026-07-17T00:00:00.010+00:00",
            "side/000001.jpg",
        ),
        _capture(
            3,
            "rotating",
            "2026-07-17T00:00:00.020+00:00",
            "rotating/000001.jpg",
            angle_deg=0.0,
        ),
    ]

    result = validate_capture_record(
        record,
        captures,
        image_probe=lambda _path: (1280, 720),
        required_camera_ids=("top", "side", "rotating"),
    )

    assert result.ready is True
    assert [frame.camera_id for frame in result.frames] == ["top", "side", "rotating"]
    assert result.side_frames[0].original_camera_id == "side"
    assert result.pairable_frame_count == 1
    assert (record_path / "session.json").read_bytes() == original_metadata
    assert not (record_path / "config.json").exists()


def test_validator_loads_capture_index_from_csv_read_only(tmp_path) -> None:
    record = _record(tmp_path)
    record_path = Path(record["record_path"])
    top_path = record_path / "top" / "000001.jpg"
    side_path = record_path / "side" / "000001.jpg"
    top_path.parent.mkdir()
    side_path.parent.mkdir()
    top_path.write_bytes(b"top")
    side_path.write_bytes(b"side")
    csv_text = (
        "camera_id,timestamp,file_path,status,cycle_id\n"
        "top,2026-07-17T00:00:00+00:00,top/000001.jpg,success,1\n"
        "side,2026-07-17T00:00:00.010+00:00,"
        "side/000001.jpg,success,1\n"
    )
    csv_path = record_path / "metadata.csv"
    csv_path.write_text(csv_text, encoding="utf-8")

    result = validate_capture_record(
        record,
        image_probe=lambda _path: (1280, 720),
    )

    assert result.ready is True
    assert result.top_frame_count == 1
    assert result.side_frame_count == 1
    assert result.pairable_frame_count == 1
    assert csv_path.read_text(encoding="utf-8") == csv_text


def test_validator_default_probe_reads_image_resolution(tmp_path) -> None:
    import cv2  # type: ignore
    import numpy as np

    record = _record(tmp_path)
    record_path = Path(record["record_path"])
    encoded_ok, encoded = cv2.imencode(
        ".jpg",
        np.zeros((9, 16, 3), dtype=np.uint8),
    )
    assert encoded_ok is True
    captures = []
    for capture_id, camera_id in ((1, "top"), (2, "side")):
        relative_path = f"{camera_id}/000001.jpg"
        path = record_path / relative_path
        path.parent.mkdir()
        path.write_bytes(encoded.tobytes())
        captures.append(
            _capture(
                capture_id,
                camera_id,
                "2026-07-17T00:00:00+00:00",
                relative_path,
            )
        )

    result = validate_capture_record(record, captures)

    assert result.ready is True
    assert result.camera_resolutions == {"side": (16, 9), "top": (16, 9)}


def test_validator_marks_active_record_not_ready(tmp_path) -> None:
    record = _record(tmp_path, status="running")
    record_path = Path(record["record_path"])
    for camera_id in ("top", "side"):
        path = record_path / camera_id / "000001.jpg"
        path.parent.mkdir()
        path.write_bytes(camera_id.encode())
    captures = [
        _capture(1, "top", "2026-07-17T00:00:00+00:00", "top/000001.jpg"),
        _capture(2, "side", "2026-07-17T00:00:00+00:00", "side/000001.jpg"),
    ]

    result = validate_capture_record(
        record,
        captures,
        image_probe=lambda _path: (1280, 720),
    )

    assert result.ready is False
    assert "record_active" in {issue.code for issue in result.issues}


def test_validator_reports_files_timestamps_and_resolutions(tmp_path) -> None:
    record = _record(tmp_path)
    record_path = Path(record["record_path"])
    files = {
        "top/valid.jpg": b"valid",
        "top/unreadable.jpg": b"broken",
        "side/one.jpg": b"one",
        "side/two.jpg": b"two",
    }
    for relative_path, content in files.items():
        path = record_path / relative_path
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(content)
    captures = [
        _capture(1, "top", "2026-07-17T00:00:00+00:00", "top/valid.jpg"),
        _capture(2, "top", "invalid", "top/valid.jpg"),
        _capture(3, "top", "2026-07-17T00:00:01+00:00", "top/missing.jpg"),
        _capture(4, "top", "2026-07-17T00:00:02+00:00", "top/unreadable.jpg"),
        _capture(5, "side", "2026-07-17T00:00:00+00:00", "side/one.jpg"),
        _capture(6, "side", "2026-07-17T00:00:01+00:00", "side/two.jpg"),
        _capture(7, "side", "2026-07-17T00:00:02+00:00", "../outside.jpg"),
    ]

    def probe(path: Path) -> tuple[int, int] | None:
        if path.name == "unreadable.jpg":
            return None
        if path.name == "two.jpg":
            return 640, 480
        return 1280, 720

    result = validate_capture_record(record, captures, image_probe=probe)
    codes = {issue.code for issue in result.issues}

    assert result.ready is False
    assert {
        "invalid_capture_timestamp",
        "missing_capture_file",
        "undecodable_capture_file",
        "unsafe_capture_path",
        "inconsistent_camera_resolution",
    } <= codes
    assert result.rejected_frame_count == 4


def test_pairing_prefers_cycle_then_group_then_timestamp() -> None:
    top = [
        _frame(1, "top", 0.0, cycle_id=1, capture_group="group-a"),
        _frame(2, "top", 2.0, cycle_id=2),
        _frame(3, "top", 4.0),
    ]
    side = [
        _frame(11, "side", 0.9, cycle_id=9, capture_group="group-a"),
        _frame(12, "side", 2.8, cycle_id=2),
        _frame(13, "side", 4.1),
    ]

    pairs = pair_capture_frames(top, side, timestamp_tolerance_ms=1000)

    assert [(pair.top_capture_id, pair.side_capture_id) for pair in pairs] == [
        (1, 11),
        (2, 12),
        (3, 13),
    ]
    assert [pair.pair_status for pair in pairs] == ["paired", "paired", "paired"]


def test_pairing_cycle_wins_when_capture_group_conflicts() -> None:
    top = [
        _frame(1, "top", 0.0, cycle_id=1, capture_group="group-a"),
        _frame(2, "top", 10.0, cycle_id=2, capture_group="group-b"),
    ]
    side = [
        _frame(11, "side", 0.1, cycle_id=2, capture_group="group-a"),
        _frame(12, "side", 10.1, cycle_id=1, capture_group="group-b"),
    ]

    pairs = pair_capture_frames(top, side, timestamp_tolerance_ms=20_000)

    assert {
        (pair.top_capture_id, pair.side_capture_id)
        for pair in pairs
    } == {(1, 12), (2, 11)}
    assert {pair.cycle_id for pair in pairs} == {1, 2}


def test_pairing_attaches_rotating_frame_and_angle_without_changing_stereo_pair() -> None:
    top = [_frame(1, "top", 0.0, cycle_id=1)]
    side = [_frame(2, "side", 0.01, cycle_id=1)]
    rotating = [
        _frame(
            3,
            "rotating",
            0.02,
            cycle_id=1,
            angle_deg=45.0,
        )
    ]

    [pair] = pair_capture_frames(top, side, rotating)

    assert pair.top_frame_id == 1
    assert pair.side_frame_id == 2
    assert pair.rotating_frame_id == 3
    assert pair.rotating_angle_deg == 45.0


def test_timestamp_fallback_is_globally_one_to_one() -> None:
    top = [_frame(1, "top", 0.0), _frame(2, "top", 4.0)]
    side = [_frame(11, "side", 3.0), _frame(12, "side", 5.0)]

    pairs = pair_capture_frames(top, side, timestamp_tolerance_ms=10_000)

    assert [(pair.top_capture_id, pair.side_capture_id) for pair in pairs] == [
        (1, 11),
        (2, 12),
    ]
    assert len({pair.side_capture_id for pair in pairs}) == 2


def test_timestamp_fallback_skips_the_best_extra_frame() -> None:
    top = [_frame(1, "top", 0.0), _frame(2, "top", 10.0)]
    side = [
        _frame(11, "side", 0.0),
        _frame(12, "side", 1.0),
        _frame(13, "side", 10.0),
    ]

    pairs = pair_capture_frames(top, side, timestamp_tolerance_ms=10_000)

    assert [(pair.top_capture_id, pair.side_capture_id) for pair in pairs] == [
        (1, 11),
        (None, 12),
        (2, 13),
    ]
    assert pairs[1].pair_status == "top_missing"


def test_timestamp_tolerance_includes_boundary() -> None:
    top = [_frame(1, "top", 0.0), _frame(2, "top", 3.0)]
    side = [_frame(11, "side", 1.0), _frame(12, "side", 4.001)]

    pairs = pair_capture_frames(top, side, timestamp_tolerance_ms=1000)

    assert pairs[0].timestamp_delta_ms == 1000.0
    assert pairs[0].pair_status == "paired"
    assert pairs[1].timestamp_delta_ms == 1001.0
    assert pairs[1].pair_status == "outside_tolerance"


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (
            1,
            [
                (None, 11, "top_missing"),
                (1, 12, "manually_aligned"),
                (2, 13, "manually_aligned"),
                (3, None, "side_missing"),
            ],
        ),
        (
            -1,
            [
                (1, None, "side_missing"),
                (2, 11, "manually_aligned"),
                (3, 12, "manually_aligned"),
                (None, 13, "top_missing"),
            ],
        ),
    ],
)
def test_manual_frame_offset_supports_both_directions(
    offset: int,
    expected: list[tuple[int | None, int | None, str]],
) -> None:
    top = [_frame(index, "top", float(index)) for index in (1, 2, 3)]
    side = [_frame(index, "side", float(index - 10)) for index in (11, 12, 13)]

    pairs = pair_capture_frames(top, side, manual_frame_offset=offset)

    assert [
        (pair.top_capture_id, pair.side_capture_id, pair.pair_status)
        for pair in pairs
    ] == expected
    assert all(pair.frame_offset == offset for pair in pairs)


def test_unpaired_frames_are_never_dropped() -> None:
    top = [_frame(1, "top", 0.0), _frame(2, "top", 1.0)]
    side = [_frame(11, "side", 0.0)]

    pairs = pair_capture_frames(top, side)

    assert len(pairs) == 2
    assert sum(pair.pair_status == "paired" for pair in pairs) == 1
    assert sum(pair.pair_status == "side_missing" for pair in pairs) == 1


def test_pairing_rejects_duplicate_capture_ids_and_invalid_tolerance() -> None:
    duplicate_top = [_frame(1, "top", 0.0), _frame(1, "top", 1.0)]
    side = [_frame(11, "side", 0.0)]

    with pytest.raises(ValueError, match="重複"):
        pair_capture_frames(duplicate_top, side)
    with pytest.raises(ValueError, match="容差"):
        pair_capture_frames([_frame(1, "top", 0.0)], side, timestamp_tolerance_ms=float("nan"))
