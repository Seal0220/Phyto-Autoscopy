from __future__ import annotations

import cv2
import numpy as np

from app.calibration.resolution_adaptation import scale_camera_matrix
from app.core.exceptions import CalibrationError


class LiveFrameUndistorter:
    def __init__(self, intrinsics: object) -> None:
        self.camera_model = str(intrinsics.camera_model)
        self.source_resolution = (
            int(intrinsics.width),
            int(intrinsics.height),
        )
        self.camera_matrix = np.asarray(
            intrinsics.camera_matrix,
            dtype=np.float64,
        )
        self.distortion = np.asarray(
            intrinsics.distortion_coefficients,
            dtype=np.float64,
        ).reshape(-1, 1)
        self._maps: dict[
            tuple[int, int],
            tuple[np.ndarray, np.ndarray],
        ] = {}

    def _undistortion_maps(
        self,
        resolution: tuple[int, int],
    ) -> tuple[np.ndarray, np.ndarray]:
        cached = self._maps.get(resolution)
        if cached is not None:
            return cached

        matrix = scale_camera_matrix(
            self.camera_matrix,
            self.source_resolution,
            resolution,
        )
        if self.camera_model == "opencv_fisheye":
            maps = cv2.fisheye.initUndistortRectifyMap(
                matrix,
                self.distortion,
                np.eye(3, dtype=np.float64),
                matrix,
                resolution,
                cv2.CV_16SC2,
            )
        else:
            maps = cv2.initUndistortRectifyMap(
                matrix,
                self.distortion,
                None,
                matrix,
                resolution,
                cv2.CV_16SC2,
            )
        self._maps[resolution] = maps
        return maps

    def apply(self, jpeg_data: bytes) -> bytes:
        image = cv2.imdecode(
            np.frombuffer(jpeg_data, dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )
        if image is None:
            raise CalibrationError("即時影像無法解碼，不能套用去畸變。")

        height, width = image.shape[:2]
        maps = self._undistortion_maps((width, height))
        undistorted = cv2.remap(
            image,
            maps[0],
            maps[1],
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
        )
        encoded, buffer = cv2.imencode(
            ".jpg",
            undistorted,
            [cv2.IMWRITE_JPEG_QUALITY, 90],
        )
        if not encoded:
            raise CalibrationError("去畸變影像無法編碼。")
        return buffer.tobytes()
