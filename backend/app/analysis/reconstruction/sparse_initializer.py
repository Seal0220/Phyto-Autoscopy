from __future__ import annotations

from pathlib import Path
import logging
import shutil
from typing import Callable

import numpy as np

from app.analysis.export.json_export import write_json_atomic
from app.analysis.checkpoints import StepJournal, step_signature
from app.analysis.reconstruction.colmap_camera import colmap_pinhole_params
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
    if requested.lower() == "cuda" and not getattr(pycolmap, "has_cuda", True):
        logging.getLogger(__name__).info("PyCOLMAP was built without CUDA; falling back to CPU SIFT")
        return getattr(device_type, "cpu")
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

    if dataset.initial_sparse_path is not None:
        # The rotating model already estimated poses and tracks; do not extract
        # or triangulate the same images a second time.
        reconstruction = pycolmap.Reconstruction(dataset.initial_sparse_path)
        by_name = {image.name: image for image in reconstruction.images.values()
                   if image.image_id in reconstruction.reg_image_ids()}
        for view in dataset.views:
            image = by_name.get(view.image_name)
            # PnP-aligned fixed views supervise the same relative geometry even
            # when COLMAP could not register their tracks automatically.
            if (dataset.coordinate_unit == "relative"
                    and view.camera_id in {"top", "side"}
                    and view.pose_source == "model_reference"):
                continue
            if image is None or not np.allclose(image.cam_from_world().matrix(), view.world_to_camera_matrix[:3], atol=1e-6):
                raise SparseInitializationError("參照模型姿態與訓練影像不一致。")
        dataset.sparse_dir.mkdir(parents=True, exist_ok=True)
        for path in dataset.initial_sparse_path.glob("*.bin"):
            shutil.copy2(path, dataset.sparse_dir / path.name)
        cloud = dataset.sparse_dir.parent / "sparse_points.ply"
        reconstruction.export_PLY(cloud)
        if cancel_check is not None:
            cancel_check()
        if progress_callback is not None:
            progress_callback("initializing_round_geometry", 1)
        return {"reconstruction_path": str(dataset.sparse_dir), "point_cloud_path": str(cloud),
                "quality": {"point_count": reconstruction.num_points3D(), "coordinate_unit": dataset.coordinate_unit,
                            "training_camera_counts": {camera: sum(view.camera_id == camera for view in dataset.views)
                                                       for camera in ("top", "side", "rotating")},
                            "initialization_source": "rotating_sfm_reference", "bundle_adjustment": {"enabled": False, "status": "already_initialized"}},
                "refined_camera_poses": []}

    def progress(stage: str, value: float) -> None:
        if cancel_check is not None:
            cancel_check()
        if progress_callback is not None:
            progress_callback(stage, value)

    def save(stage, payload, *, outputs=()):
        with StepJournal(dataset.root) as journal:
            journal.save(stage, dataset.round_key, signature, payload, outputs=outputs)

    signature = step_signature({
        "version": 3, "bundle_adjustment": use_constrained_bundle_adjustment,
        "views": [{"id": view.view_id, "hash": view.source_sha256,
                   "K": view.camera_matrix.tolist(), "pose": view.world_to_camera_matrix.tolist()}
                  for view in dataset.views],
    })
    with StepJournal(dataset.root) as journal:
        completed = journal.get("initializing_round_geometry", dataset.round_key, signature)
        features = journal.get("extracting_features", dataset.round_key, signature)
        matches = journal.get("matching_features", dataset.round_key, signature)
    if completed is not None:
        by_id = {view.view_id: view for view in dataset.views}
        for pose in completed.get("refined_camera_poses", []):
            if pose.get("refined") and pose["view_id"] in by_id:
                by_id[pose["view_id"]].world_to_camera_matrix[:] = np.asarray(pose["world_to_camera_matrix"])
        update_round_dataset_pose_metadata(dataset, completed["quality"]["bundle_adjustment"],
                                          completed.get("refined_camera_poses", []))
        progress("initializing_round_geometry", 1.0)
        return completed

    database_path = dataset.database_path
    reuse_database = features is not None and database_path.is_file()
    if database_path.exists() and not reuse_database:
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
            params=np.asarray(colmap_pinhole_params(matrix), dtype=np.float64),
            has_prior_focal_length=True,
        )

    progress("extracting_features", 0.02)
    initial = pycolmap.Reconstruction()
    with pycolmap.Database.open(database_path) as database:
        for camera in camera_by_id.values():
            if not reuse_database:
                database.write_camera(camera, use_camera_id=True)
            initial.add_camera_with_trivial_rig(camera)
        if not reuse_database and hasattr(database, "write_rig"):
            # Extraction otherwise assigns rig IDs in filename order.
            for rig in initial.rigs.values():
                database.write_rig(rig, use_rig_id=True)
        for image_id, view in enumerate(dataset.views, start=1):
            image = pycolmap.Image(
                name=view.image_name,
                camera_id=camera_ids[view.camera_id],
                image_id=image_id,
            )
            initial.add_image_with_trivial_frame(
                image,
                pycolmap.Rigid3d(view.world_to_camera_matrix[:3, :]),
            )
            if not reuse_database:
                if hasattr(database, "write_frame"):
                    database.write_frame(initial.frame(image_id), use_frame_id=True)
                database.write_image(initial.image(image_id), use_image_id=True)

    image_names = [item.image_name for item in dataset.views]
    reader_options = pycolmap.ImageReaderOptions()
    reader_options.mask_path = dataset.masks_dir
    device = _device(pycolmap, requested_device)
    backend = "cuda" if device == pycolmap.Device.cuda else "cpu"
    if not reuse_database:
        extraction = dict(
            database_path=database_path, image_path=dataset.images_dir, image_names=image_names,
            camera_mode=pycolmap.CameraMode.PER_IMAGE, reader_options=reader_options,
        )
        try:
            pycolmap.extract_features(**extraction, device=device)
        except Exception:
            if backend != "cuda":
                raise
            logging.getLogger(__name__).warning("CUDA SIFT failed; retrying on CPU", exc_info=True)
            device, backend = pycolmap.Device.cpu, "cpu"
            pycolmap.extract_features(**extraction, device=device)
        save("extracting_features", {"backend": backend})
    progress("matching_features", 0.38)
    if not reuse_database or matches is None:
        try:
            pycolmap.match_exhaustive(database_path=database_path, device=device)
        except Exception:
            if backend != "cuda":
                raise
            logging.getLogger(__name__).warning("CUDA SIFT matching failed; retrying on CPU", exc_info=True)
            backend = "cpu"
            pycolmap.match_exhaustive(database_path=database_path, device=pycolmap.Device.cpu)
        save("matching_features", {"backend": backend})
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
            "PyCOLMAP 改變了固化的世界姿態，已拒絕該結果。"
        )

    initial_point_count = int(reconstruction.num_points3D())
    if initial_point_count < 4:
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
                "fallback": "使用原始固化姿態繼續建立模型。",
            }
    point_count = int(reconstruction.num_points3D())
    if point_count < 4:
        raise SparseInitializationError(
            "姿態精修後稀疏三維點不足，無法建立 Gaussian 模型。"
        )
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
        "initial_point_count": initial_point_count,
        "point_count": point_count,
        "mean_track_length": float(reconstruction.compute_mean_track_length()),
        "mean_observations_per_image": float(
            reconstruction.compute_mean_observations_per_reg_image()
        ),
        "mean_reprojection_error_px": float(
            reconstruction.compute_mean_reprojection_error()
        ),
        "triangulation_pose_difference": triangulation_pose_difference,
        "coordinate_unit": dataset.coordinate_unit,
        "fixed_camera_poses_constant": True,
        "camera_intrinsics_constant": True,
        "bundle_adjustment": bundle_adjustment_quality,
    }
    write_json_atomic(
        dataset.sparse_dir.parent / "quality.json",
        quality,
    )
    result = {
        "reconstruction_path": str(dataset.sparse_dir),
        "point_cloud_path": str(sparse_point_cloud),
        "quality": quality,
        "refined_camera_poses": refined_camera_poses,
    }
    save("initializing_round_geometry", result,
         outputs=[sparse_point_cloud, *dataset.sparse_dir.glob("*.bin")])
    progress("initializing_round_geometry", 1.0)
    return result
