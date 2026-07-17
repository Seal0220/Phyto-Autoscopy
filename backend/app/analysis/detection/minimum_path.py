from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from math import hypot, sqrt

import cv2
import numpy as np

from app.analysis.detection.epipolar_constraint import point_line_distance


Pixel = tuple[int, int]


@dataclass(frozen=True)
class MinimumPathResult:
    candidate_point: tuple[float, float]
    path: list[tuple[float, float]]
    path_cost: float
    path_length_px: float


def morphological_skeleton(mask: np.ndarray) -> np.ndarray:
    if mask.ndim != 2:
        raise ValueError("Minimum Path 遮罩必須是單通道影像。")
    image = np.where(mask > 0, 1, 0).astype(np.uint8)

    while True:
        changed = False
        for first_pass in (True, False):
            padded = np.pad(image, 1, mode="constant")
            center = padded[1:-1, 1:-1]
            north = padded[:-2, 1:-1]
            north_east = padded[:-2, 2:]
            east = padded[1:-1, 2:]
            south_east = padded[2:, 2:]
            south = padded[2:, 1:-1]
            south_west = padded[2:, :-2]
            west = padded[1:-1, :-2]
            north_west = padded[:-2, :-2]
            neighbours = (
                north,
                north_east,
                east,
                south_east,
                south,
                south_west,
                west,
                north_west,
            )
            neighbour_count = sum(neighbours)
            transitions = sum(
                (left == 0) & (right == 1)
                for left, right in zip(
                    neighbours,
                    (*neighbours[1:], neighbours[0]),
                )
            )
            removable = (
                (center == 1)
                & (neighbour_count >= 2)
                & (neighbour_count <= 6)
                & (transitions == 1)
            )
            if first_pass:
                removable &= (
                    (north * east * south == 0)
                    & (east * south * west == 0)
                )
            else:
                removable &= (
                    (north * east * west == 0)
                    & (north * south * west == 0)
                )
            if np.any(removable):
                image[removable] = 0
                changed = True
        if not changed:
            break
    return image * 255


def _neighbors(
    node: Pixel,
    skeleton: np.ndarray,
    connectivity: int,
):
    x, y = node
    offsets = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    if connectivity == 8:
        offsets.extend([(-1, -1), (-1, 1), (1, -1), (1, 1)])
    elif connectivity != 4:
        raise ValueError("Minimum Path 鄰接方式只能是 4 或 8。")
    height, width = skeleton.shape
    for dx, dy in offsets:
        nx, ny = x + dx, y + dy
        if 0 <= nx < width and 0 <= ny < height and skeleton[ny, nx] > 0:
            yield (nx, ny), sqrt(2.0) if dx and dy else 1.0


def _nearest_node(
    nodes: list[Pixel],
    target: tuple[float, float],
) -> Pixel:
    return min(
        nodes,
        key=lambda node: (
            hypot(node[0] - target[0], node[1] - target[1]),
            node[1],
            node[0],
        ),
    )


def _shortest_path_tree(
    skeleton: np.ndarray,
    start: Pixel,
    radius: np.ndarray,
    connectivity: int,
) -> tuple[dict[Pixel, float], dict[Pixel, Pixel]]:
    distances: dict[Pixel, float] = {start: 0.0}
    previous: dict[Pixel, Pixel] = {}
    queue: list[tuple[float, Pixel]] = [(0.0, start)]
    while queue:
        cost, node = heappop(queue)
        if cost != distances.get(node):
            continue
        for neighbor, step in _neighbors(node, skeleton, connectivity):
            nx, ny = neighbor
            # CHLOROCULUS implementation choice: favour the mask centreline
            # while computing a true minimum-cost path on the skeleton graph.
            edge_cost = step / max(float(radius[ny, nx]), 1.0)
            next_cost = cost + edge_cost
            if next_cost < distances.get(neighbor, float("inf")):
                distances[neighbor] = next_cost
                previous[neighbor] = node
                heappush(queue, (next_cost, neighbor))
    return distances, previous


def _reconstruct_path(
    previous: dict[Pixel, Pixel],
    start: Pixel,
    end: Pixel,
) -> list[Pixel]:
    path = [end]
    while path[-1] != start:
        parent = previous.get(path[-1])
        if parent is None:
            return []
        path.append(parent)
    path.reverse()
    return path


def _path_length(path: list[Pixel]) -> float:
    return sum(
        hypot(right[0] - left[0], right[1] - left[1])
        for left, right in zip(path, path[1:])
    )


def minimum_path_tip(
    mask: np.ndarray,
    *,
    plant_base: tuple[float, float],
    epipolar_line: tuple[float, float, float],
    maximum_epipolar_distance_px: float,
    connectivity: int,
    origin: tuple[int, int] = (0, 0),
) -> MinimumPathResult | None:
    skeleton = morphological_skeleton(mask)
    ys, xs = np.nonzero(skeleton)
    nodes = [(int(x), int(y)) for x, y in zip(xs, ys)]
    if not nodes:
        return None
    origin_x, origin_y = origin
    local_base = plant_base[0] - origin_x, plant_base[1] - origin_y
    local_line = (
        epipolar_line[0],
        epipolar_line[1],
        epipolar_line[2]
        + epipolar_line[0] * origin_x
        + epipolar_line[1] * origin_y,
    )
    start = _nearest_node(nodes, local_base)
    degree = {
        node: sum(1 for _ in _neighbors(node, skeleton, connectivity))
        for node in nodes
    }
    candidates = [
        node
        for node in nodes
        if degree[node] <= 1
        and point_line_distance(node, local_line) <= maximum_epipolar_distance_px
    ]
    if not candidates:
        candidates = [
            node
            for node in nodes
            if point_line_distance(node, local_line) <= maximum_epipolar_distance_px
        ]
    if not candidates:
        return None
    radius = cv2.distanceTransform(
        np.where(mask > 0, 255, 0).astype(np.uint8),
        cv2.DIST_L2,
        3,
    )
    distances, previous = _shortest_path_tree(
        skeleton,
        start,
        radius,
        connectivity,
    )
    available = []
    for candidate in candidates:
        if candidate not in distances:
            continue
        path = _reconstruct_path(previous, start, candidate)
        if path:
            available.append((candidate, path, distances[candidate], _path_length(path)))
    if not available:
        return None
    # The endpoint is selected by the longest geodesic distance from the
    # configured plant base; its route is the minimum-cost graph path.
    candidate, path, cost, path_length = max(
        available,
        key=lambda item: (item[3], -item[2], -item[0][1], -item[0][0]),
    )
    return MinimumPathResult(
        candidate_point=(
            float(candidate[0] + origin_x),
            float(candidate[1] + origin_y),
        ),
        path=[
            (float(x + origin_x), float(y + origin_y))
            for x, y in path
        ],
        path_cost=float(cost),
        path_length_px=float(path_length),
    )
