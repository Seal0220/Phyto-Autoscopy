from __future__ import annotations

import json

from app.core.exceptions import CalibrationError
from app.database.connection import Database
from app.models.calibration_models import CalibrationProfile


class CalibrationRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _profile_from_row(row) -> CalibrationProfile:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError) as error:
            raise CalibrationError(
                f"相機校正設定檔 {row['calibration_id']} 的儲存資料已損毀。"
            ) from error
        if not isinstance(payload, dict):
            raise CalibrationError(
                f"相機校正設定檔 {row['calibration_id']} 的儲存格式無效。"
            )
        payload.update(
            {
                "calibration_id": row["calibration_id"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "status": row["status"],
                "valid": bool(row["valid"]),
                "output_path": row["output_path"],
                "last_error": row["last_error"],
            }
        )
        try:
            return CalibrationProfile(**payload)
        except (TypeError, ValueError) as error:
            raise CalibrationError(
                f"相機校正設定檔 {row['calibration_id']} 的儲存格式無效。"
            ) from error

    @staticmethod
    def _serialized_payload(profile: CalibrationProfile) -> str:
        payload = profile.model_dump(exclude={
            "calibration_id",
            "created_at",
            "updated_at",
            "status",
            "valid",
            "output_path",
            "last_error",
        })
        try:
            return json.dumps(payload, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise CalibrationError("相機校正設定檔包含無法儲存的數值。") from error

    def create(self, profile: CalibrationProfile) -> None:
        self.database.execute(
            """
            INSERT INTO calibration_profiles(
                calibration_id, created_at, updated_at, status, valid,
                output_path, payload_json, last_error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile.calibration_id,
                profile.created_at,
                profile.updated_at,
                profile.status,
                int(profile.valid),
                profile.output_path,
                self._serialized_payload(profile),
                profile.last_error,
            ),
        )

    def update(self, profile: CalibrationProfile) -> None:
        cursor = self.database.execute(
            """
            UPDATE calibration_profiles
            SET updated_at=?, status=?, valid=?, output_path=?,
                payload_json=?, last_error=?
            WHERE calibration_id=?
            """,
            (
                profile.updated_at,
                profile.status,
                int(profile.valid),
                profile.output_path,
                self._serialized_payload(profile),
                profile.last_error,
                profile.calibration_id,
            ),
        )
        if cursor.rowcount != 1:
            raise CalibrationError(
                f"相機校正設定檔不存在：{profile.calibration_id}"
            )

    def get(self, calibration_id: str) -> CalibrationProfile | None:
        row = self.database.fetchone(
            "SELECT * FROM calibration_profiles WHERE calibration_id=?",
            (calibration_id,),
        )
        return self._profile_from_row(row) if row else None

    def list(self) -> list[CalibrationProfile]:
        rows = self.database.fetchall(
            "SELECT * FROM calibration_profiles ORDER BY created_at DESC"
        )
        return [self._profile_from_row(row) for row in rows]

    def delete(self, calibration_id: str) -> None:
        cursor = self.database.execute(
            "DELETE FROM calibration_profiles WHERE calibration_id=?",
            (calibration_id,),
        )
        if cursor.rowcount != 1:
            raise CalibrationError(f"相機校正設定檔不存在：{calibration_id}")
