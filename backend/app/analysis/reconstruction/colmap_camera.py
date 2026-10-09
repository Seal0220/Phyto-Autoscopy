"""Convert calibrated OpenCV pixel coordinates at the COLMAP boundary."""
from __future__ import annotations

import numpy as np


def colmap_pinhole_params(camera_matrix) -> list[float]:
    """COLMAP pixel centers are half-integers; OpenCV centers are integers."""
    matrix = np.asarray(camera_matrix, dtype=float)
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all() or min(matrix[0, 0], matrix[1, 1]) <= 0:
        raise ValueError("相機內參格式無效。")
    return [float(matrix[0, 0]), float(matrix[1, 1]),
            float(matrix[0, 2] + .5), float(matrix[1, 2] + .5)]
