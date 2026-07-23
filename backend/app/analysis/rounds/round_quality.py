from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import cv2
import numpy as np

from app.models.analysis_models import AnalysisView


@dataclass(frozen=True, slots=True)
class ViewImageQuality:
    view_id: str
    sharpness: float
    mean_luminance: float
    underexposed_ratio: float
    overexposed_ratio: float
    selection_score: float

    def as_dict(self) -> dict[str, float | str]:
        return {
            "view_id": self.view_id,
            "sharpness": self.sharpness,
            "mean_luminance": self.mean_luminance,
            "underexposed_ratio": self.underexposed_ratio,
            "overexposed_ratio": self.overexposed_ratio,
            "selection_score": self.selection_score,
        }


@dataclass(frozen=True, slots=True)
class RoundQualityResult:
    round_key: str
    static_scene_score: float | None
    fixed_camera_change_score: dict[str, float]
    luminance_range: float | None
    view_quality: dict[str, ViewImageQuality]
    warnings: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "round_key": self.round_key,
            "static_scene_score": self.static_scene_score,
            "fixed_camera_change_score": self.fixed_camera_change_score,
            "luminance_range": self.luminance_range,
            "view_quality": {
                view_id: quality.as_dict()
                for view_id, quality in self.view_quality.items()
            },
            "warnings": list(self.warnings),
        }


def _read_grayscale(path: Path) -> np.ndarray:
    encoded = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"分析衍生影像無法讀取：{path.name}")
    return image


def _quality_for_image(
    view_id: str,
    image: np.ndarray,
) -> ViewImageQuality:
    pixels = image.reshape(-1)
    sharpness = float(cv2.Laplacian(image, cv2.CV_64F).var())
    mean_luminance = float(np.mean(pixels))
    underexposed = float(np.mean(pixels <= 8))
    overexposed = float(np.mean(pixels >= 247))
    exposure_penalty = abs(mean_luminance - 127.5) / 127.5
    clipping_penalty = min(1.0, underexposed + overexposed)
    selection_score = float(
        np.log1p(max(sharpness, 0.0))
        - exposure_penalty
        - clipping_penalty * 2.0
    )
    return ViewImageQuality(
        view_id=view_id,
        sharpness=sharpness,
        mean_luminance=mean_luminance,
        underexposed_ratio=underexposed,
        overexposed_ratio=overexposed,
        selection_score=selection_score,
    )


def _normalized_change(
    first: np.ndarray,
    second: np.ndarray,
) -> float:
    size = (256, 256)
    left = cv2.resize(first, size, interpolation=cv2.INTER_AREA).astype(
        np.float32
    )
    right = cv2.resize(second, size, interpolation=cv2.INTER_AREA).astype(
        np.float32
    )
    left = (left - float(left.mean())) / max(float(left.std()), 1.0)
    right = (right - float(right.mean())) / max(float(right.std()), 1.0)
    difference = float(np.mean(np.abs(left - right)))
    return min(1.0, difference / 3.0)


def evaluate_round_quality(
    round_key: str,
    views: Sequence[AnalysisView],
    derived_paths: Mapping[str, Path],
) -> RoundQualityResult:
    images: dict[str, np.ndarray] = {}
    qualities: dict[str, ViewImageQuality] = {}
    for view in views:
        path = derived_paths.get(view.view_id)
        if path is None:
            continue
        image = _read_grayscale(path)
        images[view.view_id] = image
        qualities[view.view_id] = _quality_for_image(view.view_id, image)

    fixed_change: dict[str, float] = {}
    for camera_id in ("top", "side"):
        camera_views = [
            view
            for view in views
            if view.camera_id == camera_id and view.view_id in images
        ]
        if len(camera_views) < 2:
            continue
        ordered = sorted(camera_views, key=lambda item: item.timestamp)
        changes = [
            _normalized_change(
                images[left.view_id],
                images[right.view_id],
            )
            for left, right in zip(ordered, ordered[1:])
        ]
        fixed_change[camera_id] = float(np.median(changes))

    static_scene_score = None
    if fixed_change:
        static_scene_score = max(
            0.0,
            min(1.0, 1.0 - float(np.mean(list(fixed_change.values())))),
        )
    luminance_values = [
        quality.mean_luminance
        for quality in qualities.values()
    ]
    luminance_range = (
        max(luminance_values) - min(luminance_values)
        if luminance_values
        else None
    )
    warnings: list[str] = []
    if static_scene_score is not None and static_scene_score < 0.8:
        warnings.append(
            "同一輪固定攝影機影像變化較大，植物可能移動或震動。"
        )
    if luminance_range is not None and luminance_range > 50:
        warnings.append("同一輪影像亮度變化較大，模型可能受曝光變化影響。")
    if any(
        quality.underexposed_ratio + quality.overexposed_ratio > 0.2
        for quality in qualities.values()
    ):
        warnings.append("部分影像具有明顯過暗或過曝區域。")

    return RoundQualityResult(
        round_key=round_key,
        static_scene_score=static_scene_score,
        fixed_camera_change_score=fixed_change,
        luminance_range=luminance_range,
        view_quality=qualities,
        warnings=tuple(warnings),
    )
