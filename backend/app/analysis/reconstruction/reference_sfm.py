"""Align reference images with COLMAP, then calibrate the motor reference."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import cv2

from app.analysis.checkpoints import StepJournal, step_signature
from app.analysis.export.json_export import write_json_atomic
from app.analysis.pose_alignment.model_reference import fit_motor_orbit
from app.analysis.reconstruction.dataset_adapter import _materialize_read_only_image, _sha256
from app.analysis.rounds.paths import safe_artifact_name
from app.analysis.image_probe import read_analysis_image
from app.analysis.segmentation.plant_mask import create_plant_mask
from app.analysis.segmentation.reconstruction_mask import create_reconstruction_mask
from app.analysis.reconstruction.reference_pose_refinement import REFERENCE_GEOMETRY_VERSION, refine_reference_geometry
from app.analysis.reconstruction.colmap_camera import colmap_pinhole_params


def reference_image_name(view: dict) -> str:
    return f"{view['camera_id']}__{safe_artifact_name(view['view_id'])}{Path(view['undistorted_path']).suffix.lower()}"


def reference_initial_pair(pycolmap, database_path: Path, views: list[dict], minimum_inliers: int, *, cancel_check=lambda: None):
    """Choose depth support measured from images rather than match count alone.

    Motor readings only restrict the candidate search. The score uses the
    triangulation angle estimated from calibrated image correspondences.
    Repeated fixed frames have no depth baseline and are never seed pairs.
    """
    angles = {}
    for view in views:
        if view["camera_id"] != "rotating":
            continue
        angle = view.get("angle_deg")
        if angle is None:
            angle = view.get("motor_position_deg")
        if angle is not None and np.isfinite(float(angle)):
            angles[reference_image_name(view)] = float(angle)
    with pycolmap.Database.open(database_path) as database:
        images = {image.image_id: image for image in database.read_all_images()}
        by_id = {image_id: angles[image.name] for image_id, image in images.items() if image.name in angles}
        pairs, geometries = database.read_two_view_geometries()
        candidates = []
        for pair, geometry in zip(pairs, geometries):
            first, second = pycolmap.pair_id_to_image_pair(pair)
            if first not in by_id or second not in by_id:
                continue
            baseline = abs((by_id[first] - by_id[second] + 180.) % 360. - 180.)
            inliers = len(geometry.inlier_matches)
            if 10. <= baseline <= 90. and inliers >= minimum_inliers:
                candidates.append((inliers, baseline, first, second, geometry))
        if not candidates:
            return None
        # Keep adequate support and bound repeated relative-pose estimation.
        minimum_support = max(minimum_inliers, int(max(row[0] for row in candidates) * .35))
        candidates = sorted((row for row in candidates if row[0] >= minimum_support), reverse=True,
                            key=lambda row: row[:4])[:64]
        options = pycolmap.TwoViewGeometryOptions()
        options.min_num_inliers = minimum_inliers
        options.compute_relative_pose = True
        options.ransac.random_seed = 0
        best = None
        for _, baseline, first, second, geometry in candidates:
            cancel_check()
            camera1 = database.read_camera(images[first].camera_id)
            camera2 = database.read_camera(images[second].camera_id)
            points1 = np.asarray(database.read_keypoints(first))[:, :2]
            points2 = np.asarray(database.read_keypoints(second))[:, :2]
            measured = pycolmap.estimate_calibrated_two_view_geometry(
                camera1, points1, camera2, points2, geometry.inlier_matches, options,
            )
            triangle = float(measured.tri_angle)
            support = len(measured.inlier_matches)
            if measured.cam2_from_cam1 is None:
                continue
            rotation = measured.cam2_from_cam1.rotation.matrix()
            rotation_angle = float(np.rad2deg(np.arccos(np.clip((np.trace(rotation) - 1) / 2, -1, 1))))
            # A compact/near-planar subject can admit an essential-matrix
            # branch with fictitious parallax. Metadata rejects grossly
            # implausible branches; it never sets the reconstructed pose.
            plausible_angle = baseline * 1.5 + 10
            if (not np.isfinite(triangle)
                    or triangle < np.deg2rad(4) or support < minimum_support
                    or np.rad2deg(triangle) > plausible_angle or rotation_angle > plausible_angle
                    or abs(measured.cam2_from_cam1.translation[2]) > .95):
                continue
            # Depth information grows with support and squared parallax; cap
            # at 45 degrees so weak, extreme-baseline matches cannot dominate.
            score = support * np.sin(min(triangle, np.pi / 4)) ** 2
            candidate = {"image_ids": [first, second], "motor_baseline_deg": baseline,
                         "camera_id": "rotating", "source": "calibrated_image_geometry",
                         "triangulation_angle_deg": float(np.rad2deg(triangle)),
                         "verified_inlier_count": support, "depth_support_score": float(score)}
            if best is None or score > best[0]:
                best = (score, candidate)
    return best[1] if best else None


def prepare_reference_feature_masks(views, root: Path, signature: str, *, cancel_check) -> Path:
    """Keep plant, pot and soil tracks; moving equipment cannot anchor poses."""
    masks = root / "feature_masks"
    masks.mkdir(parents=True, exist_ok=True)
    with StepJournal(root) as journal:
        for view in views:
            cancel_check()
            if journal.get("reference_feature_mask", view["view_id"], signature) is not None:
                continue
            image = read_analysis_image(Path(view["undistorted_path"]), cv2.IMREAD_COLOR)
            valid = read_analysis_image(Path(view["valid_mask_path"]), cv2.IMREAD_GRAYSCALE)
            if image is None or valid is None:
                raise ValueError("參照模型的影像或有效像素遮罩無法讀取。")
            plant = create_plant_mask(image, valid_pixel_mask=valid)
            foreground = create_reconstruction_mask(image, plant_mask=plant.mask, valid_pixel_mask=valid)
            destination = masks / (reference_image_name(view) + ".png")
            cancel_check()
            success, encoded = cv2.imencode(".png", foreground)
            if not success:
                raise ValueError("參照模型特徵遮罩無法編碼。")
            encoded.tofile(destination)
            journal.save("reference_feature_mask", view["view_id"], signature,
                         {"foreground_pixels": int(np.count_nonzero(foreground))}, outputs=[destination])
    return masks


def build_reference_sfm(job: dict, root: Path, *, progress, cancel_check) -> dict:
    import pycolmap

    root.mkdir(parents=True, exist_ok=True)
    registering = job.get("reference_action") == "register_fixed"
    source = Path(job["reference_root"]).resolve() if registering else root
    views = job["selected_views"]
    signature = step_signature({"version": 4, "geometry_version": REFERENCE_GEOMETRY_VERSION,
                                "refine_geometry": job.get("refine_geometry", True),
                                "views": views, "intrinsics": job["intrinsics_snapshot"],
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
                    params=colmap_pinhole_params(matrix), has_prior_focal_length=True)
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
                reader = pycolmap.ImageReaderOptions()
                reader.mask_path = prepare_reference_feature_masks(views, source, signature, cancel_check=cancel_check)
                arguments["reader_options"] = reader
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
    # All three cameras contribute tracks to the same reconstruction. Repeated
    # fixed views still provide independent observations of the same scene.
    options.image_names = [reference_image_name(v) for v in views]
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
    options.mapper.random_seed = 0
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
    initial_pair = None
    if not registering and not input_path:
        initial_pair = reference_initial_pair(pycolmap, database_path, views, options.mapper.init_min_num_inliers,
                                              cancel_check=cancel_check)
        if initial_pair is None:
            raise ValueError("旋臂影像缺少有足夠視差的有效配對，無法建立參照模型深度。")
        options.init_image_id1, options.init_image_id2 = initial_pair["image_ids"]
    progress("estimating_reference_poses", .5, "參照模型：對齊固定鏡頭" if registering else "參照模型：三鏡頭共同對齊")
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
        refinement_quality = original["quality"].get("geometry_refinement", {})
    else:
        refinement_quality = {"status": "disabled", "reason": "immutable_reference_model"}
        if job.get("refine_geometry", True):
            progress("estimating_reference_poses", .92, "參照模型：影像姿態精修與角度校正")
            refined = refine_reference_geometry(pycolmap, reconstruction, registered_views, cancel_check=cancel_check)
            reconstruction, refinement_quality = refined.reconstruction, refined.quality
        if refinement_quality.get("status") == "kept_original":
            progress("estimating_reference_poses", .96, "參照模型：精修未通過，沿用已檢查的原始影像幾何")
        images_by_name = {image.name: image for image in reconstruction.images.values()}
        for view in registered_views:
            image = images_by_name[view["image_name"]]
            pose = np.eye(4)
            pose[:3] = image.cam_from_world().matrix()
            view.update(pose=pose.tolist(), point_count=int(image.num_points3D))
        try:
            orbit = fit_motor_orbit(registered_views)
        except ValueError:
            if job.get("refine_geometry", True):
                raise
            # A measurement-frame failure must not discard usable SfM geometry.
            orbit = None
        observed_angles = {item["view_id"]: item["image_angle_deg"] for item in (orbit or {}).get("angle_calibration", {}).get("observations", [])}
        for view in registered_views:
            if view["view_id"] in observed_angles:
                view["image_angle_deg"] = observed_angles[view["view_id"]]
    reconstruction.write(sparse)
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
    input_counts = {camera: sum(v["camera_id"] == camera for v in views) for camera in cameras}
    registered_counts = {camera: sum(v["camera_id"] == camera for v in registered_views) for camera in cameras}
    missing_cameras = [camera for camera in cameras if input_counts[camera] and not registered_counts[camera]]
    result = {"status": "completed", "signature": geometry_signature, "job_signature": signature, "coordinate_unit": "relative",
              "views": registered_views, "orbit": orbit, "points": anchors[:8000], "sparse_path": str(sparse),
              "reference_path": str(root / "reference.json"), "point_cloud_path": str(cloud),
              "quality": {"registered_image_count": len(registered_views), "point_count": reconstruction.num_points3D(),
                          "input_camera_counts": input_counts, "registered_camera_counts": registered_counts,
                          "camera_registration": {"status": "partial" if missing_cameras else "complete",
                                                  "missing_camera_ids": missing_cameras,
                                                  "all_three_cameras_registered": all(registered_counts[camera] > 0 for camera in cameras)},
                          "absolute_accuracy_verified": False,
                          "initial_pair": initial_pair, "geometry_refinement": refinement_quality,
                          "mean_reprojection_error_px": float(reconstruction.compute_mean_reprojection_error()),
                          "coordinate_unit": "relative", "feature_backend": backend}}
    write_json_atomic(root / "reference.json", result)
    with StepJournal(root) as journal:
        journal.save("reference_sfm", "model", signature, result,
                     outputs=[root / "reference.json", cloud, *sparse.glob("*.bin")])
    progress("estimating_reference_poses", 1, "旋臂參照姿態已保存")
    return result
