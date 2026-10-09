"""Expose observed, plant-supported COLMAP tracks for image inspection."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

from app.analysis.image_probe import read_analysis_image
from app.analysis.segmentation.plant_mask import create_plant_mask


def plant_feature_correspondences(reconstruction, reference_views, selected_views, manifest, root: Path):
    selected = {view.view_id: view for view in selected_views}
    by_name = {view["image_name"]: view for view in reference_views if view.get("image_name")}
    metadata = {item["view_id"]: item for item in manifest}
    grouped = defaultdict(list)
    registered = set()
    for image in reconstruction.images.values():
        original = by_name.get(image.name)
        if original is None or original["view_id"] not in selected:
            continue
        view = selected[original["view_id"]]
        row = metadata.get(view.view_id)
        if row is None:
            continue
        path = (root / row["undistorted_path"]).resolve()
        valid_path = (root / row["valid_pixel_mask_path"]).resolve()
        path.relative_to(root.resolve())
        valid_path.relative_to(root.resolve())
        pixels = read_analysis_image(path, cv2.IMREAD_COLOR)
        valid = read_analysis_image(valid_path, cv2.IMREAD_GRAYSCALE)
        if pixels is None or valid is None:
            continue
        mask = create_plant_mask(pixels, valid_pixel_mask=valid).mask
        camera = reconstruction.cameras[image.camera_id]
        registered.add(view.view_id)
        scale = np.array([pixels.shape[1] / camera.width, pixels.shape[0] / camera.height])
        for observation in image.points2D:
            point_id = int(observation.point3D_id)
            if point_id not in reconstruction.points3D:
                continue
            point = reconstruction.points3D[point_id]
            if point.error > 2 or point.track.length() < 3:
                continue
            x, y = np.asarray(observation.xy) * scale
            if not np.isfinite([x, y]).all() or not (0 <= x < mask.shape[1] - 1 and 0 <= y < mask.shape[0] - 1):
                continue
            if mask[int(round(y)), int(round(x))] == 0:
                continue
            grouped[point_id].append({"view_id": view.view_id, "camera_id": view.camera_id,
                                      "x_px": float(x), "y_px": float(y)})
    features, occupied = [], defaultdict(list)
    for point_id, observations in sorted(grouped.items(), key=lambda row: (reconstruction.points3D[row[0]].error, row[0])):
        if len({item["camera_id"] for item in observations}) < 2:
            continue
        if any(any((item["x_px"] - x) ** 2 + (item["y_px"] - y) ** 2 < 12 ** 2
                   for x, y in occupied[item["view_id"]]) for item in observations):
            continue
        features.append({"feature_id": str(point_id), "error_px": float(reconstruction.points3D[point_id].error),
                         "observations": observations})
        for item in observations:
            occupied[item["view_id"]].append((item["x_px"], item["y_px"]))
        if len(features) == 64:
            break
    return {"coordinate_space": "undistorted_pixels", "features": features,
            "registered_view_ids": sorted(registered),
            "unregistered_view_ids": sorted(selected.keys() - registered)}
