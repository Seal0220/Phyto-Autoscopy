from __future__ import annotations

import hashlib
import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from threading import Event
from time import monotonic
from typing import Any, Mapping, Sequence

import cv2
import numpy as np

from app.analysis.checkpoints import StepJournal, step_signature
from app.analysis.export.json_export import write_json_atomic
from app.analysis.image_probe import AnalysisImageProbe, read_analysis_image
from app.analysis.reconstruction.backend import CancelCheck, ProgressCallback
from app.analysis.rounds.paths import safe_artifact_name
from app.analysis.segmentation.plant_mask import create_plant_mask
from app.analysis.segmentation.reconstruction_mask import create_reconstruction_mask


# Advance this version when plant/pot segmentation changes so saved masks expire.
MASK_PREPARATION_VERSION = 2


@dataclass(frozen=True, slots=True)
class PreparedRoundView:
    view_id: str
    camera_id: str
    image_name: str
    image_path: Path
    valid_mask_path: Path | None
    plant_mask_path: Path | None
    image_width: int
    image_height: int
    camera_matrix: np.ndarray
    world_to_camera_matrix: np.ndarray
    source_sha256: str
    angle_deg: float | None
    pose_source: str
    aruco_reprojection_error_px: float | None
    foreground_mask_path: Path | None = None


@dataclass(frozen=True, slots=True)
class PreparedRoundDataset:
    analysis_id: str
    round_key: str
    root: Path
    images_dir: Path
    masks_dir: Path
    database_path: Path
    sparse_dir: Path
    metadata_path: Path
    views: tuple[PreparedRoundView, ...]
    coordinate_unit: str = "millimetre"
    initial_sparse_path: Path | None = None
    geometry_signature: str | None = None


