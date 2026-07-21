from __future__ import annotations

import json
from typing import Iterable

from app.database.connection import Database
from app.models.analysis_models import (
    AnalysisFramePair,
    AnalysisRun,
    ManualCorrection,
    StoredDetection,
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
                pose_quality_json
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?
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
            ),
        )

    def get(self, analysis_id: str) -> AnalysisRun | None:
        row = self.database.fetchone(
            "SELECT * FROM analysis_runs WHERE analysis_id=?",
            (analysis_id,),
        )
        return self._run_from_row(row) if row else None

    def list(self, record_id: str | None = None) -> list[AnalysisRun]:
        if record_id is None:
            rows = self.database.fetchall(
                "SELECT * FROM analysis_runs ORDER BY created_at DESC"
            )
        else:
            rows = self.database.fetchall(
                """
                SELECT * FROM analysis_runs
                WHERE record_id=?
                ORDER BY created_at DESC
                """,
                (record_id,),
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
                "DELETE FROM manual_corrections WHERE analysis_id=?",
                (analysis_id,),
            )
            connection.execute(
                "DELETE FROM analysis_detections WHERE analysis_id=?",
                (analysis_id,),
            )
            connection.execute(
                "DELETE FROM analysis_frame_pairs WHERE analysis_id=?",
                (analysis_id,),
            )
            connection.execute(
                "DELETE FROM analysis_runs WHERE analysis_id=?",
                (analysis_id,),
            )

    def clear_results(
        self,
        analysis_id: str,
        *,
        include_frame_pairs: bool = False,
        include_corrections: bool = False,
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
                    pose_quality_json='{}'
                WHERE analysis_id=?
                """,
                (analysis_id,),
            )
            if include_corrections:
                connection.execute(
                    "DELETE FROM manual_corrections WHERE analysis_id=?",
                    (analysis_id,),
                )
            connection.execute(
                "DELETE FROM analysis_detections WHERE analysis_id=?",
                (analysis_id,),
            )
            if include_frame_pairs:
                connection.execute(
                    "DELETE FROM analysis_frame_pairs WHERE analysis_id=?",
                    (analysis_id,),
                )

    def update_average_reprojection_error(
        self,
        analysis_id: str,
        value: float | None,
    ) -> None:
        self.database.execute(
            """
            UPDATE analysis_runs
            SET average_reprojection_error_px=?
            WHERE analysis_id=?
            """,
            (value, analysis_id),
        )

    def replace_frame_pairs(
        self,
        analysis_id: str,
        pairs: Iterable[AnalysisFramePair],
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "DELETE FROM analysis_frame_pairs WHERE analysis_id=?",
                (analysis_id,),
            )
            connection.executemany(
                """
                INSERT INTO analysis_frame_pairs(
                    analysis_id, pair_id, frame_id, cycle_id,
                    top_input_id, side_input_id, rotating_input_id,
                    top_timestamp, side_timestamp, rotating_timestamp,
                    rotating_angle_deg, timestamp_delta_ms,
                    rotating_timestamp_delta_ms, frame_offset, pair_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        analysis_id,
                        pair.pair_id,
                        pair.frame_id,
                        pair.cycle_id,
                        pair.top_frame_id,
                        pair.side_frame_id,
                        pair.rotating_frame_id,
                        pair.top_timestamp,
                        pair.side_timestamp,
                        pair.rotating_timestamp,
                        pair.rotating_angle_deg,
                        pair.timestamp_delta_ms,
                        pair.rotating_timestamp_delta_ms,
                        pair.frame_offset,
                        pair.pair_status,
                    )
                    for pair in pairs
                ],
            )

    def list_frame_pairs(self, analysis_id: str) -> list[AnalysisFramePair]:
        rows = self.database.fetchall(
            """
            SELECT
                pair_id, frame_id, cycle_id,
                COALESCE(top_input_id, top_capture_id) AS top_frame_id,
                COALESCE(side_input_id, side_capture_id) AS side_frame_id,
                rotating_input_id AS rotating_frame_id,
                top_timestamp, side_timestamp, rotating_timestamp,
                rotating_angle_deg, timestamp_delta_ms,
                rotating_timestamp_delta_ms, frame_offset, pair_status
            FROM analysis_frame_pairs
            WHERE analysis_id=?
            ORDER BY frame_id ASC
            """,
            (analysis_id,),
        )
        return [AnalysisFramePair(**dict(row)) for row in rows]

    def get_frame_pair(
        self,
        analysis_id: str,
        frame_id: int,
    ) -> AnalysisFramePair | None:
        row = self.database.fetchone(
            """
            SELECT
                pair_id, frame_id, cycle_id,
                COALESCE(top_input_id, top_capture_id) AS top_frame_id,
                COALESCE(side_input_id, side_capture_id) AS side_frame_id,
                rotating_input_id AS rotating_frame_id,
                top_timestamp, side_timestamp, rotating_timestamp,
                rotating_angle_deg, timestamp_delta_ms,
                rotating_timestamp_delta_ms, frame_offset, pair_status
            FROM analysis_frame_pairs
            WHERE analysis_id=? AND frame_id=?
            """,
            (analysis_id, frame_id),
        )
        return AnalysisFramePair(**dict(row)) if row else None

    def upsert_detection(self, detection: StoredDetection) -> None:
        self.database.execute(
            """
            INSERT INTO analysis_detections(
                analysis_id, frame_id, camera_id, automatic_json,
                interpolated_json, resolved_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(analysis_id, frame_id, camera_id) DO UPDATE SET
                automatic_json=excluded.automatic_json,
                interpolated_json=excluded.interpolated_json,
                resolved_json=excluded.resolved_json,
                updated_at=excluded.updated_at
            """,
            self._detection_values(detection),
        )

    @staticmethod
    def _detection_values(detection: StoredDetection) -> tuple[object, ...]:
        return (
            detection.analysis_id,
            detection.frame_id,
            detection.camera_id,
            _json_dump(detection.automatic_detection.model_dump())
            if detection.automatic_detection
            else None,
            _json_dump(detection.interpolated_detection.model_dump())
            if detection.interpolated_detection
            else None,
            _json_dump(detection.resolved_detection.model_dump())
            if detection.resolved_detection
            else None,
            detection.updated_at,
        )

    @staticmethod
    def _upsert_detections(
        connection,
        detections: Iterable[StoredDetection],
    ) -> None:
        connection.executemany(
            """
            INSERT INTO analysis_detections(
                analysis_id, frame_id, camera_id, automatic_json,
                interpolated_json, resolved_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(analysis_id, frame_id, camera_id) DO UPDATE SET
                automatic_json=excluded.automatic_json,
                interpolated_json=excluded.interpolated_json,
                resolved_json=excluded.resolved_json,
                updated_at=excluded.updated_at
            """,
            [
                AnalysisRepository._detection_values(detection)
                for detection in detections
            ],
        )

    def upsert_detections(
        self,
        detections: Iterable[StoredDetection],
    ) -> None:
        with self.database.transaction() as connection:
            self._upsert_detections(connection, detections)

    @staticmethod
    def _detection_from_row(row) -> StoredDetection:
        payload = dict(row)
        payload["automatic_detection"] = _json_load(
            payload.pop("automatic_json"),
            None,
        )
        payload["interpolated_detection"] = _json_load(
            payload.pop("interpolated_json"),
            None,
        )
        payload["resolved_detection"] = _json_load(
            payload.pop("resolved_json"),
            None,
        )
        return StoredDetection(**payload)

    def get_detection(
        self,
        analysis_id: str,
        frame_id: int,
        camera_id: str,
    ) -> StoredDetection | None:
        row = self.database.fetchone(
            """
            SELECT
                analysis_id, frame_id, camera_id, automatic_json,
                interpolated_json, resolved_json, updated_at
            FROM analysis_detections
            WHERE analysis_id=? AND frame_id=? AND camera_id=?
            """,
            (analysis_id, frame_id, camera_id),
        )
        return self._detection_from_row(row) if row else None

    def list_detections(
        self,
        analysis_id: str,
        camera_id: str | None = None,
    ) -> list[StoredDetection]:
        if camera_id is None:
            rows = self.database.fetchall(
                """
                SELECT
                    analysis_id, frame_id, camera_id, automatic_json,
                    interpolated_json, resolved_json, updated_at
                FROM analysis_detections
                WHERE analysis_id=?
                ORDER BY frame_id ASC, camera_id ASC
                """,
                (analysis_id,),
            )
        else:
            rows = self.database.fetchall(
                """
                SELECT
                    analysis_id, frame_id, camera_id, automatic_json,
                    interpolated_json, resolved_json, updated_at
                FROM analysis_detections
                WHERE analysis_id=? AND camera_id=?
                ORDER BY frame_id ASC
                """,
                (analysis_id, camera_id),
            )
        return [self._detection_from_row(row) for row in rows]

    def insert_correction(self, correction: ManualCorrection) -> None:
        self.database.execute(
            """
            INSERT INTO manual_corrections(
                correction_id, analysis_id, frame_id, camera_id,
                automatic_x_px, automatic_y_px, corrected_x_px,
                corrected_y_px, operator_id, created_at, reason, invalid
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                correction.correction_id,
                correction.analysis_id,
                correction.frame_id,
                correction.camera_id,
                correction.automatic_x_px,
                correction.automatic_y_px,
                correction.corrected_x_px,
                correction.corrected_y_px,
                correction.operator_id,
                correction.created_at,
                correction.reason,
                int(correction.invalid),
            ),
        )

    @staticmethod
    def _correction_values(correction: ManualCorrection) -> tuple[object, ...]:
        return (
            correction.correction_id,
            correction.analysis_id,
            correction.frame_id,
            correction.camera_id,
            correction.automatic_x_px,
            correction.automatic_y_px,
            correction.corrected_x_px,
            correction.corrected_y_px,
            correction.operator_id,
            correction.created_at,
            correction.reason,
            int(correction.invalid),
        )

    def insert_correction_with_detections(
        self,
        correction: ManualCorrection,
        detections: Iterable[StoredDetection],
        *,
        updated_at: str,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO manual_corrections(
                    correction_id, analysis_id, frame_id, camera_id,
                    automatic_x_px, automatic_y_px, corrected_x_px,
                    corrected_y_px, operator_id, created_at, reason, invalid
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._correction_values(correction),
            )
            self._upsert_detections(connection, detections)
            connection.execute(
                """
                UPDATE analysis_runs
                SET status='reviewing', stage='waiting_for_review',
                    manual_review_completed=0,
                    average_reprojection_error_px=NULL,
                    last_error=NULL, updated_at=?
                WHERE analysis_id=?
                """,
                (updated_at, correction.analysis_id),
            )

    def delete_correction_with_detections(
        self,
        analysis_id: str,
        correction_id: str,
        detections: Iterable[StoredDetection],
        *,
        updated_at: str,
    ) -> bool:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                DELETE FROM manual_corrections
                WHERE analysis_id=? AND correction_id=?
                """,
                (analysis_id, correction_id),
            )
            if cursor.rowcount <= 0:
                return False
            self._upsert_detections(connection, detections)
            connection.execute(
                """
                UPDATE analysis_runs
                SET status='reviewing', stage='waiting_for_review',
                    manual_review_completed=0,
                    average_reprojection_error_px=NULL,
                    last_error=NULL, updated_at=?
                WHERE analysis_id=?
                """,
                (updated_at, analysis_id),
            )
            return True

    def upsert_correction(self, correction: ManualCorrection) -> None:
        """Backward-compatible name; corrections are append-only."""

        self.insert_correction(correction)

    def list_corrections(self, analysis_id: str) -> list[ManualCorrection]:
        rows = self.database.fetchall(
            """
            SELECT * FROM manual_corrections
            WHERE analysis_id=?
            ORDER BY frame_id ASC, camera_id ASC, created_at ASC, rowid ASC
            """,
            (analysis_id,),
        )
        payloads = []
        for row in rows:
            payload = dict(row)
            payload["invalid"] = bool(payload["invalid"])
            payloads.append(ManualCorrection(**payload))
        return payloads

    def get_correction(
        self,
        analysis_id: str,
        correction_id: str,
    ) -> ManualCorrection | None:
        row = self.database.fetchone(
            """
            SELECT * FROM manual_corrections
            WHERE analysis_id=? AND correction_id=?
            """,
            (analysis_id, correction_id),
        )
        if row is None:
            return None
        payload = dict(row)
        payload["invalid"] = bool(payload["invalid"])
        return ManualCorrection(**payload)

    def get_frame_correction(
        self,
        analysis_id: str,
        frame_id: int,
        camera_id: str,
    ) -> ManualCorrection | None:
        row = self.database.fetchone(
            """
            SELECT * FROM manual_corrections
            WHERE analysis_id=? AND frame_id=? AND camera_id=?
            ORDER BY created_at DESC, rowid DESC
            LIMIT 1
            """,
            (analysis_id, frame_id, camera_id),
        )
        if row is None:
            return None
        payload = dict(row)
        payload["invalid"] = bool(payload["invalid"])
        return ManualCorrection(**payload)

    def delete_correction(
        self,
        analysis_id: str,
        correction_id: str,
    ) -> bool:
        cursor = self.database.execute(
            """
            DELETE FROM manual_corrections
            WHERE analysis_id=? AND correction_id=?
            """,
            (analysis_id, correction_id),
        )
        return cursor.rowcount > 0
