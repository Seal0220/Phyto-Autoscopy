from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np

from app.analysis.export.json_export import write_json_atomic
from app.analysis.reconstruction.constrained_bundle_adjustment import (
    refine_sparse_camera_poses,
)
from app.analysis.reconstruction.dataset_adapter import (
    PreparedRoundDataset,
    update_round_dataset_pose_metadata,
)


class SparseInitializationError(RuntimeError):
    pass


def _device(pycolmap: object, requested: str):
    device_type = getattr(pycolmap, "Device")
    requested_device = getattr(device_type, requested.lower(), None)
    if requested_device is not None:
        return requested_device
    automatic = getattr(device_type, "auto", None)
    if automatic is None:
        raise SparseInitializationError("PyCOLMAP 不支援自動選擇運算裝置。")
    return automatic


def initialize_sparse_geometry(
    dataset: PreparedRoundDataset,
    *,
    requested_device: str,
    use_constrained_bundle_adjustment: bool = True,
    progress_callback: Callable[[str, float], None] | None = None,
    cancel_check: Callable[[], None] | None = None,
) -> dict:
    try:
        import pycolmap
    except ImportError as error:
        raise SparseInitializationError(
            "尚未安裝 PyCOLMAP，無法建立稀疏初始化點。"
        ) from error

    def progress(stage: str, value: float) -> None:
        if cancel_check is not None:
            cancel_check()
        if progress_callback is not None:
            progress_callback(stage, value)

    database_path = dataset.database_path
    if database_path.exists():
        database_path.unlink()
    camera_ids = {
        "top": 1,
        "side": 2,
        "rotating": 3,
    }
    camera_by_id = {}
    representative_by_camera = {}
    for view in dataset.views:
        representative_by_camera.setdefault(view.camera_id, view)
    for camera_id, view in representative_by_camera.items():
        matrix = view.camera_matrix
        camera_by_id[camera_id] = pycolmap.Camera(
            camera_id=camera_ids[camera_id],
            model=pycolmap.CameraModelId.PINHOLE,
            width=view.image_width,
            height=view.image_height,
            params=np.asarray(
                [
                    matrix[0, 0],
                    matrix[1, 1],
                    matrix[0, 2],
                    matrix[1, 2],
                ],
                dtype=np.float64,
            ),
            has_prior_focal_length=True,
        )

    progress("extracting_features", 0.02)
    initial = pycolmap.Reconstruction()
    with pycolmap.Database.open(database_path) as database:
        for camera in camera_by_id.values():
            database.write_camera(camera, use_camera_id=True)
            initial.add_camera_with_trivial_rig(camera)
        for image_id, view in enumerate(dataset.views, start=1):
            image = pycolmap.Image(
                name=view.image_name,
                camera_id=camera_ids[view.camera_id],
                image_id=image_id,
            )
            database.write_image(image, use_image_id=True)
            initial.add_image_with_trivial_frame(
                image,
                pycolmap.Rigid3d(view.world_to_camera_matrix[:3, :]),
            )

    image_names = [item.image_name for item in dataset.views]
    reader_options = pycolmap.ImageReaderOptions()
    reader_options.mask_path = dataset.masks_dir
    pycolmap.extract_features(
        database_path=database_path,
        image_path=dataset.images_dir,
        image_names=image_names,
        camera_mode=pycolmap.CameraMode.PER_IMAGE,
        reader_options=reader_options,
        device=_device(pycolmap, requested_device),
    )
    progress("matching_features", 0.38)
    pycolmap.match_exhaustive(
        database_path=database_path,
        device=_device(pycolmap, requested_device),
    )
    progress("initializing_round_geometry", 0.72)

    options = pycolmap.IncrementalPipelineOptions()
    if hasattr(options, "mapper"):
        options.mapper.fix_existing_frames = True
        options.mapper.constant_cameras = set(camera_ids.values())
    reconstruction = pycolmap.triangulate_points(
        reconstruction=initial,
        database_path=database_path,
        image_path=dataset.images_dir,
        output_path=dataset.sparse_dir,
        clear_points=True,
        options=options,
        refine_intrinsics=False,
    )

    triangulation_pose_difference = 0.0
    for image_id, view in enumerate(dataset.views, start=1):
        stored = np.asarray(
            reconstruction.image(image_id).cam_from_world().matrix(),
            dtype=np.float64,
        )
        difference = float(
            np.max(
                np.abs(
                    stored
                    - view.world_to_camera_matrix[:3, :]
                )
            )
        )
        triangulation_pose_difference = max(
            triangulation_pose_difference,
            difference,
        )
    if triangulation_pose_difference > 1e-6:
        raise SparseInitializationError(
            "PyCOLMAP 改變了固化的 ArUco 世界姿態，已拒絕該結果。"
        )

    point_count = int(reconstruction.num_points3D())
    if point_count < 4:
        raise SparseInitializationError(
            "多視角特徵不足，無法建立可供模型初始化的稀疏點。"
        )
    bundle_adjustment_quality: dict = {
        "enabled": bool(use_constrained_bundle_adjustment),
        "status": "disabled",
    }
    refined_camera_poses: list[dict] = []
    if use_constrained_bundle_adjustment:
        progress("refining_camera_poses", 0.86)
        try:
            refinement = refine_sparse_camera_poses(
                pycolmap,
                reconstruction,
                dataset,
            )
            reconstruction = refinement.reconstruction
            bundle_adjustment_quality = refinement.quality
            refined_camera_poses = refinement.refined_camera_poses
        except Exception as error:
            bundle_adjustment_quality = {
                "enabled": True,
                "status": "failed",
                "reason": str(error),
                "fallback": "使用 ArUco 固化姿態繼續建立模型。",
            }
    update_round_dataset_pose_metadata(
        dataset,
        bundle_adjustment_quality,
        refined_camera_poses,
    )
    reconstruction.write(dataset.sparse_dir)
    progress("initializing_round_geometry", 0.95)
    sparse_point_cloud = dataset.sparse_dir.parent / "sparse_points.ply"
    reconstruction.export_PLY(sparse_point_cloud)
    quality = {
        "registered_image_count": int(reconstruction.num_reg_images()),
        "point_count": point_count,
        "mean_track_length": float(reconstruction.compute_mean_track_length()),
        "mean_observations_per_image": float(
            reconstruction.compute_mean_observations_per_reg_image()
        ),
        "mean_reprojection_error_px": float(
            reconstruction.compute_mean_reprojection_error()
        ),
        "triangulation_pose_difference": triangulation_pose_difference,
        "coordinate_unit": "millimetre",
        "fixed_camera_poses_constant": True,
        "camera_intrinsics_constant": True,
        "bundle_adjustment": bundle_adjustment_quality,
    }
    write_json_atomic(
        dataset.sparse_dir.parent / "quality.json",
        quality,
    )
    progress("initializing_round_geometry", 1.0)
    return {
        "reconstruction_path": str(dataset.sparse_dir),
        "point_cloud_path": str(sparse_point_cloud),
        "quality": quality,
        "refined_camera_poses": refined_camera_poses,
    }
