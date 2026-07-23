from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.analysis.intrinsics.undistortion import FisheyeRemapCache
from app.analysis.export.json_export import write_json_atomic
from app.analysis.rounds.paths import (
    round_artifact_directory,
    safe_artifact_name,
)
from app.models.analysis_models import AnalysisView


def _read_image(path: Path) -> np.ndarray:
    encoded = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"影像無法解碼：{path.name}")
    return image


def _write_image(path: Path, image: np.ndarray) -> None:
    suffix = path.suffix.lower() or ".jpg"
    success, encoded = cv2.imencode(suffix, image)
    if not success:
        raise ValueError(f"影像無法編碼：{path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded.tofile(path)


def undistort_analysis_views(
    views: Sequence[AnalysisView],
    intrinsics_snapshot: Mapping[str, Mapping[str, Any]],
    output_root: Path,
    *,
    cancel_check: Callable[[], None] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[dict[str, Any]]:
    cache = FisheyeRemapCache()
    results: list[dict[str, Any]] = []
    total = len(views)
    written_masks: set[tuple[str, str]] = set()

    for index, view in enumerate(views, start=1):
        if cancel_check is not None:
            cancel_check()
        snapshot = intrinsics_snapshot.get(view.camera_id)
        if snapshot is None:
            raise ValueError(f"找不到 {view.camera_id} 的內參快照。")
        source = Path(view.absolute_path)
        image = _read_image(source)
        expected_size = (
            int(snapshot["analysis_image_width"]),
            int(snapshot["analysis_image_height"]),
        )
        if (image.shape[1], image.shape[0]) != expected_size:
            raise ValueError(
                f"{view.camera_id} 影像解析度在建立分析後發生變更。"
            )
        undistorted, valid_mask = cache.undistort(image, snapshot)
        round_root = (
            round_artifact_directory(output_root, view.round_key)
            / "undistortion"
        )
        image_path = (
            round_root
            / "images"
            / f"{safe_artifact_name(view.view_id)}.jpg"
        )
        mask_path = round_root / "valid_masks" / f"{view.camera_id}.png"
        _write_image(image_path, undistorted)
        mask_key = (str(round_root), view.camera_id)
        if mask_key not in written_masks:
            _write_image(mask_path, valid_mask)
            written_masks.add(mask_key)
        results.append({
            "view_id": view.view_id,
            "round_key": view.round_key,
            "camera_id": view.camera_id,
            "source_relative_path": view.relative_path,
            "source_sha256": view.image_sha256,
            "undistorted_path": str(image_path.relative_to(output_root)),
            "valid_pixel_mask_path": str(mask_path.relative_to(output_root)),
            "coordinate_space": "undistorted",
            "intrinsics_version": snapshot["intrinsics_version"],
            "image_width": expected_size[0],
            "image_height": expected_size[1],
        })
        if progress_callback is not None:
            progress_callback(index, total)

    write_json_atomic(
        output_root / "undistortion_manifest.json",
        {
            "coordinate_space": "undistorted",
            "views": results,
        },
    )
    return results
