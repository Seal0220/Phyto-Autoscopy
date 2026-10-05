from __future__ import annotations

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)
_unsupported_color_codes: set[int] = set()


def convert_color(image: np.ndarray, code: int) -> np.ndarray:
    if code not in _unsupported_color_codes:
        try:
            if cv2.cuda.getCudaEnabledDeviceCount() > 0 and hasattr(cv2.cuda, "cvtColor"):
                source = cv2.cuda_GpuMat()
                source.upload(image)
                return cv2.cuda.cvtColor(source, code).download()
        except cv2.error:
            # CUDA does not implement every OpenCV color space (e.g. Lab).
            _unsupported_color_codes.add(code)
    return cv2.cvtColor(image, code)


def detect_orb_features(image: np.ndarray, count: int):
    try:
        if cv2.cuda.getCudaEnabledDeviceCount() > 0 and hasattr(cv2, "cuda_ORB"):
            detector = cv2.cuda_ORB.create(nfeatures=count)
            source = cv2.cuda_GpuMat()
            source.upload(image)
            points, descriptors = detector.detectAndComputeAsync(source, None)
            return detector.convert(points), descriptors.download(), "cuda"
    except cv2.error:
        logger.warning("CUDA ORB failed; using CPU features", exc_info=True)
    points, descriptors = cv2.ORB_create(nfeatures=count).detectAndCompute(image, None)
    return points, descriptors, "cpu"


def cuda_hamming_matches(first: np.ndarray, second: np.ndarray, *, reciprocal: bool = True):
    """Exact ORB Hamming distances, ratio test and reciprocal matching on CUDA."""
    if min(len(first), len(second)) < 2:
        return []
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        with torch.inference_mode():
            left = torch.from_numpy(np.ascontiguousarray(first)).to("cuda")
            right = torch.from_numpy(np.ascontiguousarray(second)).to("cuda")
            table = torch.tensor([value.bit_count() for value in range(256)], dtype=torch.uint8, device="cuda")
            distances = torch.empty((len(first), len(second)), dtype=torch.int16, device="cuda")
            for start in range(0, len(first), 32):
                xor = torch.bitwise_xor(left[start:start + 32, None, :], right[None, :, :])
                distances[start:start + 32] = table[xor.long()].sum(dim=-1).to(torch.int16)

            def nearest(values):
                best, indices = values.min(dim=1)
                other = values.clone()
                other.scatter_(1, indices[:, None], 32767)
                runner_up = other.min(dim=1).values
                return indices, best, best.float() < runner_up.float() * .75

            forward, distance, forward_valid = nearest(distances)
            rows = torch.arange(len(first), device="cuda")
            accepted = forward_valid
            if reciprocal:
                backward, _, backward_valid = nearest(distances.T)
                accepted = accepted & backward_valid[forward] & (backward[forward] == rows)
            indices = rows[accepted].cpu().tolist()
            columns = forward[accepted].cpu().tolist()
            costs = distance[accepted].cpu().tolist()
        return [cv2.DMatch(int(row), int(column), float(cost)) for row, column, cost in zip(indices, columns, costs)]
    except Exception:
        logger.warning("CUDA feature matching failed; using CPU matching", exc_info=True)
        return None


def binary_morphology(mask: np.ndarray, opening: np.ndarray, closing: np.ndarray) -> np.ndarray:
    try:
        if cv2.cuda.getCudaEnabledDeviceCount() > 0 and hasattr(cv2.cuda, "createMorphologyFilter"):
            source = cv2.cuda_GpuMat()
            source.upload(mask)
            opened = cv2.cuda.createMorphologyFilter(cv2.MORPH_OPEN, cv2.CV_8UC1, opening).apply(source)
            return cv2.cuda.createMorphologyFilter(cv2.MORPH_CLOSE, cv2.CV_8UC1, closing).apply(opened).download()
    except cv2.error:
        logger.warning("OpenCV CUDA morphology failed; trying PyTorch CUDA", exc_info=True)
    try:
        import torch
        import torch.nn.functional as functional

        if torch.cuda.is_available():
            with torch.inference_mode():
                value = torch.from_numpy((mask > 0).astype(np.float32)).to("cuda")[None, None]

                def morph(value, kernel, erosion):
                    weight = torch.from_numpy(kernel.astype(np.float32)).to("cuda")[None, None]
                    y, x = kernel.shape[0] // 2, kernel.shape[1] // 2
                    padded = functional.pad(value, (x, x, y, y), value=1.0 if erosion else 0.0)
                    count = functional.conv2d(padded, weight)
                    return (count >= float(kernel.sum()) if erosion else count > 0).float()

                value = morph(morph(value, opening, True), opening, False)
                value = morph(morph(value, closing, False), closing, True)
                return (value[0, 0].cpu().numpy() * 255).astype(np.uint8)
    except Exception:
        logger.warning("CUDA mask morphology failed; using CPU morphology", exc_info=True)
    result = cv2.morphologyEx(mask, cv2.MORPH_OPEN, opening)
    return cv2.morphologyEx(result, cv2.MORPH_CLOSE, closing)


def cuda_projection_support(points: np.ndarray, projections_and_masks):
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        with torch.inference_mode():
            coordinates = torch.from_numpy(np.ascontiguousarray(points)).to("cuda", dtype=torch.float64)
            homogeneous = torch.cat((coordinates, torch.ones((len(points), 1), device="cuda", dtype=torch.float64)), dim=1)
            support = torch.zeros(len(points), device="cuda", dtype=torch.int16)
            visibility = torch.zeros_like(support)
            for projection, mask in projections_and_masks:
                pixels = homogeneous @ torch.as_tensor(projection, device="cuda", dtype=torch.float64).T
                depth = pixels[:, 2]
                valid_depth = depth > 1e-8
                denominator = torch.where(valid_depth, depth, 1.0)
                x = torch.round(pixels[:, 0] / denominator).long()
                y = torch.round(pixels[:, 1] / denominator).long()
                height, width = mask.shape
                visible = valid_depth & (x >= 0) & (x < width) & (y >= 0) & (y < height)
                indices = torch.where(visible)[0]
                visibility[indices] += 1
                gpu_mask = torch.as_tensor(mask, device="cuda")
                supported = indices[gpu_mask[y[indices], x[indices]]]
                support[supported] += 1
            return support.cpu().numpy(), visibility.cpu().numpy()
    except Exception:
        logger.warning("CUDA point projection failed; using CPU projection", exc_info=True)
        return None
