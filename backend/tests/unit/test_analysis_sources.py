from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.analysis.record_validator import CaptureFrame
from app.analysis.rounds import group_analysis_rounds
from app.models.analysis_models import (
    AnalysisCameraSource,
    AnalysisCreateRequest,
)


def _frame(
    tmp_path,
    *,
    capture_id: int,
    camera_id: str,
    round_id: str,
    snapshot_id: str,
    angle_deg: float | None = None,
) -> CaptureFrame:
    timestamp = datetime(2026, 7, 22, tzinfo=timezone.utc) + timedelta(
        seconds=capture_id
    )
    relative_path = (
        "modes/AngleInterval.01/rounds/"
        f"{round_id}/{snapshot_id}/{camera_id}/image.png"
    )
    return CaptureFrame(
        capture_id=capture_id,
        camera_id=camera_id,
        timestamp=timestamp.isoformat(),
        file_path=tmp_path / relative_path,
        relative_path=relative_path,
        angle_deg=angle_deg,
        motor_position_deg=angle_deg,
        capture_group=(
            f"modes/AngleInterval.01/rounds/{round_id}/{snapshot_id}"
        ),
        resolution=(1280, 960),
    )


def test_analysis_request_uses_only_formal_methods_and_selected_modes() -> None:
    sources = {
        camera_id: AnalysisCameraSource(enabled=True, path="record-root")
        for camera_id in ("top", "side", "rotating")
    }
    request = AnalysisCreateRequest(
        record_id="record-1",
        mode_ids=["AngleInterval.01"],
        method="round_multiview",
        camera_sources=sources,
    )

    assert request.method == "round_multiview"
    assert request.mode_ids == ["AngleInterval.01"]
    with pytest.raises(ValidationError):
        AnalysisCreateRequest(
            record_id="record-1",
            mode_ids=["AngleInterval.01"],
            method="top_side",
            camera_sources=sources,
        )


def test_round_grouping_preserves_all_rotating_views(tmp_path) -> None:
    frames = [
        _frame(
            tmp_path,
            capture_id=1,
            camera_id="top",
            round_id="round.01",
            snapshot_id="snapshot.01",
        ),
        _frame(
            tmp_path,
            capture_id=2,
            camera_id="side",
            round_id="round.01",
            snapshot_id="snapshot.01",
        ),
        _frame(
            tmp_path,
            capture_id=3,
            camera_id="rotating",
            round_id="round.01",
            snapshot_id="snapshot.01",
            angle_deg=0,
        ),
        _frame(
            tmp_path,
            capture_id=4,
            camera_id="rotating",
            round_id="round.01",
            snapshot_id="snapshot.02",
            angle_deg=90,
        ),
        _frame(
            tmp_path,
            capture_id=5,
            camera_id="rotating",
            round_id="round.01",
            snapshot_id="snapshot.03",
            angle_deg=180,
        ),
    ]
    grouped = group_analysis_rounds(
        analysis_id="analysis-1",
        record_id="record-1",
        frames=frames,
        mode_ids_by_folder={
            "AngleInterval.01": "AngleInterval.01",
        },
        method="round_multiview",
        enabled_camera_ids=("top", "side", "rotating"),
    )

    assert grouped.errors == ()
    assert grouped.ready_round_count == 1
    assert grouped.rounds[0].rotating_view_count == 3
    assert len(grouped.views) == 5


def test_same_round_number_in_different_modes_never_merges(tmp_path) -> None:
    first = _frame(
        tmp_path,
        capture_id=1,
        camera_id="top",
        round_id="round.01",
        snapshot_id="snapshot.01",
    )
    second = replace(
        first,
        capture_id=2,
        relative_path=first.relative_path.replace(
            "AngleInterval.01",
            "SpecificAngles.01",
        ),
    )
    grouped = group_analysis_rounds(
        analysis_id="analysis-1",
        record_id="record-1",
        frames=(first, second),
        mode_ids_by_folder={
            "AngleInterval.01": "AngleInterval.01",
            "SpecificAngles.01": "SpecificAngles.01",
        },
        method="top_side_tip_only",
        enabled_camera_ids=("top",),
    )

    assert len(grouped.rounds) == 2
    assert len({item.round_key for item in grouped.rounds}) == 2
