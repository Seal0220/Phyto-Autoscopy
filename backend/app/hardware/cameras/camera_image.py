from __future__ import annotations

from typing import Any

from app.core.constants import CAPTURE_IMAGE_EXTENSION
from app.core.exceptions import CameraError
from app.hardware.cameras.camera_identifier import load_opencv
from app.hardware.cameras.camera_types import CameraFrame


def encode_lossless_capture(
    frame: CameraFrame,
    *,
    cv2_module: Any | None = None,
) -> bytes:
    """Encode the decoded camera frame as lossless LZW TIFF for persistence."""

    cv2 = cv2_module or load_opencv()
    if cv2 is None:
        raise CameraError("尚未安裝 OpenCV，無法建立無損影像。")

    image = frame.raw_image
    if image is None:
        try:
            import numpy as np

            encoded_source = np.frombuffer(frame.data, dtype=np.uint8)
            image = cv2.imdecode(encoded_source, cv2.IMREAD_UNCHANGED)
        except Exception as exc:
            raise CameraError("相機原始影格無法解碼為無損影像。") from exc

    if image is None:
        raise CameraError("相機原始影格無法解碼為無損影像。")

    return encode_lossless_image(image, cv2_module=cv2)


def encode_lossless_image(
    image: Any,
    *,
    cv2_module: Any | None = None,
) -> bytes:
    cv2 = cv2_module or load_opencv()
    if cv2 is None:
        raise CameraError("尚未安裝 OpenCV，無法建立無損影像。")
    try:
        encoded_ok, encoded = cv2.imencode(
            CAPTURE_IMAGE_EXTENSION,
            image,
            [
                int(cv2.IMWRITE_TIFF_COMPRESSION),
                int(cv2.IMWRITE_TIFF_COMPRESSION_LZW),
            ],
        )
    except Exception as exc:
        raise CameraError("相機影格無損編碼失敗。") from exc

    if not encoded_ok or encoded is None:
        raise CameraError("相機影格無損編碼失敗。")
    return encoded.tobytes()
