from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.analysis.export.csv_export import write_csv_atomic
from app.analysis.export.json_export import write_json_atomic
from app.models.analysis_models import (
    AnalysisFramePair,
    AnalysisRun,
    ManualCorrection,
    StoredDetection,
)


FRAME_PAIR_FIELDS = (
    "pair_id",
    "frame_id",
    "cycle_id",
    "top_frame_id",
    "side_frame_id",
    "rotating_frame_id",
    "top_timestamp",
    "side_timestamp",
    "rotating_timestamp",
    "rotating_angle_deg",
    "timestamp_delta_ms",
    "rotating_timestamp_delta_ms",
    "frame_offset",
    "pair_status",
)

DETECTION_FIELDS = (
    "frame_id",
    "timestamp",
    "candidate_count",
    "selected_x_px",
    "selected_y_px",
    "detection_type",
    "valid",
)

TRAJECTORY_FIELDS = (
    "frame_id",
    "cycle_id",
    "timestamp",
    "top_x_px",
    "top_y_px",
    "side_x_px",
    "side_y_px",
    "rotating_x_px",
    "rotating_y_px",
    "rotating_angle_deg",
    "x_mm",
    "y_mm",
    "z_mm",
    "refined_x_mm",
    "refined_y_mm",
    "refined_z_mm",
    "top_detection_type",
    "side_detection_type",
    "top_reprojection_error_px",
    "side_reprojection_error_px",
    "rotating_reprojection_error_px",
    "rotating_used",
    "valid",
)

REPROJECTION_FIELDS = (
    "frame_id",
    "top_error_px",
    "side_error_px",
    "rotating_error_px",
    "overall_error_px",
    "refined_overall_error_px",
    "high_error",
)


@dataclass(frozen=True, slots=True)
class AnalysisArtifacts:
    """All generated paths for one run.

    The duplicate root-level CSV/JSON files are intentional: section 26 of
    GOAL-02 defines a flat export contract, while section 27 defines a grouped
    on-disk layout. Both contracts are kept in sync atomically.
    """

    root: Path

    @classmethod
    def create(cls, root: Path) -> "AnalysisArtifacts":
        resolved = root.resolve()
        for relative in (
            "detections",
            "reconstruction",
            "summaries",
            "overlays/top",
            "overlays/side",
            "overlays/rotating",
            "masks/top",
            "masks/side",
            "masks/rotating",
            "logs",
        ):
            (resolved / relative).mkdir(parents=True, exist_ok=True)
        return cls(resolved)

    @property
    def log_path(self) -> Path:
        return self.root / "logs" / "analysis.log"

    def write_run(self, run: AnalysisRun) -> None:
        write_json_atomic(self.root / "analysis.json", run.model_dump(mode="json"))

    def write_parameters(self, parameters: dict) -> None:
        write_json_atomic(self.root / "parameters.json", parameters)

    def write_calibration_reference(self, payload: dict) -> None:
        write_json_atomic(self.root / "calibration_reference.json", payload)

    def write_frame_pairs(self, pairs: Iterable[AnalysisFramePair]) -> None:
        rows = [pair.model_dump(mode="json") for pair in pairs]
        write_csv_atomic(self.root / "frame_pairs.csv", FRAME_PAIR_FIELDS, rows)

    @staticmethod
    def _detection_row(detection: StoredDetection, *, resolved: bool) -> dict:
        result = (
            detection.resolved_detection
            if resolved
            else detection.automatic_detection
        )
        if result is None:
            return {
                "frame_id": detection.frame_id,
                "timestamp": None,
                "candidate_count": 0,
                "selected_x_px": None,
                "selected_y_px": None,
                "detection_type": "Missing",
                "valid": False,
            }
        selected = result.selected_point
        return {
            "frame_id": result.frame_id,
            "timestamp": result.timestamp,
            "candidate_count": len(result.candidate_points),
            "selected_x_px": selected.x_px if selected else None,
            "selected_y_px": selected.y_px if selected else None,
            "detection_type": result.detection_type,
            "valid": result.valid,
        }

    def write_detections(
        self,
        camera_id: str,
        detections: Iterable[StoredDetection],
    ) -> None:
        records = list(detections)
        automatic_rows = [
            self._detection_row(item, resolved=False)
            for item in records
        ]
        resolved_rows = [
            self._detection_row(item, resolved=True)
            for item in records
        ]
        write_csv_atomic(
            self.root / f"{camera_id}_detections.csv",
            DETECTION_FIELDS,
            automatic_rows,
        )
        write_csv_atomic(
            self.root / "detections" / f"{camera_id}_automatic.csv",
            DETECTION_FIELDS,
            automatic_rows,
        )
        write_csv_atomic(
            self.root / f"resolved_{camera_id}_positions.csv",
            DETECTION_FIELDS,
            resolved_rows,
        )
        write_csv_atomic(
            self.root / "detections" / f"resolved_{camera_id}.csv",
            DETECTION_FIELDS,
            resolved_rows,
        )

    def write_corrections(
        self,
        corrections: Iterable[ManualCorrection],
    ) -> None:
        payload = [item.model_dump(mode="json") for item in corrections]
        write_json_atomic(self.root / "manual_corrections.json", payload)
        write_json_atomic(
            self.root / "detections" / "manual_corrections.json",
            payload,
        )

    def write_trajectory(self, rows: list[dict]) -> None:
        write_csv_atomic(
            self.root / "trajectory_3d.csv",
            TRAJECTORY_FIELDS,
            rows,
        )
        write_csv_atomic(
            self.root / "reconstruction" / "trajectory_3d.csv",
            TRAJECTORY_FIELDS,
            rows,
        )

    def write_reprojection_errors(self, rows: list[dict]) -> None:
        write_csv_atomic(
            self.root / "reprojection_errors.csv",
            REPROJECTION_FIELDS,
            rows,
        )
        write_csv_atomic(
            self.root / "reconstruction" / "reprojection_errors.csv",
            REPROJECTION_FIELDS,
            rows,
        )

    def write_detection_summary(self, payload: dict) -> None:
        write_json_atomic(self.root / "detection_summary.json", payload)
        write_json_atomic(
            self.root / "summaries" / "detection_summary.json",
            payload,
        )

    def read_csv(self, file_name: str) -> list[dict[str, str]]:
        path = self.root / file_name
        if not path.is_file():
            return []
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
