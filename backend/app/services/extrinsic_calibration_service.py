from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from uuid import uuid4

from app.analysis.run_metadata import next_dated_identifier, utc_now_iso
from app.calibration.extrinsic_solver import solve_extrinsic_profile
from app.core.exceptions import CalibrationError
from app.models.calibration_models import (
    CalibrationObservation,
    ExtrinsicCaptureRequest,
    ExtrinsicProfile,
    ExtrinsicProfileCopyRequest,
    ExtrinsicProfileCreateRequest,
    ExtrinsicProfilePatchRequest,
    QuickRelocationRequest,
)


class ExtrinsicCalibrationService:
    def __init__(
        self,
        settings: object,
        repository: object,
        capture_service: object,
        lock_service: object,
        storage_service: object,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.capture_service = capture_service
        self.lock_service = lock_service
        self.storage_service = storage_service

    @property
    def root(self) -> Path:
        return self.settings.paths.calibration_dir / "extrinsics"

    def list_profiles(self) -> list[ExtrinsicProfile]:
        return self.repository.list_extrinsic_profiles()

    def get_profile(self, profile_id: str) -> ExtrinsicProfile:
        profile = self.repository.get_extrinsic_profile(profile_id)
        if profile is None:
            raise CalibrationError(f"找不到外參校正檔：{profile_id}")
        return profile

    def get_active(self) -> ExtrinsicProfile | None:
        return self.repository.get_active_extrinsic_profile()

    def list_observations(
        self,
        profile_id: str,
    ) -> list[CalibrationObservation]:
        self.get_profile(profile_id)
        return self.repository.list_observations(profile_id)

    def _write_profile(
        self,
        profile: ExtrinsicProfile,
        observations: list[CalibrationObservation] | None = None,
    ) -> None:
        self.storage_service.write_extrinsic_profile(profile, observations)

    def _write_index(
        self,
        profiles: list[ExtrinsicProfile] | None = None,
    ) -> None:
        self.storage_service.write_index(profiles=profiles)

    @staticmethod
    def _replace_profile(
        profiles: list[ExtrinsicProfile],
        replacement: ExtrinsicProfile,
    ) -> list[ExtrinsicProfile]:
        return [
            replacement if item.profile_id == replacement.profile_id else item
            for item in profiles
        ]

    def _persist_profile(
        self,
        previous: ExtrinsicProfile,
        updated: ExtrinsicProfile,
    ) -> None:
        observations = self.repository.list_observations(previous.profile_id)
        previous_profiles = self.list_profiles()
        next_profiles = self._replace_profile(previous_profiles, updated)
        try:
            self._write_profile(updated, observations)
            self._write_index(next_profiles)
            self.repository.update_extrinsic_profile(updated)
        except Exception:
            self._write_profile(previous, observations)
            self._write_index(previous_profiles)
            raise

    def create(
        self,
        request: ExtrinsicProfileCreateRequest,
        owner: str,
    ) -> ExtrinsicProfile:
        self.lock_service.ensure_owner(owner)
        if self.repository.get_board(request.board_profile_id) is None:
            raise CalibrationError(f"找不到校正板：{request.board_profile_id}")
        profile_id = next_dated_identifier(self.root, "extrinsic")
        now = utc_now_iso()
        profile = ExtrinsicProfile(
            profile_id=profile_id,
            name=request.name,
            board_profile_id=request.board_profile_id,
            camera_ids=request.camera_ids,
            cameras=request.cameras,
            motion_model=request.motion_model,
            world_alignment=request.world_alignment,
            notes=request.notes,
            created_at=now,
            updated_at=now,
        )
        directory = self.root / profile_id
        previous_profiles = self.list_profiles()
        directory.mkdir(parents=True, exist_ok=False)
        try:
            self._write_profile(profile, [])
            self._write_index([profile, *previous_profiles])
            self.repository.create_extrinsic_profile(profile)
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            self._write_index(previous_profiles)
            raise
        return profile

    def update(
        self,
        profile_id: str,
        request: ExtrinsicProfilePatchRequest,
        owner: str,
    ) -> ExtrinsicProfile:
        self.lock_service.ensure_owner(owner)
        profile = self.get_profile(profile_id)
        if profile.is_active:
            raise CalibrationError("啟用中的外參校正檔不可直接修改，請先複製成新校正檔。")
        updates = request.model_dump(exclude_none=True)
        if "cameras" in updates:
            configured_ids = [item.camera_id for item in request.cameras or []]
            if set(configured_ids) != set(profile.camera_ids) or len(configured_ids) != len(set(configured_ids)):
                raise CalibrationError("相機位置資料必須且只能涵蓋此校正檔的參與相機。")
        updates.update({
            "status": "draft",
            "quality_status": None,
            "quality": {},
            "updated_at": utc_now_iso(),
            "last_error": None,
        })
        updated = profile.model_copy(update=updates, deep=True)
        self._persist_profile(profile, updated)
        return updated

    def copy(
        self,
        profile_id: str,
        request: ExtrinsicProfileCopyRequest,
        owner: str,
    ) -> ExtrinsicProfile:
        self.lock_service.ensure_owner(owner)
        source = self.get_profile(profile_id)
        create_request = ExtrinsicProfileCreateRequest(
            name=request.name,
            board_profile_id=source.board_profile_id,
            camera_ids=source.camera_ids,
            cameras=[
                camera.model_copy(
                    update={
                        "transform_rig_from_camera": None,
                        "transform_world_from_camera": None,
                    },
                    deep=True,
                )
                for camera in source.cameras
            ],
            motion_model=source.motion_model,
            world_alignment=source.world_alignment.model_copy(
                update={"transform_world_from_rig": None},
                deep=True,
            ),
            notes=source.notes,
        )
        return self.create(create_request, owner)

    def capture(
        self,
        profile_id: str,
        request: ExtrinsicCaptureRequest,
        owner: str,
    ) -> CalibrationObservation:
        self.lock_service.ensure_owner(owner)
        profile = self.get_profile(profile_id)
        if profile.is_active or profile.status == "archived":
            raise CalibrationError("目前外參校正檔狀態不可新增觀測。")
        camera_ids = request.camera_ids or profile.camera_ids
        if len(camera_ids) != len(set(camera_ids)) or not set(camera_ids).issubset(profile.camera_ids):
            raise CalibrationError("外參擷取的相機集合不屬於此校正檔。")
        board = self.repository.get_board(profile.board_profile_id)
        if board is None:
            raise CalibrationError(f"找不到校正板：{profile.board_profile_id}")
        observation_id = f"observation_{profile.observation_count + 1:04d}"
        frames, detections, image_paths = self.capture_service.synchronized_capture(
            profile_id,
            list(camera_ids),
            board,
            observation_id,
        )
        valid_cameras = [
            camera_id
            for camera_id, detection in detections.items()
            if detection.board_detected
        ]
        accepted = bool(valid_cameras)
        rejection_reason = None
        if not accepted:
            rejection_reason = "所有參與相機都未偵測到足夠的校正板角點。"
        first_frame = next(iter(frames.values()), None)
        observation = CalibrationObservation(
            observation_id=observation_id,
            profile_id=profile_id,
            captured_at=self.capture_service.timestamp(first_frame),
            motor_angle_deg=request.motor_angle_deg,
            arm_height_mm=(
                request.arm_height_mm
                if request.arm_height_mm is not None
                else profile.motion_model.arm_height_mm
            ),
            camera_images=image_paths,
            detections={
                camera_id: detection.to_dict(include_points=True)
                for camera_id, detection in detections.items()
            },
            accepted=accepted,
            rejection_reason=rejection_reason,
        )
        updated = profile.model_copy(
            update={
                "status": "draft",
                "observation_count": profile.observation_count + 1,
                "updated_at": utc_now_iso(),
                "last_error": rejection_reason,
            },
            deep=True,
        )
        previous_observations = self.repository.list_observations(profile_id)
        previous_profiles = self.list_profiles()
        next_profiles = self._replace_profile(previous_profiles, updated)
        try:
            self._write_profile(
                updated,
                [*previous_observations, observation],
            )
            self._write_index(next_profiles)
            self.repository.create_observation_and_update_profile(
                observation,
                updated,
            )
        except Exception:
            self._write_profile(profile, previous_observations)
            self._write_index(previous_profiles)
            shutil.rmtree(
                self.root / profile_id / "captures" / observation_id,
                ignore_errors=True,
            )
            raise
        return observation

    def solve(
        self,
        profile_id: str,
        owner: str,
    ) -> ExtrinsicProfile:
        self.lock_service.ensure_owner(owner)
        profile = self.get_profile(profile_id)
        if profile.is_active or profile.status == "archived":
            raise CalibrationError("目前外參校正檔狀態不可重新計算。")
        validating = profile.model_copy(
            update={
                "status": "validating",
                "updated_at": utc_now_iso(),
                "last_error": None,
            },
            deep=True,
        )
        self._persist_profile(profile, validating)
        observations = self.repository.list_observations(profile_id)
        intrinsics = {
            camera_id: self.repository.get_intrinsics(camera_id)
            for camera_id in profile.camera_ids
        }
        try:
            result = solve_extrinsic_profile(
                validating,
                observations,
                {
                    key: value
                    for key, value in intrinsics.items()
                    if value is not None
                },
            )
        except Exception as error:
            detail = str(error) or "外參求解未收斂。"
            failed = validating.model_copy(
                update={
                    "status": "invalid",
                    "quality_status": "failed",
                    "updated_at": utc_now_iso(),
                    "last_error": detail,
                },
                deep=True,
            )
            self._persist_profile(validating, failed)
            raise CalibrationError(
                f"外參校正檔 {profile.name} 計算失敗：{detail} "
                "請補拍共同觀測後重試。"
            ) from error
        try:
            self.lock_service.ensure_owner(owner)
        except CalibrationError as error:
            cancelled = validating.model_copy(
                update={
                    "status": "draft",
                    "quality_status": None,
                    "quality": {},
                    "updated_at": utc_now_iso(),
                    "last_error": "校正操作鎖已釋放，外參計算結果未儲存。",
                },
                deep=True,
            )
            self._persist_profile(validating, cancelled)
            raise error
        solved = validating.model_copy(
            update={
                **result,
                "status": "validating",
                "updated_at": utc_now_iso(),
                "last_error": None,
            },
            deep=True,
        )
        self._persist_profile(validating, solved)
        return solved

    def validate(
        self,
        profile_id: str,
        owner: str,
    ) -> ExtrinsicProfile:
        self.lock_service.ensure_owner(owner)
        profile = self.get_profile(profile_id)
        if profile.status != "validating" or profile.quality_status is None:
            raise CalibrationError("請先完成外參計算，再執行品質驗證。")
        valid = profile.quality_status in {"excellent", "acceptable"}
        updated = profile.model_copy(
            update={
                "status": "valid" if valid else "invalid",
                "updated_at": utc_now_iso(),
                "last_error": None if valid else "外參品質未達啟用門檻。",
            },
            deep=True,
        )
        self._persist_profile(profile, updated)
        return updated

    def activate(
        self,
        profile_id: str,
        owner: str,
    ) -> ExtrinsicProfile:
        self.lock_service.ensure_owner(owner)
        previous_profiles = self.list_profiles()
        updated_at = utc_now_iso()
        next_profiles = [
            item.model_copy(
                update={
                    "is_active": item.profile_id == profile_id,
                    "status": (
                        "active"
                        if item.profile_id == profile_id
                        else "valid" if item.is_active else item.status
                    ),
                    "updated_at": (
                        updated_at
                        if item.profile_id == profile_id or item.is_active
                        else item.updated_at
                    ),
                },
                deep=True,
            )
            for item in previous_profiles
        ]
        try:
            for item in next_profiles:
                self._write_profile(item)
            self._write_index(next_profiles)
            self.repository.activate_extrinsic_profile(profile_id, updated_at)
        except Exception:
            for item in previous_profiles:
                self._write_profile(item)
            self._write_index(previous_profiles)
            raise
        return self.get_profile(profile_id)

    def archive(
        self,
        profile_id: str,
        owner: str,
    ) -> ExtrinsicProfile:
        self.lock_service.ensure_owner(owner)
        profile = self.get_profile(profile_id)
        if profile.is_active:
            raise CalibrationError("目前啟用的外參校正檔不可封存。")
        archived = profile.model_copy(
            update={
                "status": "archived",
                "updated_at": utc_now_iso(),
                "last_error": None,
            },
            deep=True,
        )
        self._persist_profile(profile, archived)
        return archived

    def quick_relocation(
        self,
        request: QuickRelocationRequest,
        owner: str,
    ) -> ExtrinsicProfile:
        source = self.get_profile(request.source_profile_id)
        copied = self.copy(
            source.profile_id,
            ExtrinsicProfileCopyRequest(name=request.name),
            owner,
        )
        motion = copied.motion_model
        if request.arm_height_mm is not None:
            motion = motion.model_copy(
                update={"arm_height_mm": request.arm_height_mm},
                deep=True,
            )
        notes = "快速外參重定位：" + "、".join(request.changed_items)
        updated = copied.model_copy(
            update={
                "motion_model": motion,
                "notes": f"{copied.notes}\n{notes}".strip(),
                "updated_at": utc_now_iso(),
            },
            deep=True,
        )
        self._persist_profile(copied, updated)
        return updated

    def export(self, profile_id: str) -> Path:
        profile = self.get_profile(profile_id)
        directory = self.root / profile_id
        self._write_profile(profile)
        export_path = directory / f"{profile_id}.zip"
        temporary = export_path.with_suffix(".zip.tmp")
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name in ("profile.json", "observations.json", "quality.json"):
                    path = directory / name
                    if path.is_file():
                        archive.write(path, arcname=name)
            temporary.replace(export_path)
        finally:
            temporary.unlink(missing_ok=True)
        return export_path

    def delete(
        self,
        profile_id: str,
        owner: str,
    ) -> None:
        self.lock_service.ensure_owner(owner)
        directory = self.root / profile_id
        tombstone = directory.with_name(
            f".{profile_id}.{uuid4().hex}.deleted"
        )
        previous_profiles = self.list_profiles()
        next_profiles = [
            item for item in previous_profiles if item.profile_id != profile_id
        ]
        if directory.exists():
            directory.replace(tombstone)
        try:
            self._write_index(next_profiles)
            self.repository.delete_extrinsic_profile(profile_id)
        except Exception:
            if tombstone.exists():
                tombstone.replace(directory)
            self._write_index(previous_profiles)
            raise
        shutil.rmtree(tombstone, ignore_errors=True)
