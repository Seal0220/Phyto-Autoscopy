import numpy as np

from app.analysis.segmentation.mog2_background import Mog2BackgroundSegmenter


def build_segmenter(**overrides) -> Mog2BackgroundSegmenter:
    parameters = {
        "history": 5,
        "variance_threshold": 16,
        "detect_shadows": False,
        "initialization_frames": 2,
        "opening_kernel_size": None,
        "closing_kernel_size": None,
        "erosion_kernel_size": None,
        "minimum_contour_area_px": 4,
        "lighting_change_area_px": 10_000,
        "lighting_change_est_time_frames": 2,
    }
    parameters.update(overrides)
    return Mog2BackgroundSegmenter(**parameters)


def test_mog2_initialization_does_not_expose_contours() -> None:
    segmenter = build_segmenter()
    image = np.zeros((40, 40, 3), dtype=np.uint8)

    first = segmenter.process(image, learning_rate=0.5)
    second = segmenter.process(image, learning_rate=0.5)

    assert first.status == "background_initialization"
    assert second.status == "background_initialization"
    assert first.contours == []


def test_mog2_respects_roi_and_detects_moving_foreground() -> None:
    segmenter = build_segmenter(initialization_frames=1)
    background = np.zeros((40, 40, 3), dtype=np.uint8)
    segmenter.process(background, roi=(10, 10, 20, 20), learning_rate=1)
    foreground = background.copy()
    foreground[15:22, 15:22] = 255

    result = segmenter.process(
        foreground,
        roi=(10, 10, 20, 20),
        learning_rate=0,
    )

    assert result.status == "ready"
    assert result.roi_origin == (10, 10)
    assert result.mask.shape == (20, 20)
    assert result.contours


def test_lighting_transition_status_is_retained_after_background_reset() -> None:
    segmenter = build_segmenter(
        initialization_frames=1,
        lighting_change_area_px=20,
        lighting_change_est_time_frames=2,
    )
    background = np.zeros((40, 40, 3), dtype=np.uint8)
    segmenter.process(background, learning_rate=1)
    changed = background.copy()
    changed[5:30, 5:30] = 255

    triggered = segmenter.process(changed, learning_rate=0)
    first_wait = segmenter.process(changed, learning_rate=1)
    second_wait = segmenter.process(changed, learning_rate=1)

    assert triggered.status == "lighting_transition"
    assert first_wait.status == "lighting_transition"
    assert second_wait.status == "lighting_transition"
