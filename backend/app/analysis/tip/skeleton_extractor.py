from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.analysis.export.json_export import write_json_atomic


@dataclass(frozen=True, slots=True)
class SkeletonEndpoint:
    endpoint_id: str
    position_mm: np.ndarray
    branch_id: str
    path_length_mm: float
    local_radius_mm: float
    local_density: float
    supporting_point_count: int
    main_axis_score: float


@dataclass(frozen=True, slots=True)
class PlantSkeletonResult:
    path: Path
    base_position_mm: np.ndarray
    node_count: int
    edge_count: int
    endpoints: tuple[SkeletonEndpoint, ...]


def _sample_points(points: np.ndarray, maximum: int = 4_000) -> np.ndarray:
    if len(points) <= maximum:
        return points
    order = np.lexsort((points[:, 2], points[:, 1], points[:, 0]))
    indices = np.linspace(0, len(order) - 1, maximum, dtype=np.int64)
    return points[order[indices]]


def extract_plant_skeleton(
    plant_point_cloud_path: Path,
    output_path: Path,
) -> PlantSkeletonResult:
    try:
        import networkx as nx
        import open3d as o3d
        from scipy.spatial import cKDTree
    except ImportError as error:
        raise RuntimeError(
            "Open3D、SciPy 或 NetworkX 無法載入，無法建立植物骨架。"
        ) from error

    cloud = o3d.io.read_point_cloud(str(plant_point_cloud_path))
    cloud = cloud.voxel_down_sample(voxel_size=1.5)
    points = _sample_points(np.asarray(cloud.points, dtype=np.float64))
    if len(points) < 10:
        raise ValueError("植物點雲不足，無法建立骨架。")
    tree = cKDTree(points)
    distances, neighbours = tree.query(points, k=min(7, len(points)))
    graph = nx.Graph()
    graph.add_nodes_from(range(len(points)))
    for index in range(len(points)):
        for distance, neighbour in zip(distances[index, 1:], neighbours[index, 1:]):
            neighbour = int(neighbour)
            if neighbour == index or not np.isfinite(distance):
                continue
            graph.add_edge(index, neighbour, weight=float(distance))
    if graph.number_of_edges() == 0:
        raise ValueError("植物點雲無法形成連通骨架。")
    component = max(nx.connected_components(graph), key=len)
    graph = graph.subgraph(component).copy()
    skeleton = nx.minimum_spanning_tree(graph, weight="weight")
    base_node = min(
        skeleton.nodes,
        key=lambda index: (
            abs(float(points[index, 2])),
            float(np.linalg.norm(points[index, :2])),
        ),
    )
    path_lengths = nx.single_source_dijkstra_path_length(
        skeleton,
        base_node,
        weight="weight",
    )
    endpoint_nodes = [
        index
        for index, degree in skeleton.degree
        if degree == 1 and index != base_node
    ]
    endpoints = []
    maximum_path = max(path_lengths.values()) if path_lengths else 1.0
    for ordinal, index in enumerate(
        sorted(endpoint_nodes, key=lambda item: path_lengths.get(item, 0), reverse=True),
        start=1,
    ):
        radius_neighbours = tree.query_ball_point(points[index], r=4.0)
        local_points = points[radius_neighbours]
        radius = (
            float(np.median(np.linalg.norm(local_points - points[index], axis=1)))
            if len(local_points) > 1
            else 0.0
        )
        path_length = float(path_lengths.get(index, 0.0))
        continuity = path_length / max(maximum_path, 1e-9)
        density_score = min(len(radius_neighbours) / 30.0, 1.0)
        main_axis_score = float(np.clip(0.75 * continuity + 0.25 * density_score, 0, 1))
        endpoints.append(SkeletonEndpoint(
            endpoint_id=f"endpoint:{ordinal:02d}",
            position_mm=points[index].copy(),
            branch_id=f"branch:{index}",
            path_length_mm=path_length,
            local_radius_mm=radius,
            local_density=float(len(radius_neighbours) / (4.0 ** 3)),
            supporting_point_count=len(radius_neighbours),
            main_axis_score=main_axis_score,
        ))

    edges = [
        {
            "source": int(source),
            "target": int(target),
            "length_mm": float(data.get("weight", 0.0)),
        }
        for source, target, data in skeleton.edges(data=True)
    ]
    payload = {
        "coordinate_space": "aruco_world_mm",
        "base_node": int(base_node),
        "base_position_mm": points[base_node].tolist(),
        "nodes": [
            {
                "node_id": int(index),
                "position_mm": points[index].tolist(),
                "degree": int(skeleton.degree[index]),
                "path_from_base_mm": float(path_lengths.get(index, 0.0)),
            }
            for index in skeleton.nodes
        ],
        "edges": edges,
        "endpoints": [
            {
                "endpoint_id": item.endpoint_id,
                "position_mm": item.position_mm.tolist(),
                "branch_id": item.branch_id,
                "path_length_mm": item.path_length_mm,
                "local_radius_mm": item.local_radius_mm,
                "local_density": item.local_density,
                "supporting_point_count": item.supporting_point_count,
                "main_axis_score": item.main_axis_score,
            }
            for item in endpoints
        ],
    }
    write_json_atomic(output_path, payload)
    return PlantSkeletonResult(
        path=output_path,
        base_position_mm=points[base_node].copy(),
        node_count=skeleton.number_of_nodes(),
        edge_count=skeleton.number_of_edges(),
        endpoints=tuple(endpoints),
    )


__all__ = [
    "PlantSkeletonResult",
    "SkeletonEndpoint",
    "extract_plant_skeleton",
]
