import cv2
import numpy as np
import pytest

from app.analysis.reconstruction.colmap_camera import colmap_pinhole_params


def test_opencv_and_colmap_projection_use_the_same_physical_pixel():
    pycolmap = pytest.importorskip("pycolmap")
    matrix = np.array([[700., 0, 639.5], [0, 720, 479.5], [0, 0, 1]])
    original = matrix.copy()
    camera = pycolmap.Camera(model="PINHOLE", width=1280, height=960, params=colmap_pinhole_params(matrix))
    points = np.array([[-.05, .1, .5], [.08, -.12, .6], [0., 0., .7]])
    pixels = cv2.projectPoints(points, np.zeros(3), np.zeros(3), matrix, None)[0].reshape(-1, 2)
    np.testing.assert_allclose(camera.img_from_cam(points), pixels + .5)
    np.testing.assert_array_equal(matrix, original)
    np.testing.assert_array_equal(camera.params, [700., 720., 640., 480.])


@pytest.mark.parametrize("matrix", [np.eye(2), np.full((3, 3), np.nan), np.diag([0., 1., 1.])])
def test_invalid_camera_calibration_is_rejected(matrix):
    with pytest.raises(ValueError, match="內參"):
        colmap_pinhole_params(matrix)
