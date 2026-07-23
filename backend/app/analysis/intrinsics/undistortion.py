from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class RemapEntry:
    map_x: np.ndarray
    map_y: np.ndarray
    new_camera_matrix: np.ndarray
    valid_pixel_mask: np.ndarray


class FisheyeRemapCache:
    def __init__(self) -> None:
        self._entries: dict[tuple[object, ...], RemapEntry] = {}

    def get(self, snapshot: Mapping[str, Any]) -> RemapEntry:
        width = int(snapshot["analysis_image_width"])
        height = int(snapshot["analysis_image_height"])
        key = (
            snapshot["camera_id"],
            snapshot["intrinsics_version"],
            width,
            height,
            float(snapshot.get("undistortion_balance", 0.0)),
        )
        cached = self._entries.get(key)
        if cached is not None:
            return cached

        camera_matrix = np.asarray(
            snapshot["adapted_camera_matrix"],
            dtype=np.float64,
        )
        distortion = np.asarray(
            snapshot["distortion_coefficients"],
            dtype=np.float64,
        ).reshape(-1, 1)
        new_camera_matrix = np.asarray(
            snapshot["undistorted_camera_matrix"],
            dtype=np.float64,
        )
        if snapshot["camera_model"] == "opencv_fisheye":
            map_x, map_y = cv2.fisheye.initUndistortRectifyMap(
                camera_matrix,
                distortion,
                np.eye(3, dtype=np.float64),
                new_camera_matrix,
                (width, height),
                cv2.CV_32FC1,
            )
        else:
            map_x, map_y = cv2.initUndistortRectifyMap(
                camera_matrix,
                distortion,
                None,
                new_camera_matrix,
                (width, height),
                cv2.CV_32FC1,
            )
        source_mask = np.full((height, width), 255, dtype=np.uint8)
        valid_pixel_mask = cv2.remap(
            source_mask,
            map_x,
            map_y,
            interpolation=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
        entry = RemapEntry(
            map_x=map_x,
            map_y=map_y,
            new_camera_matrix=new_camera_matrix,
            valid_pixel_mask=valid_pixel_mask,
        )
        self._entries[key] = entry
        return entry

    def undistort(
        self,
        image: np.ndarray,
        snapshot: Mapping[str, Any],
    ) -> tuple[np.ndarray, np.ndarray]:
        entry = self.get(snapshot)
        undistorted = cv2.remap(
            image,
            entry.map_x,
            entry.map_y,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
        )
        return undistorted, entry.valid_pixel_mask.copy()
