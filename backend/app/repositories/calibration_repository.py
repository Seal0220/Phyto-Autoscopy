from __future__ import annotations

import json

from app.core.exceptions import CalibrationError
from app.database.connection import Database
from app.models.calibration_models import (
    CalibrationBoardProfile,
    CameraIntrinsics,
    IntrinsicRun,
)


class CalibrationRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _model_payload(
        model,
        *,
        exclude: set[str],
    ) -> str:
        try:
            return json.dumps(
                model.model_dump(exclude=exclude),
                ensure_ascii=False,
                allow_nan=False,
            )
        except (TypeError, ValueError) as error:
            raise CalibrationError("校正資料包含無法儲存的數值。") from error

    @staticmethod
    def _load_payload(row, model_type, base: dict):
        try:
            payload = json.loads(row["payload_json"])
            if not isinstance(payload, dict):
                raise TypeError("payload must be an object")
            payload.update(base)
            return model_type.model_validate(payload)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            identifier = next(iter(base.values()), "unknown")
            raise CalibrationError(f"校正資料 {identifier} 的儲存格式無效。") from error

    def create_board(self, board: CalibrationBoardProfile) -> None:
        self.database.execute(
            """
            INSERT INTO calibration_boards(
                board_profile_id, name, board_type, created_at,
                updated_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                board.board_profile_id,
                board.name,
                board.board_type,
                board.created_at,
                board.updated_at,
                self._model_payload(
                    board,
                    exclude={
                        "board_profile_id",
                        "name",
                        "board_type",
                        "created_at",
                        "updated_at",
                    },
                ),
            ),
        )

    def get_board(self, board_profile_id: str) -> CalibrationBoardProfile | None:
        row = self.database.fetchone(
            "SELECT * FROM calibration_boards WHERE board_profile_id=?",
            (board_profile_id,),
        )
        if row is None:
            return None
        return self._load_payload(
            row,
            CalibrationBoardProfile,
            {
                "board_profile_id": row["board_profile_id"],
                "name": row["name"],
                "board_type": row["board_type"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            },
        )

    def list_boards(self) -> list[CalibrationBoardProfile]:
        rows = self.database.fetchall(
            "SELECT * FROM calibration_boards ORDER BY created_at ASC"
        )
        return [
            self._load_payload(
                row,
                CalibrationBoardProfile,
                {
                    "board_profile_id": row["board_profile_id"],
                    "name": row["name"],
                    "board_type": row["board_type"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                },
            )
            for row in rows
        ]

    def _upsert_intrinsics(
        self,
        connection,
        intrinsics: CameraIntrinsics,
    ) -> None:
        payload = self._model_payload(
            intrinsics,
            exclude={
                "camera_id",
                "camera_model",
                "width",
                "height",
                "board_profile_id",
                "source_run_id",
                "status",
                "created_at",
                "updated_at",
            },
        )
        previous = connection.execute(
            "SELECT * FROM camera_intrinsics WHERE camera_id=?",
            (intrinsics.camera_id,),
        ).fetchone()
        if previous is not None:
            connection.execute(
                """
                INSERT INTO camera_intrinsics_history(
                    camera_id, replaced_at, payload_json
                ) VALUES (?, ?, ?)
                """,
                (
                    intrinsics.camera_id,
                    intrinsics.updated_at,
                    json.dumps(
                        dict(previous),
                        ensure_ascii=False,
                        allow_nan=False,
                    ),
                ),
            )
        connection.execute(
            """
            INSERT INTO camera_intrinsics(
                camera_id, camera_model, width, height, board_profile_id,
                source_run_id, status, created_at, updated_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(camera_id) DO UPDATE SET
                camera_model=excluded.camera_model,
                width=excluded.width,
                height=excluded.height,
                board_profile_id=excluded.board_profile_id,
                source_run_id=excluded.source_run_id,
                status=excluded.status,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at,
                payload_json=excluded.payload_json
            """,
            (
                intrinsics.camera_id,
                intrinsics.camera_model,
                intrinsics.width,
                intrinsics.height,
                intrinsics.board_profile_id,
                intrinsics.source_run_id,
                intrinsics.status,
                intrinsics.created_at,
                intrinsics.updated_at,
                payload,
            ),
        )

    def upsert_intrinsics(self, intrinsics: CameraIntrinsics) -> None:
        with self.database.transaction() as connection:
            self._upsert_intrinsics(connection, intrinsics)

    def apply_intrinsics(
        self,
        intrinsics: CameraIntrinsics,
        run: IntrinsicRun,
    ) -> None:
        with self.database.transaction() as connection:
            self._upsert_intrinsics(connection, intrinsics)
            cursor = connection.execute(
                """
                UPDATE calibration_runs
                SET status=?, updated_at=?, payload_json=?, last_error=?
                WHERE run_id=? AND run_type='intrinsic'
                """,
                (
                    run.status,
                    run.updated_at,
                    self._model_payload(
                        run,
                        exclude={
                            "run_id",
                            "camera_id",
                            "board_profile_id",
                            "status",
                            "created_at",
                            "updated_at",
                            "last_error",
                        },
                    ),
                    run.last_error,
                    run.run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise CalibrationError(f"找不到內參校正工作：{run.run_id}")

    def get_intrinsics(self, camera_id: str) -> CameraIntrinsics | None:
        row = self.database.fetchone(
            "SELECT * FROM camera_intrinsics WHERE camera_id=?",
            (camera_id,),
        )
        if row is None:
            return None
        return self._intrinsics_from_row(row)

    def _intrinsics_from_row(self, row) -> CameraIntrinsics:
        return self._load_payload(
            row,
            CameraIntrinsics,
            {
                "camera_id": row["camera_id"],
                "camera_model": row["camera_model"],
                "width": row["width"],
                "height": row["height"],
                "board_profile_id": row["board_profile_id"],
                "source_run_id": row["source_run_id"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            },
        )

    def list_intrinsics(self) -> list[CameraIntrinsics]:
        rows = self.database.fetchall(
            "SELECT * FROM camera_intrinsics ORDER BY camera_id ASC"
        )
        return [self._intrinsics_from_row(row) for row in rows]

    def create_intrinsic_run(self, run: IntrinsicRun) -> None:
        self.database.execute(
            """
            INSERT INTO calibration_runs(
                run_id, run_type, camera_id, board_profile_id,
                status, created_at, updated_at, payload_json, last_error
            ) VALUES (?, 'intrinsic', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                run.camera_id,
                run.board_profile_id,
                run.status,
                run.created_at,
                run.updated_at,
                self._model_payload(
                    run,
                    exclude={
                        "run_id",
                        "camera_id",
                        "board_profile_id",
                        "status",
                        "created_at",
                        "updated_at",
                        "last_error",
                    },
                ),
                run.last_error,
            ),
        )

    def update_intrinsic_run(self, run: IntrinsicRun) -> None:
        cursor = self.database.execute(
            """
            UPDATE calibration_runs
            SET status=?, updated_at=?, payload_json=?, last_error=?
            WHERE run_id=? AND run_type='intrinsic'
            """,
            (
                run.status,
                run.updated_at,
                self._model_payload(
                    run,
                    exclude={
                        "run_id",
                        "camera_id",
                        "board_profile_id",
                        "status",
                        "created_at",
                        "updated_at",
                        "last_error",
                    },
                ),
                run.last_error,
                run.run_id,
            ),
        )
        if cursor.rowcount != 1:
            raise CalibrationError(f"找不到內參校正工作：{run.run_id}")

    def get_intrinsic_run(self, run_id: str) -> IntrinsicRun | None:
        row = self.database.fetchone(
            """
            SELECT * FROM calibration_runs
            WHERE run_id=? AND run_type='intrinsic'
            """,
            (run_id,),
        )
        if row is None:
            return None
        return self._load_payload(
            row,
            IntrinsicRun,
            {
                "run_id": row["run_id"],
                "camera_id": row["camera_id"],
                "board_profile_id": row["board_profile_id"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "last_error": row["last_error"],
            },
        )

    def list_intrinsic_runs(
        self,
        camera_id: str,
    ) -> list[IntrinsicRun]:
        rows = self.database.fetchall(
            """
            SELECT * FROM calibration_runs
            WHERE run_type='intrinsic' AND camera_id=?
            ORDER BY created_at DESC
            """,
            (camera_id,),
        )
        return [
            self._load_payload(
                row,
                IntrinsicRun,
                {
                    "run_id": row["run_id"],
                    "camera_id": row["camera_id"],
                    "board_profile_id": row["board_profile_id"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "last_error": row["last_error"],
                },
            )
            for row in rows
        ]

    def delete_intrinsic_run(self, run_id: str) -> None:
        cursor = self.database.execute(
            "DELETE FROM calibration_runs WHERE run_id=? AND run_type='intrinsic'",
            (run_id,),
        )
        if cursor.rowcount != 1:
            raise CalibrationError(f"找不到內參校正工作：{run_id}")
