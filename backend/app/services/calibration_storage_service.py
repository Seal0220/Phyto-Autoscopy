from __future__ import annotations

import json
from pathlib import Path
from threading import RLock

from app.analysis.export.json_export import write_json_atomic
from app.core.exceptions import CalibrationError
from app.models.calibration_models import (
    CalibrationBoardProfile,
    CameraIntrinsics,
    IntrinsicRun,
)


class CalibrationStorageService:
    """Maintain recoverable JSON projections of canonical SQLite calibration data."""

    def __init__(
        self,
        settings: object,
        repository: object,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self._lock = RLock()
        self._last_error: str | None = None
        self.ensure_layout()

    @property
    def root(self) -> Path:
        return self.settings.paths.calibration_dir

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    @property
    def synchronized(self) -> bool:
        return self.last_error is None

    def ensure_layout(self) -> None:
        for directory in (
            self.root / "boards",
            self.root / "intrinsics" / "runs",
            self.root / "intrinsics" / "previews",
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def _write(
        self,
        path: Path,
        payload: object,
        label: str,
    ) -> None:
        try:
            write_json_atomic(path, payload)
            parsed = json.loads(path.read_text(encoding="utf-8"))
            if parsed is None:
                raise ValueError("JSON root must not be null")
        except (OSError, UnicodeError, TypeError, ValueError) as error:
            message = (
                f"{label}無法寫入 {path}：{error}。"
                "既有校正資料仍保存在 SQLite；"
                "請確認儲存空間與檔案權限後執行重新同步。"
            )
            self._last_error = message
            raise CalibrationError(message) from error

    def write_board(self, board: CalibrationBoardProfile) -> None:
        with self._lock:
            self._write(
                self.root / "boards" / f"{board.board_profile_id}.json",
                board.model_dump(mode="json"),
                f"校正板 {board.name}",
            )

    def write_intrinsics(self, intrinsics: CameraIntrinsics) -> None:
        with self._lock:
            self._write(
                self.root / "intrinsics" / f"{intrinsics.camera_id}.json",
                intrinsics.model_dump(mode="json"),
                f"相機 {intrinsics.camera_id} 內參",
            )

    def write_intrinsic_run(self, run: IntrinsicRun) -> None:
        with self._lock:
            self._write(
                self.root / "intrinsics" / "runs" / run.run_id / "run.json",
                run.model_dump(mode="json"),
                f"內參工作 {run.run_id}",
            )

    def write_index(
        self,
        intrinsics: list[CameraIntrinsics] | None = None,
    ) -> None:
        with self._lock:
            intrinsics = intrinsics if intrinsics is not None else (
                self.repository.list_intrinsics()
            )
            self._write(
                self.root / "index.json",
                {
                    "intrinsics": {
                        item.camera_id: item.updated_at
                        for item in intrinsics
                    },
                },
                "校正索引",
            )

    def reconcile(self) -> None:
        with self._lock:
            self.ensure_layout()
            for board in self.repository.list_boards():
                self.write_board(board)
            for intrinsics in self.repository.list_intrinsics():
                self.write_intrinsics(intrinsics)
            for camera_id in self.settings.cameras:
                for run in self.repository.list_intrinsic_runs(camera_id):
                    self.write_intrinsic_run(run)
            self.write_index(
                intrinsics=self.repository.list_intrinsics(),
            )
            self._last_error = None
