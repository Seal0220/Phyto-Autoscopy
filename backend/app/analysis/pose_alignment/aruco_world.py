from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np


MARKER_POSITIONS = (
    "left_rear",
    "right_rear",
    "left_front",
    "right_front",
)


def _value(settings: object, name: str):
    if isinstance(settings, Mapping):
        return settings[name]
    return getattr(settings, name)


def _optional(settings: object, name: str, default=None):
    if isinstance(settings, Mapping):
        return settings.get(name, default)
    return getattr(settings, name, default)


def marker_ids(settings: object) -> dict[str, int]:
    return {
        "left_rear": int(_value(settings, "left_rear_id")),
        "right_rear": int(_value(settings, "right_rear_id")),
        "left_front": int(_value(settings, "left_front_id")),
        "right_front": int(_value(settings, "right_front_id")),
    }


def marker_centers(settings: object) -> dict[str, np.ndarray]:
    if bool(_optional(settings, "advanced_mode", False)):
        configured = _value(settings, "marker_centers_world_mm")
        return {
            position: np.asarray(
                [
                    float(_value(configured[position], "x_mm")),
                    float(_value(configured[position], "y_mm")),
                    float(_optional(configured[position], "z_mm", 0.0)),
                ],
                dtype=np.float64,
            )
            for position in MARKER_POSITIONS
        }

    half_width = float(_value(settings, "left_right_center_distance_mm")) / 2.0
    half_depth = float(_value(settings, "rear_front_center_distance_mm")) / 2.0
    x_sign = 1.0 if _value(settings, "x_axis_direction") == "right" else -1.0
    y_sign = 1.0 if _value(settings, "y_axis_direction") == "front" else -1.0
    centers = {
        "left_rear": np.asarray([-half_width * x_sign, -half_depth * y_sign, 0.0]),
        "right_rear": np.asarray([half_width * x_sign, -half_depth * y_sign, 0.0]),
        "left_front": np.asarray([-half_width * x_sign, half_depth * y_sign, 0.0]),
        "right_front": np.asarray([half_width * x_sign, half_depth * y_sign, 0.0]),
    }
    origin = _value(settings, "world_origin")
    if origin != "layout_center":
        offset = centers[origin].copy()
        centers = {
            position: center - offset
            for position, center in centers.items()
        }
    return centers


def marker_world_corners(settings: object) -> dict[int, np.ndarray]:
    centers = marker_centers(settings)
    ids = marker_ids(settings)
    half_size = float(_value(settings, "marker_size_mm")) / 2.0
    top_y = (
        -half_size
        if _value(settings, "z_axis_direction") == "up"
        else half_size
    )
    bottom_y = -top_y
    local = np.asarray(
        [
            [-half_size, top_y, 0.0],
            [half_size, top_y, 0.0],
            [half_size, bottom_y, 0.0],
            [-half_size, bottom_y, 0.0],
        ],
        dtype=np.float64,
    )
    result: dict[int, np.ndarray] = {}
    configured = _optional(settings, "marker_centers_world_mm", {})
    for position in MARKER_POSITIONS:
        orientation = float(_value(settings, "marker_orientation_deg"))
        if bool(_optional(settings, "advanced_mode", False)):
            orientation = float(
                _optional(configured[position], "orientation_deg", orientation)
            )
        radians = math.radians(orientation)
        rotation = np.asarray(
            [
                [math.cos(radians), -math.sin(radians), 0.0],
                [math.sin(radians), math.cos(radians), 0.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )
        result[ids[position]] = local @ rotation.T + centers[position]
    return result


def aruco_layout_snapshot(settings: object) -> dict:
    payload = (
        settings.model_dump(mode="json")
        if hasattr(settings, "model_dump")
        else dict(settings)
    )
    payload["marker_centers_resolved_mm"] = {
        position: center.astype(float).tolist()
        for position, center in marker_centers(settings).items()
    }
    ids = marker_ids(settings)
    corners = marker_world_corners(settings)
    payload["layout_version"] = "aruco_world_v2"
    payload["marker_ids"] = list(ids.values())
    payload["marker_corner_world_coordinates"] = {
        str(marker_id): value.astype(float).tolist()
        for marker_id, value in corners.items()
    }
    payload["markers"] = [
        {
            "position": position,
            "marker_id": marker_id,
            "corners_world_mm": corners[marker_id].astype(float).tolist(),
        }
        for position, marker_id in ids.items()
    ]
    payload["marker_orientation"] = payload.get("marker_orientation_deg", 0.0)
    payload["world_axes"] = {
        "x": payload.get("x_axis_direction", "right"),
        "y": payload.get("y_axis_direction", "front"),
        "z": payload.get("z_axis_direction", "up"),
    }
    payload["unit"] = "mm"
    payload["distance_definition"] = "marker_center_to_center"
    return payload
