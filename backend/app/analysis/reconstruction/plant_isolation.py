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
    background_output_path: Path | None
    scene_point_count: int
    plant_point_count: int
    background_point_count: int
    supporting_view_count: int
    quality: dict[str, float | int | str]


@dataclass(frozen=True, slots=True)
class PlantPointClassification:
    plant_mask: np.ndarray
    background_mask: np.ndarray
    quality: dict[str, float | int | str]


def plant_isolation_views_from_dataset(
    dataset: object,
) -> list[PlantIsolationView]:
    views = []
    for view in getattr(dataset, "views", ()):
        plant_mask_path = getattr(view, "plant_mask_path", None)
        if plant_mask_path is None:
            continue
        camera_matrix = np.asarray(
            getattr(view, "camera_matrix", None),
            dtype=np.float64,
        )
        world_to_camera = np.asarray(
            getattr(view, "world_to_camera_matrix", None),
            dtype=np.float64,
        )
        if camera_matrix.shape != (3, 3):
            raise ValueError("植物模型相機內參格式無效。")
        if world_to_camera.shape != (4, 4):
            raise ValueError("植物模型相機姿態格式無效。")
        views.append(
            PlantIsolationView(
                view_id=str(getattr(view, "view_id", "")),
                projection_matrix=(
                    camera_matrix @ world_to_camera[:3, :4]
                ),
                plant_mask_path=Path(plant_mask_path),
            )
        )
    if not views:
        raise ValueError("模型資料集沒有植物遮罩，無法分離植物與背景。")
    return views


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


def classify_plant_points(
    points: np.ndarray,
    views: list[PlantIsolationView],
    *,
    platform_height_mm: float = 0.0,
    maximum_height_mm: float | None = None,
    minimum_plant_point_count: int = 20,
) -> PlantPointClassification:
    """Classify world-space points with spatial and multi-view mask evidence."""

    coordinates = np.asarray(points, dtype=np.float64)
    if coordinates.ndim != 2 or coordinates.shape[1] != 3:
        raise ValueError("植物模型點座標格式無效。")
    if len(coordinates) < minimum_plant_point_count:
        raise ValueError("三維模型點數不足，無法分離植物與背景。")
    if not views:
        raise ValueError("缺少植物遮罩視角，無法分離植物與背景。")

    finite = np.isfinite(coordinates).all(axis=1)
    support, visibility = _projection_support(coordinates, views)
    minimum_support = max(1, int(np.ceil(len(views) * 0.25)))
    spatial = finite & (
        coordinates[:, 2] >= float(platform_height_mm) - 5.0
    )
    if maximum_height_mm is not None:
        spatial &= coordinates[:, 2] <= float(maximum_height_mm)

    radial = np.linalg.norm(coordinates[:, :2], axis=1)
    finite_radius = radial[finite & np.isfinite(radial)]
    radial_limit = None
    if finite_radius.size:
        radial_limit = max(
            float(np.percentile(finite_radius, 92)),
            25.0,
        )
        spatial &= radial <= radial_limit

    plant = spatial & (support >= minimum_support) & (visibility > 0)
    if np.count_nonzero(plant) < minimum_plant_point_count:
        plant = spatial & (support > 0) & (visibility > 0)
    plant_count = int(np.count_nonzero(plant))
    if plant_count < minimum_plant_point_count:
        raise ValueError("植物語意與空間證據不足，無法分離植物模型。")

    background = finite & ~plant
    background_count = int(np.count_nonzero(background))
    return PlantPointClassification(
        plant_mask=plant,
        background_mask=background,
        quality={
            "scene_point_count": int(np.count_nonzero(finite)),
            "plant_point_count": plant_count,
            "background_point_count": background_count,
            "supporting_view_count": len(views),
            "minimum_mask_support": minimum_support,
            "plant_ratio": float(
                plant_count / max(int(np.count_nonzero(finite)), 1)
            ),
            "radial_limit_mm": (
                float(radial_limit)
                if radial_limit is not None
                else "unavailable"
            ),
            "coordinate_space": "aruco_world_mm",
            "classification_evidence": "spatial+multiview_mask",
        },
    )


def isolate_plant_point_cloud(
    scene_point_cloud_path: Path,
    output_path: Path,
    views: list[PlantIsolationView],
    *,
    background_output_path: Path | None = None,
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

    classification = classify_plant_points(
        points,
        views,
        platform_height_mm=platform_height_mm,
        maximum_height_mm=maximum_height_mm,
    )
    retained = classification.plant_mask
    background = classification.background_mask

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

    written_background_path = None
    background_point_count = int(np.count_nonzero(background))
    if background_output_path is not None:
        if background_point_count == 0:
            raise ValueError("背景分類沒有可輸出的有效點。")
        background_cloud = o3d.geometry.PointCloud()
        background_cloud.points = o3d.utility.Vector3dVector(
            points[background]
        )
        if len(colors) == len(points):
            background_cloud.colors = o3d.utility.Vector3dVector(
                colors[background]
            )
        background_cloud = background_cloud.voxel_down_sample(
            voxel_size=0.75
        )
        background_output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        background_temporary = background_output_path.with_suffix(
            background_output_path.suffix + ".tmp.ply"
        )
        if not o3d.io.write_point_cloud(
            str(background_temporary),
            background_cloud,
            write_ascii=False,
        ):
            raise OSError("背景點雲無法寫入。")
        background_temporary.replace(background_output_path)
        written_background_path = background_output_path
        background_point_count = len(background_cloud.points)

    return PlantIsolationResult(
        output_path=output_path,
        background_output_path=written_background_path,
        scene_point_count=int(len(points)),
        plant_point_count=int(len(filtered)),
        background_point_count=int(background_point_count),
        supporting_view_count=len(views),
        quality={
            **classification.quality,
            "final_plant_point_count": int(len(filtered)),
            "final_background_point_count": int(background_point_count),
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
    "PlantPointClassification",
    "classify_plant_points",
    "isolate_plant_point_cloud",
    "plant_isolation_views_from_dataset",
    "point_cloud_support",
]
