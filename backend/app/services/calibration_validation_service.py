from __future__ import annotations

from app.core.exceptions import CalibrationError


class CalibrationValidationService:
    def __init__(
        self,
        settings: object,
        repository: object,
    ) -> None:
        self.settings = settings
        self.repository = repository

    def intrinsics_status(self) -> list[object]:
        results = []
        for intrinsics in self.repository.list_intrinsics():
            camera = self.settings.cameras.get(intrinsics.camera_id)
            reasons = list(intrinsics.invalidation_reasons)
            if camera is None:
                reasons.append("相機設定已不存在。")
            status = "potentially_invalid" if reasons else intrinsics.status
            quality = dict(intrinsics.quality)
            if camera is not None:
                quality["configured_resolution"] = [camera.width, camera.height]
                quality["resolution_requires_scaling"] = (
                    (intrinsics.width, intrinsics.height)
                    != (camera.width, camera.height)
                )
            results.append(intrinsics.model_copy(
                update={
                    "status": status,
                    "invalidation_reasons": list(dict.fromkeys(reasons)),
                    "quality": quality,
                },
                deep=True,
            ))
        return results

    def require_valid_intrinsics(
        self,
        camera_ids: list[str],
    ) -> dict[str, object]:
        available = {item.camera_id: item for item in self.intrinsics_status()}
        missing = [
            camera_id
            for camera_id in camera_ids
            if camera_id not in available or available[camera_id].status != "valid"
        ]
        if missing:
            raise CalibrationError(
                f"以下相機缺少可用的有效內參：{', '.join(missing)}。"
                "請先完成各相機內參校正。"
            )
        return {camera_id: available[camera_id] for camera_id in camera_ids}
