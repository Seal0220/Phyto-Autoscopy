from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class PlantIsolationView:
    view_id: str
    projection_matrix: np.ndarray
    plant_mask_path: Path


@dataclass(frozen=True, slots=True)
class PlantIsolationResult:
    output_path: Path
    scene_point_count: int
    plant_point_count: int
    supporting_view_count: int
    quality: dict[str, float | int | str]


def _read_mask(path: Path) -> np.ndarray:
    encoded = np.fromfile(path, dtype=np.uint8)
    mask = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise ValueError(f"植物遮罩無法解碼：{path.name}")
    return mask > 0


def _projection_support(
    points: np.ndarray,
    views: list[PlantIsolationView],
) -> tuple[np.ndarray, np.ndarray]:
    homogeneous = np.column_stack((points, np.ones(len(points))))
    support = np.zeros(len(points), dtype=np.int16)
    visibility = np.zeros(len(points), dtype=np.int16)
    for view in views:
        projection = np.asarray(view.projection_matrix, dtype=np.float64)
        if projection.shape != (3, 4):
            raise ValueError("植物模型投影矩陣格式無效。")
        pixels = (projection @ homogeneous.T).T
        depth = pixels[:, 2]
        mask = _read_mask(view.plant_mask_path)
        height, width = mask.shape
        valid_depth = depth > 1e-8
        x = np.zeros(len(points), dtype=np.int64)
        y = np.zeros(len(points), dtype=np.int64)
        x[valid_depth] = np.rint(
            pixels[valid_depth, 0] / depth[valid_depth]
        ).astype(np.int64)
        y[valid_depth] = np.rint(
            pixels[valid_depth, 1] / depth[valid_depth]
        ).astype(np.int64)
        visible = (
            valid_depth
            & (x >= 0)
            & (x < width)
            & (y >= 0)
            & (y < height)
        )
        visibility[visible] += 1
        indices = np.flatnonzero(visible)
        support[indices[mask[y[indices], x[indices]]]] += 1
    return support, visibility


def isolate_plant_point_cloud(
    scene_point_cloud_path: Path,
    output_path: Path,
    views: list[PlantIsolationView],
    *,
    platform_height_mm: float = 0.0,
    maximum_height_mm: float | None = None,
) -> PlantIsolationResult:
    """Isolate the plant with spatial, connectivity and mask evidence."""

    try:
        import open3d as o3d
    except ImportError as error:
        raise RuntimeError("Open3D 無法載入，無法分離植物點雲。") from error
    scene = o3d.io.read_point_cloud(str(scene_point_cloud_path))
    points = np.asarray(scene.points, dtype=np.float64)
    colors = np.asarray(scene.colors, dtype=np.float64)
    if len(points) < 20:
        raise ValueError("完整場景點雲不足，無法分離植物。")
    finite = np.isfinite(points).all(axis=1)
    points = points[finite]
    colors = colors[finite] if len(colors) == len(finite) else np.empty((0, 3))

    support, visibility = _projection_support(points, views)
    visible_views = max(len(views), 1)
    minimum_support = max(1, int(np.ceil(visible_views * 0.25)))
    spatial = points[:, 2] >= float(platform_height_mm) - 5.0
    if maximum_height_mm is not None:
        spatial &= points[:, 2] <= float(maximum_height_mm)
    radial = np.linalg.norm(points[:, :2], axis=1)
    finite_radius = radial[np.isfinite(radial)]
    if finite_radius.size:
        radial_limit = max(float(np.percentile(finite_radius, 92)), 25.0)
        spatial &= radial <= radial_limit
    retained = spatial & (support >= minimum_support) & (visibility > 0)
    if np.count_nonzero(retained) < 20:
        retained = spatial & (support > 0) & (visibility > 0)
    if np.count_nonzero(retained) < 20:
        raise ValueError("植物語意與空間證據不足，無法建立純植物點雲。")

    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(points[retained])
    if len(colors) == len(points):
        cloud.colors = o3d.utility.Vector3dVector(colors[retained])
    cloud = cloud.voxel_down_sample(voxel_size=0.75)
    if len(cloud.points) >= 30:
        cloud, _ = cloud.remove_statistical_outlier(
            nb_neighbors=min(20, len(cloud.points) - 1),
            std_ratio=2.0,
        )
    filtered = np.asarray(cloud.points)
    if len(filtered) < 20:
        raise ValueError("植物點雲清理後的有效點不足。")

    labels = np.asarray(
        cloud.cluster_dbscan(eps=4.0, min_points=5, print_progress=False)
    )
    valid_labels = [value for value in np.unique(labels) if value >= 0]
    if valid_labels:
        cluster_scores: list[tuple[float, int]] = []
        for label in valid_labels:
            cluster = filtered[labels == label]
            center = cluster.mean(axis=0)
            score = len(cluster) - 0.03 * np.linalg.norm(center[:2])
            cluster_scores.append((float(score), int(label)))
        selected_label = max(cluster_scores)[1]
        indices = np.flatnonzero(labels == selected_label)
        cloud = cloud.select_by_index(indices.tolist())
        filtered = np.asarray(cloud.points)
    if len(filtered) < 20:
        raise ValueError("找不到具有足夠連通性的植物主群聚。")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp.ply")
    if not o3d.io.write_point_cloud(str(temporary), cloud, write_ascii=False):
        raise OSError("純植物點雲無法寫入。")
    temporary.replace(output_path)
    return PlantIsolationResult(
        output_path=output_path,
        scene_point_count=int(len(points)),
        plant_point_count=int(len(filtered)),
        supporting_view_count=len(views),
        quality={
            "minimum_mask_support": minimum_support,
            "retained_ratio": float(len(filtered) / max(len(points), 1)),
            "coordinate_space": "aruco_world_mm",
            "isolation_evidence": "spatial+multiview_mask+connectivity",
        },
    )


def point_cloud_support(
    point_cloud_path: Path,
    point_world_mm: np.ndarray,
    *,
    neighbourhood_radius_mm: float = 5.0,
) -> tuple[float | None, int]:
    try:
        import open3d as o3d
        from scipy.spatial import cKDTree
    except ImportError:
        return None, 0
    cloud = o3d.io.read_point_cloud(str(point_cloud_path))
    points = np.asarray(cloud.points, dtype=np.float64)
    if not len(points):
        return None, 0
    finite = points[np.isfinite(points).all(axis=1)]
    if not len(finite):
        return None, 0
    tree = cKDTree(finite)
    distance, _ = tree.query(point_world_mm, k=1)
    neighbours = tree.query_ball_point(
        point_world_mm,
        r=neighbourhood_radius_mm,
    )
    return float(distance), len(neighbours)


__all__ = [
    "PlantIsolationResult",
    "PlantIsolationView",
    "isolate_plant_point_cloud",
    "point_cloud_support",
]
