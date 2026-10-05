from __future__ import annotations

from dataclasses import dataclass, field
import logging
from threading import RLock
from typing import Any, Mapping

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RemapEntry:
    map_x: np.ndarray
    map_y: np.ndarray
    new_camera_matrix: np.ndarray
    valid_pixel_mask: np.ndarray


@dataclass
class SharedRemapMaps:
    entries: dict = field(default_factory=dict)
    opencv_cuda_maps: dict = field(default_factory=dict)
    cuda_grids: dict = field(default_factory=dict)
    lock: Any = field(default_factory=RLock)


class FisheyeRemapCache:
    def __init__(self, shared_maps: SharedRemapMaps | None = None) -> None:
        self._owns_maps = shared_maps is None
        self.shared_maps = shared_maps if shared_maps is not None else SharedRemapMaps()
        self._entries = self.shared_maps.entries
        self._cuda_grids = self.shared_maps.cuda_grids
        self._cuda_available: bool | None = None
        self._opencv_cuda_available: bool | None = None
        self._opencv_cuda_maps = self.shared_maps.opencv_cuda_maps
        self._opencv_cuda_stream = None
        self.backend_counts = {"gpu": 0, "cpu": 0}

    def get(self, snapshot: Mapping[str, Any]) -> RemapEntry:
        with self.shared_maps.lock:
            return self._get(snapshot)

    def _get(self, snapshot: Mapping[str, Any]) -> RemapEntry:
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
        if self._opencv_cuda_available is not False:
            try:
                self._opencv_cuda_available = cv2.cuda.getCudaEnabledDeviceCount() > 0 and hasattr(cv2.cuda, "remap")
                if self._opencv_cuda_available:
                    with self.shared_maps.lock:
                        maps = self._opencv_cuda_maps.get(id(entry))
                        if maps is None:
                            map_x, map_y = cv2.cuda_GpuMat(), cv2.cuda_GpuMat()
                            map_x.upload(np.rint(entry.map_x * 32) / 32)
                            map_y.upload(np.rint(entry.map_y * 32) / 32)
                            maps = (map_x, map_y)
                            self._opencv_cuda_maps[id(entry)] = maps
                    source = cv2.cuda_GpuMat()
                    if self._opencv_cuda_stream is None:
                        self._opencv_cuda_stream = cv2.cuda_Stream()
                    stream = self._opencv_cuda_stream
                    source.upload(image, stream)
                    result = cv2.cuda.remap(source, *maps, cv2.INTER_LINEAR,
                                            borderMode=cv2.BORDER_CONSTANT, stream=stream)
                    output = result.download(stream=stream)
                    stream.waitForCompletion()
                    self.backend_counts["gpu"] += 1
                    return output, entry.valid_pixel_mask.copy()
            except Exception:
                self._opencv_cuda_available = False
                if self._owns_maps:
                    self._opencv_cuda_maps.clear()
                logger.warning("OpenCV CUDA remapping failed; trying PyTorch CUDA", exc_info=True)
        if self._cuda_available is not False:
            try:
                import torch
                import torch.nn.functional as functional

                self._cuda_available = torch.cuda.is_available()
                if self._cuda_available:
                    height, width = image.shape[:2]
                    with self.shared_maps.lock:
                        grid = self._cuda_grids.get(id(entry))
                        if grid is None:
                            # OpenCV INTER_LINEAR uses a 1/32-pixel interpolation table.
                            x = np.rint(entry.map_x * 32) / 32
                            y = np.rint(entry.map_y * 32) / 32
                            grid = torch.from_numpy(np.stack((
                                x * 2 / max(width - 1, 1) - 1,
                                y * 2 / max(height - 1, 1) - 1,
                            ), axis=-1)).to("cuda").unsqueeze(0)
                            self._cuda_grids[id(entry)] = grid
                    channels = image[:, :, None] if image.ndim == 2 else image
                    tensor = torch.from_numpy(np.ascontiguousarray(channels)).to("cuda", dtype=torch.float32)
                    with torch.inference_mode():
                        result = functional.grid_sample(
                            tensor.permute(2, 0, 1).unsqueeze(0), grid,
                            mode="bilinear", padding_mode="zeros", align_corners=True,
                        )[0].permute(1, 2, 0)
                        if np.issubdtype(image.dtype, np.integer):
                            result = result.round().clamp(0, np.iinfo(image.dtype).max)
                        output = result.cpu().numpy().astype(image.dtype)
                    self.backend_counts["gpu"] += 1
                    return (output[:, :, 0] if image.ndim == 2 else output), entry.valid_pixel_mask.copy()
            except Exception:
                self._cuda_available = False
                if self._owns_maps:
                    self._cuda_grids.clear()
                logger.warning("CUDA remapping failed; using OpenCV CPU remapping", exc_info=True)
        undistorted = cv2.remap(
            image,
            entry.map_x,
            entry.map_y,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
        )
        self.backend_counts["cpu"] += 1
        return undistorted, entry.valid_pixel_mask.copy()

    def close(self) -> None:
        if self._owns_maps:
            self._opencv_cuda_maps.clear()
            self._cuda_grids.clear()
            self._entries.clear()
        self._opencv_cuda_stream = None
