from __future__ import annotations

import json
from typing import Iterable

from app.database.connection import Database
from app.models.analysis_models import (
    AnalysisRound,
    AnalysisRun,
    AnalysisView,
    CameraPoseResult,
    RoundModelResult,
    TipCorrection,
    TipLandmark,
    TipObservation2D,
    TipTrajectoryPoint,
)


def _json_dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_load(value: str | None, fallback):
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return fallback


SUPPORTED_ANALYSIS_METHODS = (
    "fixed",
    "rotating",
)


class AnalysisRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _run_from_row(row) -> AnalysisRun:
        payload = dict(row)
        payload["parameters"] = _json_load(payload.pop("parameters_json"), {})
        payload["intrinsics_snapshot"] = _json_load(
            payload.pop("intrinsics_snapshot_json"),
            {},
        )
        payload["aruco_layout_snapshot"] = _json_load(
            payload.pop("aruco_layout_snapshot_json"),
            {},
        )
        payload["camera_pose_results"] = _json_load(
            payload.pop("camera_pose_results_json"),
            [],
        )
        payload["pose_quality"] = _json_load(
            payload.pop("pose_quality_json"),
            {},
        )
        payload["reconstruction_environment"] = _json_load(
            payload.pop("reconstruction_environment_json", None),
            {},
        )
        payload["manual_review_completed"] = bool(
            payload["manual_review_completed"]
        )
        return AnalysisRun(**payload)

    def create(self, run: AnalysisRun) -> None:
        self.database.execute(
            """
            INSERT INTO analysis_runs(
                analysis_id, record_id, method_name,
                method_version, git_commit, parameters_json, created_at,
                updated_at, created_by, output_path, status, stage,
                current_frame, total_frames, progress,
                manual_review_completed, last_error,
                intrinsics_snapshot_json, aruco_layout_snapshot_json,
                camera_pose_results_json, pose_estimation_version,
                pose_quality_json, reconstruction_backend,
                reconstruction_backend_version,
                reconstruction_environment_json, round_count,
                completed_round_count, failed_round_count,
                tip_marker_count, trajectory_status
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                run.analysis_id,
                run.record_id,
                run.method_name,
                run.method_version,
                run.git_commit,
                _json_dump(run.parameters),
                run.created_at,
                run.updated_at,
                run.created_by,
                run.output_path,
                run.status,
                run.stage,
                run.current_frame,
                run.total_frames,
                run.progress,
                int(run.manual_review_completed),
                run.last_error,
                _json_dump(run.intrinsics_snapshot),
                _json_dump(run.aruco_layout_snapshot),
                _json_dump(run.camera_pose_results),
                run.pose_estimation_version,
                _json_dump(run.pose_quality),
                run.reconstruction_backend,
                run.reconstruction_backend_version,
                _json_dump(run.reconstruction_environment),
                run.round_count,
                run.completed_round_count,
                run.failed_round_count,
                run.tip_marker_count,
                run.trajectory_status,
            ),
        )

    def get(self, analysis_id: str) -> AnalysisRun | None:
        row = self.database.fetchone(
            """
            SELECT * FROM analysis_runs
            WHERE analysis_id=? AND method_name IN (?, ?)
            """,
            (analysis_id, *SUPPORTED_ANALYSIS_METHODS),
        )
        return self._run_from_row(row) if row else None

    def list(self, record_id: str | None = None) -> list[AnalysisRun]:
        if record_id is None:
            rows = self.database.fetchall(
                """
                SELECT * FROM analysis_runs
                WHERE method_name IN (?, ?)
                ORDER BY created_at DESC
                """,
                SUPPORTED_ANALYSIS_METHODS,
            )
        else:
            rows = self.database.fetchall(
                """
                SELECT * FROM analysis_runs
                WHERE record_id=? AND method_name IN (?, ?)
                ORDER BY created_at DESC
                """,
                (record_id, *SUPPORTED_ANALYSIS_METHODS),
            )
        return [self._run_from_row(row) for row in rows]

    def update_state(
        self,
        analysis_id: str,
        *,
        updated_at: str,
        status: str | None = None,
        stage: str | None = None,
        current_frame: int | None = None,
        total_frames: int | None = None,
        progress: float | None = None,
        completed_round_count: int | None = None,
        failed_round_count: int | None = None,
        tip_marker_count: int | None = None,
        trajectory_status: str | None = None,
        manual_review_completed: bool | None = None,
        last_error: str | None = None,
        clear_error: bool = False,
    ) -> None:
        assignments = ["updated_at=?"]
        values: list[object] = [updated_at]
        optional_values = {
            "status": status,
            "stage": stage,
            "current_frame": current_frame,
            "total_frames": total_frames,
            "progress": progress,
            "completed_round_count": completed_round_count,
            "failed_round_count": failed_round_count,
            "tip_marker_count": tip_marker_count,
            "trajectory_status": trajectory_status,
        }
        for name, value in optional_values.items():
            if value is not None:
                assignments.append(f"{name}=?")
                values.append(value)
        if manual_review_completed is not None:
            assignments.append("manual_review_completed=?")
            values.append(int(manual_review_completed))
        if last_error is not None or clear_error:
            assignments.append("last_error=?")
            values.append(last_error)
        values.append(analysis_id)
        self.database.execute(
            f"UPDATE analysis_runs SET {', '.join(assignments)} WHERE analysis_id=?",
            values,
        )

    def update_parameters(
        self,
        analysis_id: str,
        parameters: dict,
        updated_at: str,
    ) -> None:
        self.database.execute(
            """
            UPDATE analysis_runs
            SET parameters_json=?, updated_at=?
            WHERE analysis_id=?
            """,
            (_json_dump(parameters), updated_at, analysis_id),
        )

    def update_cancellation_metadata(
        self,
        analysis_id: str,
        *,
        requested_at: str,
        requested_by: str,
        updated_at: str,
    ) -> None:
        self.database.execute(
            """
            UPDATE analysis_runs
            SET cancel_requested_at=?, cancel_requested_by=?, updated_at=?
            WHERE analysis_id=?
            """,
            (
                requested_at,
                requested_by,
                updated_at,
                analysis_id,
            ),
        )

    def update_reconstruction_metadata(
        self,
        analysis_id: str,
        *,
        backend: str,
        backend_version: str,
        environment: dict,
        updated_at: str,
    ) -> None:
        self.database.execute(
            """
            UPDATE analysis_runs
            SET reconstruction_backend=?,
                reconstruction_backend_version=?,
                reconstruction_environment_json=?,
                updated_at=?
            WHERE analysis_id=?
            """,
            (
                backend,
                backend_version,
                _json_dump(environment),
                updated_at,
                analysis_id,
            ),
        )

    def update_average_reprojection_error(
        self,
        analysis_id: str,
        value: float | None,
        updated_at: str,
    ) -> None:
        self.database.execute(
            """
            UPDATE analysis_runs
            SET average_reprojection_error_px=?, updated_at=?
            WHERE analysis_id=?
            """,
            (value, updated_at, analysis_id),
        )

    def update_pose_alignment(
        self,
        analysis_id: str,
        *,
        camera_pose_results: list[dict],
        pose_estimation_version: str,
        pose_quality: dict,
        updated_at: str,
    ) -> None:
        self.database.execute(
            """
            UPDATE analysis_runs
            SET camera_pose_results_json=?, pose_estimation_version=?,
                pose_quality_json=?, updated_at=?
            WHERE analysis_id=?
            """,
            (
                _json_dump(camera_pose_results),
                pose_estimation_version,
                _json_dump(pose_quality),
                updated_at,
                analysis_id,
            ),
        )

    def delete(self, analysis_id: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "DELETE FROM analysis_tip_corrections WHERE analysis_id=?",
                (analysis_id,),
            )
            connection.execute(
                "DELETE FROM analysis_trajectory_points WHERE analysis_id=?",
                (analysis_id,),
            )
            connection.execute(
                "DELETE FROM analysis_tip_observations WHERE analysis_id=?",
                (analysis_id,),
            )
            connection.execute(
                "DELETE FROM analysis_tip_landmarks WHERE analysis_id=?",
                (analysis_id,),
            )
            connection.execute(
                "DELETE FROM analysis_round_models WHERE analysis_id=?",
                (analysis_id,),
            )
            connection.execute(
                "DELETE FROM analysis_camera_poses WHERE analysis_id=?",
                (analysis_id,),
            )
            connection.execute(
                "DELETE FROM analysis_runs WHERE analysis_id=?",
                (analysis_id,),
            )

    def clear_results(
        self,
        analysis_id: str,
    ) -> None:
        """Clear derived data in one short transaction.

        Capture records are deliberately outside this repository and can never be
        modified by an analysis reset.
        """

        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE analysis_runs
                SET average_reprojection_error_px=NULL,
                    camera_pose_results_json='[]',
                    pose_estimation_version=NULL,
                    pose_quality_json='{}',
                    completed_round_count=0,
                    failed_round_count=0,
                    tip_marker_count=0,
                    trajectory_status=NULL,
                    reconstruction_backend=NULL,
                    reconstruction_backend_version=NULL,
                    reconstruction_environment_json='{}'
                WHERE analysis_id=?
                """,
                (analysis_id,),
            )
            connection.execute(
                "DELETE FROM analysis_tip_corrections WHERE analysis_id=?",
                (analysis_id,),
            )
            connection.execute(
                "DELETE FROM analysis_trajectory_points WHERE analysis_id=?",
                (analysis_id,),
            )
            connection.execute(
                "DELETE FROM analysis_tip_observations WHERE analysis_id=?",
                (analysis_id,),
            )
            connection.execute(
                "DELETE FROM analysis_tip_landmarks WHERE analysis_id=?",
                (analysis_id,),
            )
            connection.execute(
                "DELETE FROM analysis_round_models WHERE analysis_id=?",
                (analysis_id,),
            )
            connection.execute(
                "DELETE FROM analysis_camera_poses WHERE analysis_id=?",
                (analysis_id,),
            )
    def replace_rounds_and_views(
        self,
        analysis_id: str,
        rounds: Iterable[AnalysisRound],
        views: Iterable[AnalysisView],
    ) -> None:
        round_rows = list(rounds)
        view_rows = list(views)
        with self.database.transaction() as connection:
            connection.execute(
                "DELETE FROM analysis_views WHERE analysis_id=?",
                (analysis_id,),
            )
            connection.execute(
                "DELETE FROM analysis_rounds WHERE analysis_id=?",
                (analysis_id,),
            )
            connection.executemany(
                """
                INSERT INTO analysis_rounds(
                    analysis_id, round_key, record_id, mode_id, round_id,
                    started_at, ended_at, duration_seconds, status, view_count,
                    top_view_count, side_view_count, rotating_view_count,
                    angular_coverage_deg, static_scene_score, model_result_id,
                    tip_landmark_id, failure_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.analysis_id,
                        item.round_key,
                        item.record_id,
                        item.mode_id,
                        item.round_id,
                        item.started_at,
                        item.ended_at,
                        item.duration_seconds,
                        item.status,
                        item.view_count,
                        item.top_view_count,
                        item.side_view_count,
                        item.rotating_view_count,
                        item.angular_coverage_deg,
                        item.static_scene_score,
                        item.model_result_id,
                        item.tip_landmark_id,
                        item.failure_reason,
                    )
                    for item in round_rows
                ],
            )
            connection.executemany(
                """
                INSERT INTO analysis_views(
                    analysis_id, round_key, view_id, capture_id, camera_id,
                    snapshot_id, timestamp, relative_path, absolute_path,
                    angle_deg, motor_position_deg, image_width, image_height,
                    image_sha256, selected_for_reconstruction,
                    exclusion_reason, pose_status,
                    pose_reprojection_error_px
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.analysis_id,
                        item.round_key,
                        item.view_id,
                        item.capture_id,
                        item.camera_id,
                        item.snapshot_id,
                        item.timestamp,
                        item.relative_path,
                        item.absolute_path,
                        item.angle_deg,
                        item.motor_position_deg,
                        item.image_width,
                        item.image_height,
                        item.image_sha256,
                        int(item.selected_for_reconstruction),
                        item.exclusion_reason,
                        item.pose_status,
                        item.pose_reprojection_error_px,
                    )
                    for item in view_rows
                ],
            )

    def list_rounds(self, analysis_id: str) -> list[AnalysisRound]:
        rows = self.database.fetchall(
            """
            SELECT * FROM analysis_rounds
            WHERE analysis_id=?
            ORDER BY mode_id, round_id
            """,
            (analysis_id,),
        )
        return [AnalysisRound(**dict(row)) for row in rows]

    def list_views(
        self,
        analysis_id: str,
        round_key: str | None = None,
    ) -> list[AnalysisView]:
        if round_key is None:
            rows = self.database.fetchall(
                """
                SELECT * FROM analysis_views
                WHERE analysis_id=?
                ORDER BY round_key, timestamp, camera_id
                """,
                (analysis_id,),
            )
        else:
            rows = self.database.fetchall(
                """
                SELECT * FROM analysis_views
                WHERE analysis_id=? AND round_key=?
                ORDER BY timestamp, camera_id
                """,
                (analysis_id, round_key),
            )
        return [
            AnalysisView(
                **{
                    **dict(row),
                    "selected_for_reconstruction": bool(
                        row["selected_for_reconstruction"]
                    ),
                }
            )
            for row in rows
        ]

    def update_round(self, item: AnalysisRound) -> None:
        self.database.execute(
            """
            UPDATE analysis_rounds
            SET started_at=?, ended_at=?, duration_seconds=?, status=?,
                view_count=?, top_view_count=?, side_view_count=?,
                rotating_view_count=?, angular_coverage_deg=?,
                static_scene_score=?, model_result_id=?,
                tip_landmark_id=?, failure_reason=?
            WHERE analysis_id=? AND round_key=?
            """,
            (
                item.started_at,
                item.ended_at,
                item.duration_seconds,
                item.status,
                item.view_count,
                item.top_view_count,
                item.side_view_count,
                item.rotating_view_count,
                item.angular_coverage_deg,
                item.static_scene_score,
                item.model_result_id,
                item.tip_landmark_id,
                item.failure_reason,
                item.analysis_id,
                item.round_key,
            ),
        )

    def update_views(self, views: Iterable[AnalysisView]) -> None:
        records = list(views)
        with self.database.transaction() as connection:
            connection.executemany(
                """
                UPDATE analysis_views
                SET selected_for_reconstruction=?, exclusion_reason=?,
                    pose_status=?, pose_reprojection_error_px=?
                WHERE analysis_id=? AND view_id=?
                """,
                [
                    (
                        int(item.selected_for_reconstruction),
                        item.exclusion_reason,
                        item.pose_status,
                        item.pose_reprojection_error_px,
                        item.analysis_id,
                        item.view_id,
                    )
                    for item in records
                ],
            )

    def replace_camera_poses(
        self,
        analysis_id: str,
        poses: Iterable[CameraPoseResult],
    ) -> None:
        records = list(poses)
        with self.database.transaction() as connection:
            connection.execute(
                "DELETE FROM analysis_camera_poses WHERE analysis_id=?",
                (analysis_id,),
            )
            connection.executemany(
                """
                INSERT INTO analysis_camera_poses(
                    analysis_id, round_key, view_id, camera_id,
                    payload_json, valid, pose_source, failure_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.analysis_id,
                        item.round_key,
                        item.view_id,
                        item.camera_id,
                        _json_dump(item.model_dump(mode="json")),
                        int(item.valid),
                        item.pose_source,
                        item.failure_reason,
                    )
                    for item in records
                ],
            )

    def list_camera_poses(
        self,
        analysis_id: str,
        round_key: str | None = None,
    ) -> list[CameraPoseResult]:
        if round_key is None:
            rows = self.database.fetchall(
                """
                SELECT payload_json FROM analysis_camera_poses
                WHERE analysis_id=?
                ORDER BY round_key, view_id
                """,
                (analysis_id,),
            )
        else:
            rows = self.database.fetchall(
                """
                SELECT payload_json FROM analysis_camera_poses
                WHERE analysis_id=? AND round_key=?
                ORDER BY view_id
                """,
                (analysis_id, round_key),
            )
        return [
            CameraPoseResult.model_validate(
                _json_load(row["payload_json"], {})
            )
            for row in rows
        ]

    def upsert_round_model(self, item: RoundModelResult) -> None:
        self.database.execute(
            """
            INSERT INTO analysis_round_models(
                analysis_id, round_key, model_id, status,
                payload_json, failure_reason
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(analysis_id, model_id) DO UPDATE SET
                status=excluded.status,
                payload_json=excluded.payload_json,
                failure_reason=excluded.failure_reason
            """,
            (
                item.analysis_id,
                item.round_key,
                item.model_id,
                item.status,
                _json_dump(item.model_dump(mode="json")),
                item.failure_reason,
            ),
        )

    def list_round_models(
        self,
        analysis_id: str,
    ) -> list[RoundModelResult]:
        rows = self.database.fetchall(
            """
            SELECT payload_json FROM analysis_round_models
            WHERE analysis_id=?
            ORDER BY round_key
            """,
            (analysis_id,),
        )
        return [
            RoundModelResult.model_validate(
                _json_load(row["payload_json"], {})
            )
            for row in rows
        ]

    def upsert_tip_landmark(self, item: TipLandmark) -> None:
        self.database.execute(
            """
            INSERT INTO analysis_tip_landmarks(
                analysis_id, round_key, tip_id, payload_json,
                valid, confidence
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(analysis_id, tip_id) DO UPDATE SET
                payload_json=excluded.payload_json,
                valid=excluded.valid,
                confidence=excluded.confidence
            """,
            (
                item.analysis_id,
                item.round_key,
                item.tip_id,
                _json_dump(item.model_dump(mode="json")),
                int(item.valid),
                item.confidence,
            ),
        )

    def list_tip_landmarks(self, analysis_id: str) -> list[TipLandmark]:
        rows = self.database.fetchall(
            """
            SELECT payload_json FROM analysis_tip_landmarks
            WHERE analysis_id=?
            ORDER BY round_key
            """,
            (analysis_id,),
        )
        return [
            TipLandmark.model_validate(_json_load(row["payload_json"], {}))
            for row in rows
        ]

    def replace_tip_observations(
        self,
        analysis_id: str,
        round_key: str,
        observations: Iterable[TipObservation2D],
    ) -> None:
        records = list(observations)
        with self.database.transaction() as connection:
            connection.execute(
                """
                DELETE FROM analysis_tip_observations
                WHERE analysis_id=? AND round_key=?
                """,
                (analysis_id, round_key),
            )
            connection.executemany(
                """
                INSERT INTO analysis_tip_observations(
                    analysis_id, round_key, view_id, candidate_id,
                    payload_json, selected
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.analysis_id,
                        item.round_key,
                        item.view_id,
                        item.candidate_id,
                        _json_dump(item.model_dump(mode="json")),
                        int(item.selected),
                    )
                    for item in records
                ],
            )

    def list_tip_observations(
        self,
        analysis_id: str,
        round_key: str | None = None,
    ) -> list[TipObservation2D]:
        if round_key is None:
            rows = self.database.fetchall(
                """
                SELECT payload_json FROM analysis_tip_observations
                WHERE analysis_id=?
                ORDER BY round_key, view_id, candidate_id
                """,
                (analysis_id,),
            )
        else:
            rows = self.database.fetchall(
                """
                SELECT payload_json FROM analysis_tip_observations
                WHERE analysis_id=? AND round_key=?
                ORDER BY view_id, candidate_id
                """,
                (analysis_id, round_key),
            )
        return [
            TipObservation2D.model_validate(
                _json_load(row["payload_json"], {})
            )
            for row in rows
        ]

    def insert_tip_correction(self, item: TipCorrection) -> None:
        self.database.execute(
            """
            INSERT INTO analysis_tip_corrections(
                correction_id, analysis_id, round_key,
                operator_id, created_at, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                item.correction_id,
                item.analysis_id,
                item.round_key,
                item.operator_id,
                item.created_at,
                _json_dump(item.model_dump(mode="json")),
            ),
        )

    def list_tip_corrections(
        self,
        analysis_id: str,
        round_key: str | None = None,
    ) -> list[TipCorrection]:
        if round_key is None:
            rows = self.database.fetchall(
                """
                SELECT payload_json FROM analysis_tip_corrections
                WHERE analysis_id=?
                ORDER BY created_at, correction_id
                """,
                (analysis_id,),
            )
        else:
            rows = self.database.fetchall(
                """
                SELECT payload_json FROM analysis_tip_corrections
                WHERE analysis_id=? AND round_key=?
                ORDER BY created_at, correction_id
                """,
                (analysis_id, round_key),
            )
        return [
            TipCorrection.model_validate(_json_load(row["payload_json"], {}))
            for row in rows
        ]

    def delete_tip_correction(
        self,
        analysis_id: str,
        correction_id: str,
    ) -> bool:
        cursor = self.database.execute(
            """
            DELETE FROM analysis_tip_corrections
            WHERE analysis_id=? AND correction_id=?
            """,
            (analysis_id, correction_id),
        )
        return cursor.rowcount > 0

    def replace_tip_trajectory(
        self,
        analysis_id: str,
        points: Iterable[TipTrajectoryPoint],
    ) -> None:
        records = list(points)
        with self.database.transaction() as connection:
            connection.execute(
                "DELETE FROM analysis_trajectory_points WHERE analysis_id=?",
                (analysis_id,),
            )
            connection.executemany(
                """
                INSERT INTO analysis_trajectory_points(
                    analysis_id, mode_id, round_key, point_index,
                    payload_json
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.analysis_id,
                        item.mode_id,
                        item.round_key,
                        item.point_index,
                        _json_dump(item.model_dump(mode="json")),
                    )
                    for item in records
                ],
            )

    def list_tip_trajectory(
        self,
        analysis_id: str,
        mode_id: str | None = None,
    ) -> list[TipTrajectoryPoint]:
        if mode_id is None:
            rows = self.database.fetchall(
                """
                SELECT payload_json FROM analysis_trajectory_points
                WHERE analysis_id=?
                ORDER BY mode_id, point_index
                """,
                (analysis_id,),
            )
        else:
            rows = self.database.fetchall(
                """
                SELECT payload_json FROM analysis_trajectory_points
                WHERE analysis_id=? AND mode_id=?
                ORDER BY point_index
                """,
                (analysis_id, mode_id),
            )
        return [
            TipTrajectoryPoint.model_validate(
                _json_load(row["payload_json"], {})
            )
            for row in rows
        ]
