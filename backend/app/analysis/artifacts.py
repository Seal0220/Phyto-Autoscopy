from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.analysis.export.csv_export import write_csv_atomic
from app.analysis.export.json_export import write_json_atomic
from app.analysis.rounds.paths import round_artifact_directory
from app.models.analysis_models import (
    CameraPoseResult,
    AnalysisRound,
    AnalysisRun,
    AnalysisView,
    RoundModelResult,
    TipCorrection,
    TipLandmark,
    TipTrajectoryPoint,
)


TIP_TRAJECTORY_FIELDS = (
    "record_id",
    "mode_id",
    "round_id",
    "snapshot_id",
    "timestamp",
    "x_mm",
    "y_mm",
    "z_mm",
    "confidence",
    "valid",
    "detection_type",
    "visible_view_count",
    "mean_reprojection_error_px",
    "manually_corrected",
    "elapsed_seconds",
    "adjacent_distance_mm",
    "speed_mm_per_second",
    "acceleration_mm_per_second2",
    "direction_x",
    "direction_y",
    "direction_z",
    "horizontal_displacement_mm",
    "vertical_displacement_mm",
    "path_length_mm",
    "curvature_per_mm",
    "missing_segment",
)

ROUND_SUMMARY_FIELDS = (
    "record_id",
    "mode_id",
    "round_id",
    "snapshot_id",
    "status",
    "view_count",
    "top_view_count",
    "side_view_count",
    "rotating_view_count",
    "angular_coverage_deg",
    "duration_seconds",
    "model_status",
    "tip_marker_status",
)


