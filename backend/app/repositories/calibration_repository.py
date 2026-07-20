from __future__ import annotations

import json

from app.core.exceptions import CalibrationError
from app.database.connection import Database
from app.models.calibration_models import (
    CalibrationBoardProfile,
    CalibrationObservation,
    CameraIntrinsics,
    ExtrinsicProfile,
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
                run_id, run_type, camera_id, profile_id, board_profile_id,
                status, created_at, updated_at, payload_json, last_error
            ) VALUES (?, 'intrinsic', ?, NULL, ?, ?, ?, ?, ?, ?)
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

    def create_extrinsic_profile(self, profile: ExtrinsicProfile) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO extrinsic_profiles(
                    profile_id, name, status, is_active, board_profile_id,
                    created_at, updated_at, payload_json, last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile.profile_id,
                    profile.name,
                    profile.status,
                    int(profile.is_active),
                    profile.board_profile_id,
                    profile.created_at,
                    profile.updated_at,
                    self._model_payload(
                        profile,
                        exclude={
                            "profile_id",
                            "name",
                            "status",
                            "is_active",
                            "board_profile_id",
                            "created_at",
                            "updated_at",
                            "last_error",
                        },
                    ),
                    profile.last_error,
                ),
            )
            self._replace_extrinsic_cameras(connection, profile)

    @staticmethod
    def _replace_extrinsic_cameras(connection, profile: ExtrinsicProfile) -> None:
        connection.execute(
            "DELETE FROM extrinsic_profile_cameras WHERE profile_id=?",
            (profile.profile_id,),
        )
        for camera in profile.cameras:
            connection.execute(
                """
                INSERT INTO extrinsic_profile_cameras(
                    profile_id, camera_id, height_mm, position_json,
                    transform_json, mount_description
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    profile.profile_id,
                    camera.camera_id,
                    camera.height_mm,
                    json.dumps(
                        camera.model_dump(exclude={
                            "transform_rig_from_camera",
                            "transform_world_from_camera",
                            "mount_description",
                        }),
                        ensure_ascii=False,
                        allow_nan=False,
                    ),
                    json.dumps(
                        {
                            "transform_rig_from_camera": camera.transform_rig_from_camera,
                            "transform_world_from_camera": camera.transform_world_from_camera,
                        },
                        ensure_ascii=False,
                        allow_nan=False,
                    ),
                    camera.mount_description,
                ),
            )

    def update_extrinsic_profile(self, profile: ExtrinsicProfile) -> None:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE extrinsic_profiles
                SET name=?, status=?, is_active=?, board_profile_id=?,
                    updated_at=?, payload_json=?, last_error=?
                WHERE profile_id=?
                """,
                (
                    profile.name,
                    profile.status,
                    int(profile.is_active),
                    profile.board_profile_id,
                    profile.updated_at,
                    self._model_payload(
                        profile,
                        exclude={
                            "profile_id",
                            "name",
                            "status",
                            "is_active",
                            "board_profile_id",
                            "created_at",
                            "updated_at",
                            "last_error",
                        },
                    ),
                    profile.last_error,
                    profile.profile_id,
                ),
            )
            if cursor.rowcount != 1:
                raise CalibrationError(f"找不到外參校正檔：{profile.profile_id}")
            self._replace_extrinsic_cameras(connection, profile)

    def _extrinsic_from_row(self, row) -> ExtrinsicProfile:
        return self._load_payload(
            row,
            ExtrinsicProfile,
            {
                "profile_id": row["profile_id"],
                "name": row["name"],
                "status": row["status"],
                "is_active": bool(row["is_active"]),
                "board_profile_id": row["board_profile_id"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "last_error": row["last_error"],
            },
        )

    def get_extrinsic_profile(self, profile_id: str) -> ExtrinsicProfile | None:
        row = self.database.fetchone(
            "SELECT * FROM extrinsic_profiles WHERE profile_id=?",
            (profile_id,),
        )
        return self._extrinsic_from_row(row) if row else None

    def list_extrinsic_profiles(self) -> list[ExtrinsicProfile]:
        rows = self.database.fetchall(
            "SELECT * FROM extrinsic_profiles ORDER BY created_at DESC"
        )
        return [self._extrinsic_from_row(row) for row in rows]

    def get_active_extrinsic_profile(self) -> ExtrinsicProfile | None:
        row = self.database.fetchone(
            "SELECT * FROM extrinsic_profiles WHERE is_active=1"
        )
        return self._extrinsic_from_row(row) if row else None

    def activate_extrinsic_profile(
        self,
        profile_id: str,
        updated_at: str,
    ) -> None:
        with self.database.transaction() as connection:
            target = connection.execute(
                "SELECT status FROM extrinsic_profiles WHERE profile_id=?",
                (profile_id,),
            ).fetchone()
            if target is None:
                raise CalibrationError(f"找不到外參校正檔：{profile_id}")
            if target["status"] not in {"valid", "active"}:
                raise CalibrationError("只有通過品質驗證的外參校正檔可以啟用。")
            connection.execute(
                """
                UPDATE extrinsic_profiles
                SET is_active=0, status='valid', updated_at=?
                WHERE is_active=1 AND profile_id<>?
                """,
                (updated_at, profile_id),
            )
            connection.execute(
                """
                UPDATE extrinsic_profiles
                SET is_active=1, status='active', updated_at=?
                WHERE profile_id=?
                """,
                (updated_at, profile_id),
            )

    def delete_extrinsic_profile(self, profile_id: str) -> None:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT is_active FROM extrinsic_profiles WHERE profile_id=?",
                (profile_id,),
            ).fetchone()
            if row is None:
                raise CalibrationError(f"找不到外參校正檔：{profile_id}")
            if bool(row["is_active"]):
                raise CalibrationError("目前啟用的外參校正檔不可直接刪除。")
            connection.execute(
                "DELETE FROM extrinsic_profiles WHERE profile_id=?",
                (profile_id,),
            )

    def create_observation(self, observation: CalibrationObservation) -> None:
        self.database.execute(
            """
            INSERT INTO calibration_observations(
                observation_id, profile_id, captured_at, motor_angle_deg,
                arm_height_mm, accepted, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation.observation_id,
                observation.profile_id,
                observation.captured_at,
                observation.motor_angle_deg,
                observation.arm_height_mm,
                int(observation.accepted),
                self._model_payload(
                    observation,
                    exclude={
                        "observation_id",
                        "profile_id",
                        "captured_at",
                        "motor_angle_deg",
                        "arm_height_mm",
                        "accepted",
                    },
                ),
            ),
        )

    def create_observation_and_update_profile(
        self,
        observation: CalibrationObservation,
        profile: ExtrinsicProfile,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO calibration_observations(
                    observation_id, profile_id, captured_at, motor_angle_deg,
                    arm_height_mm, accepted, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation.observation_id,
                    observation.profile_id,
                    observation.captured_at,
                    observation.motor_angle_deg,
                    observation.arm_height_mm,
                    int(observation.accepted),
                    self._model_payload(
                        observation,
                        exclude={
                            "observation_id",
                            "profile_id",
                            "captured_at",
                            "motor_angle_deg",
                            "arm_height_mm",
                            "accepted",
                        },
                    ),
                ),
            )
            cursor = connection.execute(
                """
                UPDATE extrinsic_profiles
                SET name=?, status=?, is_active=?, board_profile_id=?,
                    updated_at=?, payload_json=?, last_error=?
                WHERE profile_id=?
                """,
                (
                    profile.name,
                    profile.status,
                    int(profile.is_active),
                    profile.board_profile_id,
                    profile.updated_at,
                    self._model_payload(
                        profile,
                        exclude={
                            "profile_id",
                            "name",
                            "status",
                            "is_active",
                            "board_profile_id",
                            "created_at",
                            "updated_at",
                            "last_error",
                        },
                    ),
                    profile.last_error,
                    profile.profile_id,
                ),
            )
            if cursor.rowcount != 1:
                raise CalibrationError(
                    f"找不到外參校正檔：{profile.profile_id}"
                )
            self._replace_extrinsic_cameras(connection, profile)

    def list_observations(self, profile_id: str) -> list[CalibrationObservation]:
        rows = self.database.fetchall(
            """
            SELECT * FROM calibration_observations
            WHERE profile_id=? ORDER BY captured_at ASC
            """,
            (profile_id,),
        )
        return [
            self._load_payload(
                row,
                CalibrationObservation,
                {
                    "observation_id": row["observation_id"],
                    "profile_id": row["profile_id"],
                    "captured_at": row["captured_at"],
                    "motor_angle_deg": row["motor_angle_deg"],
                    "arm_height_mm": row["arm_height_mm"],
                    "accepted": bool(row["accepted"]),
                },
            )
            for row in rows
        ]
