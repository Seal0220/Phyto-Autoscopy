from __future__ import annotations

import logging
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import local
from uuid import uuid4

import cv2
import numpy as np

from app.analysis.gpu_operations import convert_color


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
    """Convert unsupported inputs losslessly to TIFF, then prefer CUDA decoding."""

    GPU_EXTENSIONS = frozenset({".tif", ".tiff"})

    def __init__(self, cache_root: Path | None = None, *, initialize_decoder: bool = True) -> None:
        self.gpu_decoded = 0
        self.cpu_decoded = 0
        self.converted = 0
        self.conversion_failed = 0
        self._temporary_cache = TemporaryDirectory(prefix="phyto_analysis_tiff_") if cache_root is None else None
        self.cache_root = cache_root if cache_root is not None else Path(self._temporary_cache.name)
        self._gpu_decoder = None
        self._decode_params = None
        self._gpu_failures: dict[str, int] = {}
        self._gpu_initialized = False
        if initialize_decoder:
            self._initialize_decoder()

    def _initialize_decoder(self) -> None:
        self._gpu_initialized = True
        try:
            from nvidia import nvimgcodec

            self._gpu_decoder = nvimgcodec.Decoder(
                device_id=0,
                max_num_cpu_threads=2,
                backends=[nvimgcodec.Backend(nvimgcodec.BackendKind.GPU_ONLY)],
            )
            self._decode_params = nvimgcodec.DecodeParams(
                apply_exif_orientation=False,
                allow_any_depth=True,
                color_spec=nvimgcodec.ColorSpec.UNCHANGED,
                sample_format=nvimgcodec.SampleFormat.I_UNCHANGED,
            )
        except Exception:
            self._gpu_decoder = None
            logger.info(
                "GPU image decoder unavailable; using CPU image validation",
                exc_info=True,
            )

    def close(self) -> None:
        decoder, self._gpu_decoder = self._gpu_decoder, None
        if decoder is not None:
            decoder.__exit__(None, None, None)
        if self._temporary_cache is not None:
            self._temporary_cache.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def prepare(self, path: Path, *, image: np.ndarray | None = None) -> Path:
        if path.suffix.lower() in self.GPU_EXTENSIONS:
            return path
        # Content checks still hash the original file. This identity is only for
        # reusing derived TIFFs when the same immutable source is read again.
        stat = path.stat()
        identity = f"{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}"
        key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        destination = self.cache_root / key[:2] / f"{key}.tiff"
        if destination.is_file():
            return destination
        if image is None:
            image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        if image is None:
            raise ValueError(f"影像無法轉成 TIFF：{path.name}")
        # LZW is lossless and supported by nvTIFF; preserve channels and bit depth.
        success, encoded = cv2.imencode(".tiff", image, [cv2.IMWRITE_TIFF_COMPRESSION, 5])
        if not success:
            raise ValueError(f"TIFF 編碼失敗：{path.name}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{key}.{uuid4().hex}.tmp")
        try:
            encoded.tofile(temporary)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        self.converted += 1
        return destination

    def _prepare_or_original(self, path: Path) -> Path:
        try:
            return self.prepare(path)
        except (OSError, ValueError, cv2.error):
            self.conversion_failed += 1
            logger.warning("TIFF conversion failed; falling back to source CPU decoding", exc_info=True)
            return path

    def _decode_gpu(self, path: Path):
        extension = path.suffix.lower()
        if extension in self.GPU_EXTENSIONS and not self._gpu_initialized:
            self._initialize_decoder()
        if (
            extension in self.GPU_EXTENSIONS
            and self._gpu_decoder is not None
            and self._gpu_failures.get(extension, 0) < 3
        ):
            try:
                image = self._gpu_decoder.read(str(path), params=self._decode_params)
                if image is not None and image.width > 0 and image.height > 0:
                    self._gpu_failures[extension] = 0
                    return image
            except Exception:
                logger.warning("GPU image decoding failed; falling back to CPU", exc_info=True)
            self._gpu_failures[extension] = self._gpu_failures.get(extension, 0) + 1
        return None

    def __call__(self, path: Path) -> tuple[int, int] | None:
        prepared = self._prepare_or_original(path)
        image = self._decode_gpu(prepared)
        if image is not None:
            self.gpu_decoded += 1
            return int(image.width), int(image.height)

        resolution = probe_image_cpu(prepared)
        if resolution is None and prepared != path:
            resolution = probe_image_cpu(path)
        if resolution is not None:
            self.cpu_decoded += 1
        return resolution

    def read(self, path: Path, flags: int = cv2.IMREAD_COLOR) -> np.ndarray | None:
        prepared = self._prepare_or_original(path)
        decoded = self._decode_gpu(prepared)
        if decoded is not None:
            try:
                image = np.asarray(decoded.cpu()).copy()
                if image.ndim == 3 and image.shape[2] == 1:
                    image = image[:, :, 0]
                elif image.ndim == 3 and image.shape[2] == 3:
                    image = convert_color(image, cv2.COLOR_RGB2BGR)
                elif image.ndim == 3 and image.shape[2] == 4:
                    image = convert_color(image, cv2.COLOR_RGBA2BGRA)
                if flags != cv2.IMREAD_UNCHANGED:
                    if image.dtype == np.uint16 and not flags & cv2.IMREAD_ANYDEPTH:
                        image = (image >> 8).astype(np.uint8)
                    if flags == cv2.IMREAD_GRAYSCALE and image.ndim == 3:
                        image = convert_color(image, cv2.COLOR_BGR2GRAY)
                    elif flags == cv2.IMREAD_COLOR:
                        if image.ndim == 2:
                            image = convert_color(image, cv2.COLOR_GRAY2BGR)
                        elif image.shape[2] == 4:
                            image = convert_color(image, cv2.COLOR_BGRA2BGR)
                self.gpu_decoded += 1
                return image
            except Exception:
                logger.warning("GPU image transfer failed; falling back to CPU", exc_info=True)
        for candidate in dict.fromkeys((prepared, path)):
            try:
                image = cv2.imdecode(np.fromfile(candidate, dtype=np.uint8), flags)
                if image is not None:
                    self.cpu_decoded += 1
                    return image
            except (OSError, cv2.error):
                continue
        return None

    @property
    def backend_counts(self) -> dict[str, int]:
        return {
            "gpu": self.gpu_decoded,
            "cpu": self.cpu_decoded,
            "converted": self.converted,
            "conversion_failed": self.conversion_failed,
        }


_readers = local()


def read_analysis_image(path: Path, flags: int = cv2.IMREAD_COLOR) -> np.ndarray | None:
    """Shared GPU-first decoding for derived analysis images and model workers."""
    root = next((parent for parent in path.parents if parent.name.startswith("analysis_")), None)
    cache_root = root / "image_cache" if root is not None else None
    reader = getattr(_readers, "reader", None)
    if reader is None or getattr(_readers, "cache_root", None) != cache_root:
        if reader is not None:
            reader.close()
        reader = AnalysisImageProbe(cache_root)
        _readers.reader = reader
        _readers.cache_root = cache_root
    return reader.read(path, flags)
