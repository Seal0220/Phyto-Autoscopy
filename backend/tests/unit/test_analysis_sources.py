from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from pydantic import ValidationError

from app.analysis.source_validator import validate_analysis_sources
from app.models.analysis_models import (
    AnalysisCameraSource,
    AnalysisCreateRequest,
)


def _write_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(
        ".png",
        np.zeros((12, 16, 3), dtype=np.uint8),
    )
    assert ok
    path.write_bytes(encoded.tobytes())


def _sources(root: Path) -> dict[str, AnalysisCameraSource]:
    return {
        camera_id: AnalysisCameraSource(
            enabled=True,
            path=str(root / camera_id),
        )
        for camera_id in ("top", "side", "rotating")
    }


def test_manual_three_camera_sources_accept_angle_csv(tmp_path: Path) -> None:
    for camera_id in ("top", "side", "rotating"):
        _write_image(tmp_path / camera_id / "frame_000001.png")
    (tmp_path / "rotating" / "angles.csv").write_text(
        "filename,angle_deg,cycle_id\nframe_000001.png,45,1\n",
        encoding="utf-8",
    )

    result = validate_analysis_sources(
        _sources(tmp_path),
        method="top_side_rotating",
        allowed_roots=(tmp_path,),
    )

    assert result.ready is True
    assert result.camera_resolutions == {
        "top": (16, 12),
        "side": (16, 12),
        "rotating": (16, 12),
    }
    assert result.rotating_frames[0].angle_deg == 45.0
    assert result.pairable_frame_count == 1


def test_advanced_sources_reject_rotating_image_without_angle(tmp_path: Path) -> None:
    for camera_id in ("top", "side", "rotating"):
        _write_image(tmp_path / camera_id / "frame_000001.png")

    result = validate_analysis_sources(
        _sources(tmp_path),
        method="top_side_rotating",
        allowed_roots=(tmp_path,),
    )

    assert result.ready is False
    assert any("缺少 angle_角度" in reason for reason in result.not_ready_reasons)


def test_analysis_request_enforces_method_sources_and_canonical_ids() -> None:
    calibration = "calibration-1"
    base_sources = {
        "top": AnalysisCameraSource(enabled=True, path="data/top"),
        "side": AnalysisCameraSource(enabled=True, path="data/side"),
        "rotating": AnalysisCameraSource(enabled=False, path=""),
    }

    request = AnalysisCreateRequest(
        method="top_side",
        camera_sources=base_sources,
        calibration_id=calibration,
    )
    assert request.record_id is None

    with pytest.raises(ValidationError, match="rotating"):
        AnalysisCreateRequest(
            method="top_side_rotating",
            camera_sources=base_sources,
            calibration_id=calibration,
        )

    with pytest.raises(ValidationError, match="top.*side.*rotating"):
        AnalysisCreateRequest(
            method="top_side",
            camera_sources={
                **base_sources,
                "legacy-side": AnalysisCameraSource(
                    enabled=True,
                    path="data/legacy-side",
                ),
            },
            calibration_id=calibration,
        )
