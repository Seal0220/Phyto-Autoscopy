from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Sequence


def observation_graph(
    camera_ids: Iterable[str],
    observations: Sequence[object],
) -> dict[str, set[str]]:
    graph = {camera_id: set() for camera_id in camera_ids}
    for observation in observations:
        if not bool(getattr(observation, "accepted", False)):
            continue
        detections = getattr(observation, "detections", {})
        visible = [
            camera_id
            for camera_id, detection in detections.items()
            if bool(detection.get("board_detected"))
        ]
        for index, camera_id in enumerate(visible):
            graph.setdefault(camera_id, set())
            for other in visible[index + 1:]:
                graph[camera_id].add(other)
                graph.setdefault(other, set()).add(camera_id)
    return graph


def graph_components(graph: dict[str, set[str]]) -> list[list[str]]:
    pending = set(graph)
    components: list[list[str]] = []
    while pending:
        root = min(pending)
        queue = deque([root])
        pending.remove(root)
        component: list[str] = []
        while queue:
            current = queue.popleft()
            component.append(current)
            for neighbor in sorted(graph.get(current, ())):
                if neighbor in pending:
                    pending.remove(neighbor)
                    queue.append(neighbor)
        components.append(sorted(component))
    return components


def observation_graph_status(
    camera_ids: Iterable[str],
    observations: Sequence[object],
) -> dict:
    graph = observation_graph(camera_ids, observations)
    components = graph_components(graph)
    edge_count = sum(len(neighbors) for neighbors in graph.values()) // 2
    return {
        "connected": len(components) <= 1 and bool(graph),
        "components": components,
        "edge_count": edge_count,
        "adjacency": {
            camera_id: sorted(neighbors)
            for camera_id, neighbors in graph.items()
        },
    }


def pair_observations(
    observations: Sequence[object],
) -> dict[tuple[str, str], list[object]]:
    pairs: dict[tuple[str, str], list[object]] = defaultdict(list)
    for observation in observations:
        detections = getattr(observation, "detections", {})
        visible = sorted(
            camera_id
            for camera_id, detection in detections.items()
            if bool(detection.get("board_detected"))
        )
        for index, camera_id in enumerate(visible):
            for other in visible[index + 1:]:
                pairs[(camera_id, other)].append(observation)
    return dict(pairs)
