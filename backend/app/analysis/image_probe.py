from __future__ import annotations

import logging
from pathlib import Path


logger = logging.getLogger(__name__)


def probe_image_cpu(path: Path) -> tuple[int, int] | None:
    """Fully decode an image, not just its header, before accepting it."""
    try:
        import cv2  # type: ignore
        import numpy as np

        encoded = np.fromfile(path, dtype=np.uint8)
        if encoded.size == 0:
            return None
        image = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
        if image is None or image.ndim < 2:
            return None
        height, width = image.shape[:2]
        if width <= 0 or height <= 0:
            return None
        return int(width), int(height)
    except (ImportError, OSError, ValueError):
        return None


class AnalysisImageProbe:
    """Use nvTIFF on CUDA for TIFF; retain CPU decoding for legacy PNG."""

    def __init__(self) -> None:
        self.gpu_decoded = 0
        self.cpu_decoded = 0
        self._gpu_decoder = None
        self._gpu_failures = 0
        try:
            from nvidia import nvimgcodec

            self._gpu_decoder = nvimgcodec.Decoder(
                device_id=0,
                backends=[nvimgcodec.Backend(nvimgcodec.BackendKind.GPU_ONLY)],
            )
        except Exception:
            logger.info(
                "GPU TIFF decoder unavailable; using CPU image validation",
                exc_info=True,
            )

    def __call__(self, path: Path) -> tuple[int, int] | None:
        if path.suffix.lower() in {".tif", ".tiff"} and self._gpu_decoder is not None:
            try:
                image = self._gpu_decoder.read(str(path))
                if image is not None and image.width > 0 and image.height > 0:
                    self.gpu_decoded += 1
                    self._gpu_failures = 0
                    return int(image.width), int(image.height)
            except Exception:
                logger.warning("GPU TIFF decoding failed; falling back to CPU", exc_info=True)
            self._gpu_failures += 1
            if self._gpu_failures >= 3:
                self._gpu_decoder = None

        resolution = probe_image_cpu(path)
        if resolution is not None:
            self.cpu_decoded += 1
        return resolution

    @property
    def backend_counts(self) -> dict[str, int]:
        return {
            "gpu": self.gpu_decoded,
            "cpu": self.cpu_decoded,
        }