@dataclass(frozen=True, slots=True)
class AnalysisArtifacts:
    """Manage the traceable output tree for one formal Analysis Run."""

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
            "pose_debug",
            "logs",
            "rounds",
            "trajectory",
        ):
            (resolved / relative).mkdir(parents=True, exist_ok=True)
        return cls(resolved)

    @property
    def log_path(self) -> Path:
        return self.root / "logs" / "analysis.log.csv"

    def write_run(self, run: AnalysisRun) -> None:
        payload = run.model_dump(mode="json")
        write_json_atomic(self.root / "run.json", payload)
        (self.root / "analysis.json").unlink(missing_ok=True)

    def write_parameters(self, parameters: dict) -> None:
        write_json_atomic(self.root / "parameters.json", parameters)

    def write_input_manifest(self, payload: list[dict]) -> None:
        write_json_atomic(self.root / "input_manifest.json", payload)

    def write_source_manifest(self, payload: list[dict]) -> None:
        write_json_atomic(self.root / "source_manifest.json", payload)

    def write_round_index(
        self,
        rounds: Iterable[AnalysisRound],
        views: Iterable[AnalysisView],
    ) -> None:
        round_items = list(rounds)
        view_items = list(views)
        write_json_atomic(
            self.root / "round_index.json",
            {
                "rounds": [
                    item.model_dump(mode="json")
                    for item in round_items
                ],
                "views": [
                    item.model_dump(mode="json")
                    for item in view_items
                ],
            },
        )
        views_by_round: dict[str, list[AnalysisView]] = {}
        for view in view_items:
            views_by_round.setdefault(view.round_key, []).append(view)
        for round_item in round_items:
            directory = round_artifact_directory(
                self.root,
                round_item.round_key,
            )
            write_json_atomic(
                directory / "round.json",
                round_item.model_dump(mode="json"),
            )
            write_json_atomic(
                directory / "views.json",
                [
                    item.model_dump(mode="json")
                    for item in views_by_round.get(
                        round_item.round_key,
                        [],
                    )
                ],
            )

    def write_round_pose_results(
        self,
        round_key: str,
        poses: Iterable[CameraPoseResult],
        *,
        detections: Iterable[dict],
        quality: dict,
        pose_estimation_version: str,
    ) -> None:
        directory = round_artifact_directory(self.root, round_key)
        write_json_atomic(
            directory / "camera_poses.json",
            [item.model_dump(mode="json") for item in poses],
        )
        write_json_atomic(
            directory / "aruco_detections.json",
            list(detections),
        )
        write_json_atomic(
            directory / "pose_quality.json",
            {
                "pose_estimation_version": pose_estimation_version,
                **quality,
            },
        )

    def write_round_camera_poses(
        self,
        round_key: str,
        poses: Iterable[CameraPoseResult],
    ) -> None:
        write_json_atomic(
            round_artifact_directory(self.root, round_key)
            / "camera_poses.json",
            [item.model_dump(mode="json") for item in poses],
        )

    def write_round_quality(
        self,
        round_key: str,
        payload: dict,
    ) -> None:
        write_json_atomic(
            round_artifact_directory(self.root, round_key) / "quality.json",
            payload,
        )

    def write_reconstruction_environment(self, payload: dict) -> None:
        write_json_atomic(
            self.root / "reconstruction_environment.json",
            payload,
        )

    def read_undistortion_manifest(self) -> list[dict]:
        path = self.root / "undistortion_manifest.json"
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        views = payload.get("views") if isinstance(payload, dict) else None
        if not isinstance(views, list):
            raise ValueError("去畸變影像清單的視角資料必須是陣列。")
        return [item for item in views if isinstance(item, dict)]

    def write_round_model_result(self, item: RoundModelResult) -> None:
        directory = round_artifact_directory(self.root, item.round_key)
        write_json_atomic(
            directory / "model" / "result.json",
            item.model_dump(mode="json"),
        )
        metadata_path = directory / "model" / "model_metadata.json"
        if not metadata_path.is_file():
            return
        try:
            payload = json.loads(
                metadata_path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, json.JSONDecodeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        write_json_atomic(
            metadata_path,
            {
                **payload,
                "formal_result_status": item.status,
                "gaussian_model_path": item.model_path,
                "plant_gaussian_model_path": item.plant_model_path,
                "background_gaussian_model_path": (
                    item.background_model_path
                ),
                "point_cloud_path": item.point_cloud_path,
                "plant_point_cloud_path": (
                    item.plant_point_cloud_path
                ),
                "background_point_cloud_path": (
                    item.background_point_cloud_path
                ),
                "skeleton_path": item.skeleton_path,
                "preview_paths": item.preview_paths,
                "formal_result": item.model_dump(mode="json"),
            },
        )

    def write_round_model_index(
        self,
        items: Iterable[RoundModelResult],
    ) -> None:
        write_json_atomic(
            self.root / "round_models.json",
            [item.model_dump(mode="json") for item in items],
        )

    def write_tip_landmark(
        self,
        item: TipLandmark,
        *,
        quality: dict | None = None,
    ) -> None:
        payload = item.model_dump(mode="json")
        if quality is not None:
            payload["quality"] = quality
        write_json_atomic(
            round_artifact_directory(self.root, item.round_key)
            / "tip"
            / "tip_marker.json",
            payload,
        )

    def write_tip_corrections(
        self,
        corrections: Iterable[TipCorrection],
    ) -> None:
        records = list(corrections)
        write_json_atomic(
            self.root / "tip_corrections.json",
            [item.model_dump(mode="json") for item in records],
        )
        for path in (self.root / "rounds").rglob(
            "tip/corrections.json"
        ):
            path.unlink(missing_ok=True)
        by_round: dict[str, list[TipCorrection]] = {}
        for item in records:
            by_round.setdefault(item.round_key, []).append(item)
        for round_key, items in by_round.items():
            write_json_atomic(
                round_artifact_directory(self.root, round_key)
                / "tip"
                / "corrections.json",
                [item.model_dump(mode="json") for item in items],
            )

    def write_intrinsics_snapshot(self, payload: dict) -> None:
        write_json_atomic(self.root / "intrinsics_snapshot.json", payload)

    def read_intrinsics_snapshot(self) -> dict:
        path = self.root / "intrinsics_snapshot.json"
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("相機內參快照必須是物件。")
        return payload

    def write_aruco_layout_snapshot(self, payload: dict) -> None:
        write_json_atomic(self.root / "aruco_layout_snapshot.json", payload)

    def read_aruco_layout_snapshot(self) -> dict:
        path = self.root / "aruco_layout_snapshot.json"
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("ArUco 佈局快照必須是物件。")
        return payload

    def write_pose_alignment(self, result: object) -> None:
        payload = (
            result.model_dump(mode="json")
            if hasattr(result, "model_dump")
            else dict(result)
        )
        write_json_atomic(
            self.root / "camera_poses.json",
            payload.get("camera_poses", []),
        )
        write_json_atomic(
            self.root / "aruco_alignment.json",
            {
                "pose_estimation_version": payload.get(
                    "pose_estimation_version"
                ),
                "status": payload.get("aruco_alignment_status"),
                "fixed_camera_poses": payload.get("fixed_camera_poses", {}),
                "detections": payload.get("aruco_detections", []),
            },
        )
        write_json_atomic(
            self.root / "pose_quality.json",
            payload.get("quality", {}),
        )

    def write_aggregated_pose_results(
        self,
        poses: Iterable[CameraPoseResult],
        *,
        pose_estimation_version: str,
        round_quality: list[dict],
        fixed_camera_consistency: dict[str, dict],
    ) -> None:
        pose_items = list(poses)
        write_json_atomic(
            self.root / "camera_poses.json",
            [item.model_dump(mode="json") for item in pose_items],
        )
        write_json_atomic(
            self.root / "aruco_alignment.json",
            {
                "pose_estimation_version": pose_estimation_version,
                "coordinate_space": "undistorted",
                "round_count": len(round_quality),
            },
        )
        write_json_atomic(
            self.root / "pose_quality.json",
            {
                "coordinate_space": "undistorted",
                "fixed_camera_consistency": fixed_camera_consistency,
                "rounds": round_quality,
            },
        )

    def clear_pose_alignment(self) -> None:
        for file_name in (
            "camera_poses.json",
            "aruco_alignment.json",
            "pose_quality.json",
        ):
            (self.root / file_name).unlink(missing_ok=True)
        debug_directory = self.root / "pose_debug"
        if debug_directory.is_dir():
            for path in debug_directory.iterdir():
                if path.is_file():
                    path.unlink()

    def read_camera_poses(self) -> list[dict]:
        path = self.root / "camera_poses.json"
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, list):
            raise ValueError("相機姿態資料必須是陣列。")
        return [item for item in payload if isinstance(item, dict)]

    def write_tip_trajectory(
        self,
        points: Iterable[TipTrajectoryPoint],
        quality: dict,
        *,
        export_csv: bool = True,
    ) -> None:
        records = list(points)
        rows = [
            {
                field: getattr(item, field)
                for field in TIP_TRAJECTORY_FIELDS
            }
            for item in records
        ]
        csv_path = (
            self.root / "trajectory" / "tip_marker_trajectory.csv"
        )
        if export_csv:
            write_csv_atomic(
                csv_path,
                TIP_TRAJECTORY_FIELDS,
                rows,
            )
        else:
            csv_path.unlink(missing_ok=True)
        write_json_atomic(
            self.root / "trajectory" / "tip_marker_trajectory.json",
            [item.model_dump(mode="json") for item in records],
        )
        write_json_atomic(
            self.root / "trajectory" / "trajectory_quality.json",
            quality,
        )

    def write_formal_summaries(
        self,
        rounds: Iterable[AnalysisRound],
        models: Iterable[RoundModelResult],
        landmarks: Iterable[TipLandmark],
        trajectory_quality: dict,
    ) -> None:
        round_items = list(rounds)
        model_items = list(models)
        landmark_items = list(landmarks)
        models_by_round = {
            item.round_key: item
            for item in model_items
        }
        landmarks_by_round = {
            item.round_key: item
            for item in landmark_items
        }
        rows = []
        for item in round_items:
            model = models_by_round.get(item.round_key)
            landmark = landmarks_by_round.get(item.round_key)
            rows.append({
                "record_id": item.record_id,
                "mode_id": item.mode_id,
                "round_id": item.round_id,
                "snapshot_id": item.snapshot_id,
                "status": item.status,
                "view_count": item.view_count,
                "top_view_count": item.top_view_count,
                "side_view_count": item.side_view_count,
                "rotating_view_count": item.rotating_view_count,
                "angular_coverage_deg": item.angular_coverage_deg,
                "duration_seconds": item.duration_seconds,
                "model_status": model.status if model is not None else None,
                "tip_marker_status": (
                    "valid"
                    if landmark is not None and landmark.valid
                    else "invalid"
                    if landmark is not None
                    else "missing"
                ),
            })
        write_csv_atomic(
            self.root / "summaries" / "round_summary.csv",
            ROUND_SUMMARY_FIELDS,
            rows,
        )
        write_json_atomic(
            self.root / "summaries" / "model_quality.json",
            [
                {
                    "round_key": item.round_key,
                    "status": item.status,
                    "backend": item.backend,
                    "backend_version": item.backend_version,
                    "repository_url": item.repository_url,
                    "repository_commit": item.repository_commit,
                    "license": item.license,
                    "environment": item.environment,
                    "model_path": item.model_path,
                    "plant_model_path": item.plant_model_path,
                    "background_model_path": item.background_model_path,
                    "point_cloud_path": item.point_cloud_path,
                    "plant_point_cloud_path": (
                        item.plant_point_cloud_path
                    ),
                    "background_point_cloud_path": (
                        item.background_point_cloud_path
                    ),
                    "skeleton_path": item.skeleton_path,
                    "preview_paths": item.preview_paths,
                    "quality": item.model_quality,
                    "failure_reason": item.failure_reason,
                }
                for item in model_items
            ],
        )
        write_json_atomic(
            self.root / "summaries" / "tip_marker_quality.json",
            [item.model_dump(mode="json") for item in landmark_items],
        )
        write_json_atomic(
            self.root / "summaries" / "analysis_summary.json",
            {
                "round_count": len(round_items),
                "completed_round_count": sum(
                    item.status == "tip_completed"
                    for item in round_items
                ),
                "failed_round_count": sum(
                    item.status in {
                        "failed",
                        "model_failed",
                        "tip_only",
                        "tip_invalid",
                    }
                    for item in round_items
                ),
                "tip_marker_count": sum(
                    item.valid
                    for item in landmark_items
                ),
                "trajectory": trajectory_quality,
            },
        )

    def read_csv(self, file_name: str) -> list[dict[str, str]]:
        path = self.root / file_name
        if not path.is_file():
            return []
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
