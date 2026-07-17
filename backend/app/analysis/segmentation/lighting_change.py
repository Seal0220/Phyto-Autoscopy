from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LightingState:
    changed: bool
    transitioning: bool
    remaining_frames: int


class LightingChangeDetector:
    """Area-threshold lighting transition state from Ruiz-Melero et al."""

    def __init__(
        self,
        *,
        area_threshold_px: float,
        stabilization_frames: int,
    ) -> None:
        if area_threshold_px < 0:
            raise ValueError("光照變化面積門檻不可為負值。")
        if stabilization_frames < 1:
            raise ValueError("光照穩定等待影格數至少為 1。")
        self.area_threshold_px = float(area_threshold_px)
        self.stabilization_frames = int(stabilization_frames)
        self._remaining_frames = 0

    @property
    def transitioning(self) -> bool:
        return self._remaining_frames > 0

    def reset(self) -> None:
        self._remaining_frames = 0

    def observe(self, contour_area_px: float) -> LightingState:
        if self._remaining_frames > 0:
            self._remaining_frames -= 1
            return LightingState(
                changed=False,
                transitioning=True,
                remaining_frames=self._remaining_frames,
            )
        if contour_area_px > self.area_threshold_px:
            self._remaining_frames = self.stabilization_frames
            return LightingState(
                changed=True,
                transitioning=True,
                remaining_frames=self._remaining_frames,
            )
        return LightingState(
            changed=False,
            transitioning=False,
            remaining_frames=0,
        )