def update_round_dataset_pose_metadata(
    dataset: PreparedRoundDataset,
    bundle_adjustment_quality: Mapping[str, Any],
    refined_camera_poses: Sequence[Mapping[str, Any]],
) -> None:
    try:
        payload = json.loads(
            dataset.metadata_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("模型資料集姿態清單無法更新。") from error
    if not isinstance(payload, dict) or not isinstance(
        payload.get("views"),
        list,
    ):
        raise ValueError("模型資料集姿態清單格式無效。")
    refined_by_view = {
        str(item.get("view_id")): item
        for item in refined_camera_poses
        if item.get("refined")
    }
    view_by_id = {
        item.view_id: item
        for item in dataset.views
    }
    for item in payload["views"]:
        if not isinstance(item, dict):
            continue
        view_id = str(item.get("view_id") or "")
        view = view_by_id.get(view_id)
        if view is None:
            continue
        item["world_to_camera_matrix"] = (
            view.world_to_camera_matrix.tolist()
        )
        if view_id in refined_by_view:
            item["pose_source"] = "feature_refined"
            item["bundle_adjustment"] = {
                "translation_change_mm": refined_by_view[view_id].get(
                    "translation_change_mm"
                ),
                "rotation_change_deg": refined_by_view[view_id].get(
                    "rotation_change_deg"
                ),
            }
    payload["bundle_adjustment"] = dict(bundle_adjustment_quality)
    write_json_atomic(dataset.metadata_path, payload)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _materialize_read_only_image(
    source: Path,
    destination: Path,
    *,
    source_sha256: str | None = None,
) -> None:
    if destination.exists():
        if os.path.samefile(source, destination):
            return
        if _sha256(destination) != (source_sha256 or _sha256(source)):
            raise ValueError(
                f"模型資料集中的影像內容與既有檔案衝突：{destination.name}"
            )
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def _read_image(
    path: Path,
    flags: int,
    *,
    reader: AnalysisImageProbe | None = None,
) -> np.ndarray:
    image = reader.read(path, flags) if reader is not None else read_analysis_image(path, flags)
    if image is None:
        raise ValueError(f"模型資料集影像無法解碼：{path.name}")
    return image


def _write_png(path: Path, image: np.ndarray) -> None:
    success, encoded = cv2.imencode(".png", image)
    if not success:
        raise ValueError(f"模型資料集遮罩無法編碼：{path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.png")
    encoded.tofile(temporary)
    temporary.replace(path)


def _matrix(
    value: object,
    shape: tuple[int, int],
    *,
    label: str,
) -> np.ndarray:
    matrix = np.asarray(value, dtype=np.float64)
    if matrix.shape != shape or not np.isfinite(matrix).all():
        raise ValueError(f"{label}格式無效。")
    return matrix


def automatic_dataset_workers(
    intrinsics: Mapping,
    *,
    cpu_count: int | None = None,
    available_ram: int | None = None,
) -> int:
    """Bound concurrent full-resolution segmentation buffers by host memory."""
    if available_ram is None:
        try:
            import psutil

            available_ram = int(psutil.virtual_memory().available)
        except ImportError:
            available_ram = 1024 ** 3
    pixels = max((
        int(snapshot["analysis_image_width"]) * int(snapshot["analysis_image_height"])
        for snapshot in intrinsics.values()
    ), default=1920 * 1080)
    # GrabCut, component labels, color channels and native decoder buffers are
    # considerably larger than the encoded image. Eight concurrent images gave
    # higher measured throughput while preserving headroom for the model worker.
    bytes_per_image = max(pixels * 160, 64 * 1024 ** 2)
    return max(1, min(cpu_count or os.cpu_count() or 1, 8, int(available_ram * .6) // bytes_per_image))


def _prepare_dataset_masks(
    views: Sequence[PreparedRoundView],
    signatures: Mapping[str, str],
    root: Path,
    workers: int,
    *,
    progress_callback: ProgressCallback | None,
    cancel_check: CancelCheck | None,
) -> tuple[dict[str, dict], dict[str, int | float]]:
    """Save each mask before reporting it, with thread-owned CUDA/SQLite handles."""
    started = monotonic()
    results = Queue()
    stopped = Event()
    quality: dict[str, dict] = {}
    completed = reused = 0
    last_report = float("-inf")
    # Configure WAL and create the schema before concurrent connections open.
    with StepJournal(root):
        pass

    def check_cancel() -> None:
        if cancel_check is not None:
            cancel_check()
        if stopped.is_set():
            raise InterruptedError("建模影像前處理已停止。")

    def process_batch(batch: Sequence[PreparedRoundView]) -> None:
        valid_masks: dict[str, np.ndarray] = {}
        with (
            StepJournal(root) as journal,
            AnalysisImageProbe(root / "image_cache", initialize_decoder=False) as reader,
        ):
            for view in batch:
                check_cancel()
                signature = signatures[view.view_id]
                saved = journal.get("preparing_model_images", view.view_id, signature)
                if saved is not None:
                    results.put((view.view_id, saved["quality"], True))
                    continue
                image = _read_image(view.image_path, cv2.IMREAD_COLOR, reader=reader)
                valid = None
                if view.valid_mask_path is not None:
                    # Views often share one immutable valid-pixel mask. Cache
                    # that mask inside this thread without sharing CUDA handles.
                    stat = view.valid_mask_path.stat()
                    mask_key = str((stat.st_dev, stat.st_ino or str(view.valid_mask_path.resolve()), stat.st_size, stat.st_mtime_ns))
                    if mask_key not in valid_masks:
                        valid_masks[mask_key] = _read_image(view.valid_mask_path, cv2.IMREAD_GRAYSCALE, reader=reader)
                    valid = valid_masks[mask_key]
                check_cancel()
                segmentation = create_plant_mask(image, valid_pixel_mask=valid)
                check_cancel()
                foreground = create_reconstruction_mask(image, plant_mask=segmentation.mask, valid_pixel_mask=valid)
                check_cancel()
                _write_png(view.plant_mask_path, segmentation.mask)
                _write_png(view.foreground_mask_path, foreground)
                mask_quality = {
                    "foreground_ratio": segmentation.foreground_ratio,
                    "component_count": segmentation.component_count,
                    "confidence": segmentation.confidence,
                    "reconstruction_foreground_ratio": float(np.count_nonzero(foreground) / foreground.size),
                }
                journal.save(
                    "preparing_model_images", view.view_id, signature,
                    {"quality": mask_quality},
                    outputs=[view.plant_mask_path, view.foreground_mask_path],
                )
                results.put((view.view_id, mask_quality, False))

    def report() -> None:
        nonlocal last_report
        now = monotonic()
        if progress_callback is not None and (completed == len(views) or now - last_report >= .5):
            last_report = now
            progress_callback(
                "selecting_reconstruction_views", .01 * completed / max(len(views), 1),
                f"建模影像 {completed}/{len(views)} 張 · 並行 {workers} 執行緒 · 沿用遮罩 {reused} 張",
            )

    report()
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="model-image") as executor:
        pending = {executor.submit(process_batch, views[index::workers]) for index in range(workers)}
        try:
            while pending:
                check_cancel()
                finished, pending = wait(pending, timeout=.1, return_when=FIRST_COMPLETED)
                while True:
                    try:
                        view_id, mask_quality, was_reused = results.get_nowait()
                    except Empty:
                        break
                    quality[view_id] = mask_quality
                    completed += 1
                    reused += int(was_reused)
                report()
                for future in finished:
                    future.result()
        finally:
            stopped.set()
            for future in pending:
                future.cancel()
    return quality, {
        "workers": workers, "image_count": completed, "reused_masks": reused,
        "generated_masks": completed - reused, "duration_seconds": monotonic() - started,
    }


def prepare_round_dataset(
    job: Mapping[str, Any],
    output_dir: Path,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
    maximum_workers: int | None = None,
) -> PreparedRoundDataset:
    analysis_id = str(job.get("analysis_id") or "").strip()
    round_key = str(job.get("round_key") or "").strip()
    raw_views = job.get("selected_views")
    camera_poses = job.get("camera_poses")
    intrinsics = job.get("intrinsics_snapshot")
    if not analysis_id or not round_key:
        raise ValueError("重建工作缺少分析或 Round 識別碼。")
    if not isinstance(raw_views, Sequence) or isinstance(raw_views, (str, bytes)):
        raise ValueError("重建工作缺少已選取的 View。")
    if not isinstance(camera_poses, Sequence) or isinstance(
        camera_poses,
        (str, bytes),
    ):
        raise ValueError("重建工作缺少相機姿態。")
    if not isinstance(intrinsics, Mapping):
        raise ValueError("重建工作缺少內參快照。")
    background = job.get("background")
    if not isinstance(background, Mapping):
        background = {}
    generate_plant_mask = bool(
        background.get("generate_plant_mask", True)
    )
    use_plant_mask_in_loss = bool(
        background.get("use_plant_mask_in_loss", True)
    )

    pose_by_view = {
        str(item.get("view_id")): item
        for item in camera_poses
        if isinstance(item, Mapping) and item.get("valid")
    }
    root = output_dir.resolve()
    artifact_root_text = str(job.get("artifact_root") or "").strip()
    artifact_root = (
        Path(artifact_root_text).resolve()
        if artifact_root_text
        else None
    )
    images_dir = root / "images"
    masks_dir = root / "masks"
    plant_masks_dir = root / "plant_masks"
    foreground_masks_dir = root / "foreground_masks"
    sparse_dir = root / "sparse" / "0"
    database_path = root / "database.db"
    metadata_path = root / "phyto_metadata.json"
    images_dir.mkdir(parents=True, exist_ok=True)
    masks_dir.mkdir(parents=True, exist_ok=True)
    plant_masks_dir.mkdir(parents=True, exist_ok=True)
    sparse_dir.mkdir(parents=True, exist_ok=True)

    prepared_views: list[PreparedRoundView] = []
    plant_mask_quality: dict[str, dict[str, float | int]] = {}
    mask_signatures: dict[str, str] = {}
    seen_names: set[str] = set()
    for raw_view in raw_views:
        if cancel_check is not None:
            cancel_check()
        if not isinstance(raw_view, Mapping):
            raise ValueError("重建 View 格式無效。")
        view_id = str(raw_view.get("view_id") or "").strip()
        camera_id = str(raw_view.get("camera_id") or "").strip()
        if camera_id not in {"top", "side", "rotating"}:
            raise ValueError(f"View {view_id or 'unknown'} 的相機識別碼無效。")
        pose = pose_by_view.get(view_id)
        snapshot = intrinsics.get(camera_id)
        if pose is None:
            raise ValueError(f"View {view_id} 沒有有效的固化相機姿態。")
        if not isinstance(snapshot, Mapping):
            raise ValueError(f"找不到 {camera_id} 的固化內參。")
        source = Path(str(raw_view.get("undistorted_path") or "")).resolve()
        if artifact_root is not None:
            try:
                source.relative_to(artifact_root)
            except ValueError as error:
                raise ValueError(
                    f"View {view_id} 的去畸變影像不在分析產物目錄內。"
                ) from error
        if not source.is_file():
            raise ValueError(f"View {view_id} 的去畸變影像不存在。")
        source_hash = _sha256(source)
        expected_hash = str(raw_view.get("undistorted_sha256") or "").strip()
        if expected_hash and source_hash != expected_hash:
            raise ValueError(f"View {view_id} 的去畸變影像已變更。")

        image_name = (
            f"{camera_id}__{safe_artifact_name(view_id)}{source.suffix.lower()}"
        )
        if image_name in seen_names:
            raise ValueError(f"模型資料集影像名稱重複：{image_name}")
        seen_names.add(image_name)
        destination = images_dir / image_name
        _materialize_read_only_image(source, destination, source_sha256=source_hash)

        mask_source_text = str(raw_view.get("valid_mask_path") or "").strip()
        mask_destination = None
        mask_hash = None
        if mask_source_text:
            mask_source = Path(mask_source_text).resolve()
            if artifact_root is not None:
                try:
                    mask_source.relative_to(artifact_root)
                except ValueError as error:
                    raise ValueError(
                        f"View {view_id} 的有效像素遮罩不在分析產物目錄內。"
                    ) from error
            if not mask_source.is_file():
                raise ValueError(f"View {view_id} 的有效像素遮罩不存在。")
            # PyCOLMAP expects ``<image-name>.png`` under its mask root.
            mask_destination = masks_dir / f"{image_name}.png"
            mask_hash = _sha256(mask_source)
            _materialize_read_only_image(mask_source, mask_destination, source_sha256=mask_hash)

        plant_mask_destination = None
        foreground_mask_destination = None
        if generate_plant_mask or use_plant_mask_in_loss:
            plant_mask_destination = plant_masks_dir / f"{image_name}.png"
            foreground_mask_destination = foreground_masks_dir / f"{image_name}.png"
            mask_signatures[view_id] = step_signature({
                "version": MASK_PREPARATION_VERSION, "source_sha256": source_hash,
                "valid_mask_sha256": mask_hash,
            })

        width = int(snapshot["analysis_image_width"])
        height = int(snapshot["analysis_image_height"])
        camera_matrix = _matrix(
            snapshot["undistorted_camera_matrix"],
            (3, 3),
            label=f"{camera_id} 去畸變內參",
        )
        rotation = _matrix(
            pose.get("rotation_matrix"),
            (3, 3),
            label=f"View {view_id} 旋轉矩陣",
        )
        translation = np.asarray(
            pose.get("translation_vector_mm"),
            dtype=np.float64,
        ).reshape(-1)
        if translation.shape != (3,) or not np.isfinite(translation).all():
            raise ValueError(f"View {view_id} 平移向量格式無效。")
        world_to_camera = np.eye(4, dtype=np.float64)
        world_to_camera[:3, :3] = rotation
        world_to_camera[:3, 3] = translation
        prepared_views.append(
            PreparedRoundView(
                view_id=view_id,
                camera_id=camera_id,
                image_name=image_name,
                image_path=destination,
                valid_mask_path=mask_destination,
                plant_mask_path=plant_mask_destination,
                foreground_mask_path=foreground_mask_destination,
                image_width=width,
                image_height=height,
                camera_matrix=camera_matrix,
                world_to_camera_matrix=world_to_camera,
                source_sha256=source_hash,
                angle_deg=(
                    float(raw_view["angle_deg"])
                    if raw_view.get("angle_deg") is not None
                    else None
                ),
                pose_source=str(pose.get("pose_source") or "invalid"),
                aruco_reprojection_error_px=(
                    float(pose["aruco_reprojection_error_px"])
                    if pose.get("aruco_reprojection_error_px") is not None
                    else None
                ),
            )
        )

    if len(prepared_views) < 3:
        raise ValueError("每輪多視角模型至少需要三個具有有效姿態的 View。")
    camera_ids = {item.camera_id for item in prepared_views}
    coordinate_unit = str(job.get("world_coordinate_unit") or "millimetre")
    if coordinate_unit not in {"millimetre", "relative"}:
        raise ValueError("模型座標單位無效。")
    required_cameras = {"rotating"} if coordinate_unit == "relative" else {"top", "side", "rotating"}
    missing = required_cameras - camera_ids
    if missing:
        raise ValueError("模型資料集缺少必要視角：" + "、".join(sorted(missing)))

    preparation = {}
    if mask_signatures:
        if maximum_workers is not None and maximum_workers < 1:
            raise ValueError("建模影像執行緒數至少為 1。")
        workers = min(len(prepared_views), automatic_dataset_workers(intrinsics), maximum_workers or 8)
        plant_mask_quality, preparation = _prepare_dataset_masks(
            prepared_views, mask_signatures, root, workers,
            progress_callback=progress_callback, cancel_check=cancel_check,
        )

    metadata = {
        "schema_version": "1.0",
        "analysis_id": analysis_id,
        "round_key": round_key,
        "coordinate_space": "undistorted",
        "world_coordinate_unit": coordinate_unit,
        "world_coordinate_source": (
            "rotating_sfm_reference" if coordinate_unit == "relative" else (
                "measured_stereo_baseline_and_feature_poses"
                if any(view.pose_source == "rig_stereo" for view in prepared_views)
                else "aruco_snapshot_and_refined_camera_poses"
            )
        ),
        "source_images_are_read_only": True,
        "plant_mask_in_training_loss": use_plant_mask_in_loss,
        "reconstruction_foreground": "plant_and_pot" if use_plant_mask_in_loss else "scene",
        "plant_mask_quality": plant_mask_quality,
        "preparation": preparation,
        "views": [
            {
                "view_id": item.view_id,
                "camera_id": item.camera_id,
                "image_name": item.image_name,
                "image_sha256": item.source_sha256,
                "valid_mask": (
                    str(item.valid_mask_path.relative_to(root))
                    if item.valid_mask_path is not None
                    else None
                ),
                "plant_mask": (
                    str(item.plant_mask_path.relative_to(root))
                    if item.plant_mask_path is not None
                    else None
                ),
                "foreground_mask": (
                    str(item.foreground_mask_path.relative_to(root))
                    if item.foreground_mask_path is not None else None
                ),
                "image_width": item.image_width,
                "image_height": item.image_height,
                "camera_matrix": item.camera_matrix.tolist(),
                "world_to_camera_matrix": (
                    item.world_to_camera_matrix.tolist()
                ),
                "angle_deg": item.angle_deg,
                "pose_source": item.pose_source,
                "aruco_reprojection_error_px": (
                    item.aruco_reprojection_error_px
                ),
            }
            for item in prepared_views
        ],
    }
    write_json_atomic(metadata_path, metadata)
    initial_sparse = Path(job["initial_sparse_path"]).resolve() if job.get("initial_sparse_path") else None
    if initial_sparse is not None:
        if artifact_root is None:
            raise ValueError("參照模型缺少產物根目錄。")
        initial_sparse.relative_to(artifact_root)
        if not (initial_sparse / "points3D.bin").is_file():
            raise ValueError("參照模型的稀疏初始化資料遺失。")
    return PreparedRoundDataset(
        analysis_id=analysis_id,
        round_key=round_key,
        root=root,
        images_dir=images_dir,
        masks_dir=masks_dir,
        database_path=database_path,
        sparse_dir=sparse_dir,
        metadata_path=metadata_path,
        views=tuple(prepared_views),
        coordinate_unit=coordinate_unit,
        initial_sparse_path=initial_sparse,
        geometry_signature=job.get("geometry_signature"),
    )
