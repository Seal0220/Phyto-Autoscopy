from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from app.calibration.board_detection import BoardDetectionResult, detect_board
from app.core.exceptions import CalibrationError
from app.models.calibration_models import CalibrationBoardProfile


class CalibrationCaptureService:
    def __init__(
        self,
        settings: object,
        camera_manager: object,
        storage_service: object,
    ) -> None:
        self.settings = settings
        self.camera_manager = camera_manager
        self.storage_service = storage_service
        self._save_lock = RLock()

    @property
    def root(self) -> Path:
        return self.settings.paths.calibration_dir

    def analyze_camera(
        self,
        camera_id: str,
        board: CalibrationBoardProfile,
        *,
        include_preview: bool = False,
    ) -> tuple[object, BoardDetectionResult]:
        try:
            frame = self.camera_manager.capture(camera_id)
            return frame, detect_board(
                frame.data,
                board,
                include_preview=include_preview,
            )
        except CalibrationError:
            raise
        except Exception as error:
            raise CalibrationError(
                f"相機 {camera_id} 校正板偵測失敗：{error}。請重新連線後再試。"
            ) from error

    def save_intrinsic_frame(
        self,
        run_id: str,
        sample_id: str,
        frame: object,
        preview_jpeg: bytes | None,
    ) -> tuple[str, str | None]:
        directory = self.root / "intrinsics" / "runs" / run_id
        image_path = directory / "captures" / f"{sample_id}.jpg"
        preview_path = directory / "previews" / f"{sample_id}.jpg"
        with self._save_lock:
            self.storage_service.save_bytes(image_path, frame.data)
            if preview_jpeg is not None:
                self.storage_service.save_bytes(preview_path, preview_jpeg)
        return image_path.as_posix(), (
            preview_path.as_posix() if preview_jpeg is not None else None
        )

    def synchronized_capture(
        self,
        profile_id: str,
        camera_ids: list[str],
        board: CalibrationBoardProfile,
        observation_id: str,
    ) -> tuple[dict[str, object], dict[str, BoardDetectionResult], dict[str, str]]:
        if not camera_ids:
            raise CalibrationError("外參擷取至少需要一顆相機。")
        frames: dict[str, object] = {}
        with ThreadPoolExecutor(max_workers=len(camera_ids)) as executor:
            futures = {
                executor.submit(self.camera_manager.capture, camera_id): camera_id
                for camera_id in camera_ids
            }
            for future in as_completed(futures):
                camera_id = futures[future]
                try:
                    frames[camera_id] = future.result()
                except Exception as error:
                    raise CalibrationError(
                        f"外參同步擷取時無法取得相機 {camera_id} 影像：{error}。"
                    ) from error
        detections: dict[str, BoardDetectionResult] = {}
        for camera_id, frame in frames.items():
            try:
                detections[camera_id] = detect_board(
                    frame.data,
                    board,
                    include_preview=True,
                )
            except Exception as error:
                raise CalibrationError(
                    f"外參擷取的相機 {camera_id} 校正板偵測失敗：{error}。"
                ) from error
        directory = self.root / "extrinsics" / profile_id / "captures" / observation_id
        image_paths: dict[str, str] = {}
        with self._save_lock:
            for camera_id, frame in frames.items():
                image_path = directory / f"{camera_id}.jpg"
                self.storage_service.save_bytes(image_path, frame.data)
                image_paths[camera_id] = image_path.as_posix()
                preview = detections[camera_id].preview_jpeg
                if preview is not None:
                    self.storage_service.save_bytes(
                        directory / f"{camera_id}_detected.jpg",
                        preview,
                    )
        return frames, detections, image_paths

    @staticmethod
    def timestamp(frame: object | None = None) -> str:
        captured_at = getattr(frame, "timestamp", None)
        if not isinstance(captured_at, datetime):
            captured_at = datetime.now(timezone.utc)
        return captured_at.astimezone(timezone.utc).isoformat()
