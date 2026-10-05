"""Estimate unknown rotating poses before any fixed-camera calibration."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

from app.analysis.checkpoints import StepJournal, step_signature
from app.analysis.export.json_export import write_json_atomic
from app.analysis.pose_alignment.model_reference import fit_motor_orbit
from app.analysis.reconstruction.dataset_adapter import _materialize_read_only_image, _sha256
from app.analysis.rounds.paths import safe_artifact_name


def reference_image_name(view: dict) -> str:
    return f"{view['camera_id']}__{safe_artifact_name(view['view_id'])}{Path(view['undistorted_path']).suffix.lower()}"


def build_reference_sfm(job: dict, root: Path, *, progress, cancel_check) -> dict:
    import pycolmap

    root.mkdir(parents=True, exist_ok=True)
    registering = job.get("reference_action") == "register_fixed"
    source = Path(job["reference_root"]).resolve() if registering else root
    views = job["selected_views"]
    signature = step_signature({"version": 2, "views": views, "intrinsics": job["intrinsics_snapshot"],
                                "action": job.get("reference_action"), "settings": job["parameters"],
                                "source_signature": job.get("source_signature")})
    with StepJournal(root) as journal:
        completed = journal.get("reference_sfm", "model", signature)
        if completed is not None:
            return completed
        stage_record = journal.get("reference_sfm", "database", signature)
    images = source / "images"
    images.mkdir(parents=True, exist_ok=True)
    database_path = source / "database.db"
    cameras = {"rotating": 3, "top": 1, "side": 2}
    fresh_database = not registering and (stage_record is None or not database_path.is_file())
    if fresh_database:
        database_path.unlink(missing_ok=True)
        reconstruction = pycolmap.Reconstruction()
        with pycolmap.Database.open(database_path) as database:
            for camera_id in {v["camera_id"] for v in views}:
                snapshot = job["intrinsics_snapshot"][camera_id]
                matrix = np.asarray(snapshot["undistorted_camera_matrix"])
                camera = pycolmap.Camera(camera_id=cameras[camera_id], model="PINHOLE",
                    width=snapshot["analysis_image_width"], height=snapshot["analysis_image_height"],
                    params=[matrix[0, 0], matrix[1, 1], matrix[0, 2], matrix[1, 2]], has_prior_focal_length=True)
                reconstruction.add_camera_with_trivial_rig(camera)
                database.write_camera(camera, use_camera_id=True)
            for rig in reconstruction.rigs.values():
                database.write_rig(rig, use_rig_id=True)
            for image_id, view in enumerate(views, 1):
                cancel_check()
                image_path = Path(view["undistorted_path"]).resolve()
                image_path.relative_to(Path(job["artifact_root"]).resolve())
                if _sha256(image_path) != view["undistorted_sha256"]:
                    raise ValueError("參照模型輸入已變更，無法恢復既有姿態。")
                name = reference_image_name(view)
                _materialize_read_only_image(image_path, images / name)
                image = pycolmap.Image(image_id=image_id, camera_id=cameras[view["camera_id"]], name=name)
                reconstruction.add_image_with_trivial_frame(image)
                database.write_frame(reconstruction.frame(image_id), use_frame_id=True)
                database.write_image(reconstruction.image(image_id), use_image_id=True)
        with StepJournal(root) as journal:
            journal.save("reference_sfm", "database", signature, {})
    device = pycolmap.Device.cuda if pycolmap.has_cuda else pycolmap.Device.cpu
    backend = "cuda" if pycolmap.has_cuda else "cpu"
    if not registering:
        for stage, operation in (("extracting_features", pycolmap.extract_features), ("matching_features", pycolmap.match_exhaustive)):
            with StepJournal(root) as journal:
                saved = journal.get("reference_sfm", stage, signature)
            if saved is not None and not fresh_database:
                backend = saved.get("backend", backend)
                device = pycolmap.Device.cpu if backend == "cpu" else device
                continue
            progress(stage, .1 if stage == "extracting_features" else .35, f"參照模型：{'特徵擷取' if stage == 'extracting_features' else '多視角配對'}（{backend.upper()}）")
            arguments = {"database_path": database_path, "device": device}
            if stage == "extracting_features":
                arguments.update(image_path=images, image_names=[reference_image_name(v) for v in views])
            try:
                operation(**arguments)
            except Exception:
                if device == pycolmap.Device.cpu:
                    raise
                logging.getLogger(__name__).warning("Reference CUDA features failed; using CPU", exc_info=True)
                device, backend = pycolmap.Device.cpu, "cpu"
                operation(**{**arguments, "device": device})
            with StepJournal(root) as journal:
                journal.save("reference_sfm", stage, signature, {"backend": backend})
            cancel_check()
    options = pycolmap.IncrementalPipelineOptions()
    options.image_names = [reference_image_name(v) for v in views if registering or v["camera_id"] == "rotating"]
    options.multiple_models = False
    options.min_model_size = 6
    options.ba_refine_focal_length = options.ba_refine_principal_point = options.ba_refine_extra_params = False
    options.ba_refine_sensor_from_rig = False
    options.ba_use_gpu = bool(pycolmap.has_cuda)
    options.ba_gpu_index = "0"
    options.mapper.abs_pose_refine_focal_length = options.mapper.abs_pose_refine_extra_params = False
    options.mapper.init_min_num_inliers = max(12, int(job["parameters"].get("minimum_rotating_inliers", 12)))
    options.mapper.abs_pose_min_num_inliers = options.mapper.init_min_num_inliers
    options.mapper.abs_pose_max_error = float(job["parameters"].get("maximum_pnp_reprojection_error_px", 5))
    options.mapper.init_min_tri_angle = 4
    options.mapper.filter_min_tri_angle = 1
    options.fix_existing_frames = registering
    snapshots = root / "snapshots" / signature
    snapshots.mkdir(parents=True, exist_ok=True)
    options.snapshot_path, options.snapshot_frames_freq = snapshots, 1
    options.mapper.constant_cameras = set(cameras.values())
    token = pycolmap.CancellationToken()
    paused = []

    def registered_image():
        try:
            cancel_check()
        except Exception as error:
            paused.append(error)
            token.cancel()
            return
        count = len([p for p in snapshots.iterdir() if (p / "images.bin").is_file()])
        progress("estimating_reference_poses", .5 + .4 * min(count / max(len(views), 1), 1),
                 f"參照模型：已保存 {count} 個姿態步驟")

    latest = sorted((p for p in snapshots.iterdir() if (p / "images.bin").is_file()), key=lambda p: p.name)
    input_path = latest[-1] if latest else source / "sparse" / "0" if registering else ""
    progress("estimating_reference_poses", .5, "參照模型：對齊固定鏡頭" if registering else "參照模型：求旋臂初始姿態")
    models = pycolmap.incremental_mapping(database_path, images, root / "mapping", options,
        input_path=str(input_path), next_image_callback=registered_image, cancellation_token=token)
    if paused:
        raise paused[0]
    cancel_check()
    if not models:
        raise ValueError("旋臂多視角重建未找到連續的共同特徵，尚無法建立參照模型。")
    reconstruction = max(models.values(), key=lambda m: m.num_reg_images())
    sparse = root / "sparse" / "0"
    sparse.mkdir(parents=True, exist_ok=True)
    reconstruction.write(sparse)
    by_name = {reference_image_name(v): v for v in views}
    registered_ids = set(reconstruction.reg_image_ids())
    registered_views = []
    for image in reconstruction.images.values():
        if image.name not in by_name or image.image_id not in registered_ids:
            continue
        view = by_name[image.name]
        pose = np.eye(4)
        pose[:3] = image.cam_from_world().matrix()
        registered_views.append({**view, "image_name": image.name, "pose": pose.tolist(),
                                 "point_count": int(image.num_points3D)})
    if registering:
        original = json.loads((source / "reference.json").read_text(encoding="utf-8"))
        orbit = original["orbit"]
        backend = original["quality"]["feature_backend"]
    else:
        orbit = fit_motor_orbit(registered_views)
    # Sparse tracks are identifiable physical anchors in the trained model frame.
    anchors = [{"id": int(point_id), "xyz": point.xyz.tolist(), "rgb": point.color.tolist(),
                "error_px": float(point.error), "track_length": int(point.track.length())}
               for point_id, point in reconstruction.points3D.items() if point.track.length() >= 3 and point.error <= 4]
    anchors.sort(key=lambda p: (-p["track_length"], p["error_px"]))
    if len(anchors) < 4:
        raise ValueError("旋臂模型缺少四個可供固定鏡頭對齊的穩定三維參照點。")
    cloud = root / "sparse_points.ply"
    reconstruction.export_PLY(cloud)
    geometry_signature = step_signature({"inputs": signature,
        "geometry": {path.name: _sha256(path) for path in sorted(sparse.glob("*.bin"))}})
    result = {"status": "completed", "signature": geometry_signature, "job_signature": signature, "coordinate_unit": "relative",
              "views": registered_views, "orbit": orbit, "points": anchors[:8000], "sparse_path": str(sparse),
              "reference_path": str(root / "reference.json"), "point_cloud_path": str(cloud),
              "quality": {"registered_image_count": len(registered_views), "point_count": reconstruction.num_points3D(),
                          "mean_reprojection_error_px": float(reconstruction.compute_mean_reprojection_error()),
                          "coordinate_unit": "relative", "feature_backend": backend}}
    write_json_atomic(root / "reference.json", result)
    with StepJournal(root) as journal:
        journal.save("reference_sfm", "model", signature, result,
                     outputs=[root / "reference.json", cloud, *sparse.glob("*.bin")])
    progress("estimating_reference_poses", 1, "旋臂參照姿態已保存")
    return result
