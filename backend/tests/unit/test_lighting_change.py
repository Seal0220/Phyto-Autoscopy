from app.analysis.segmentation.lighting_change import LightingChangeDetector


def test_lighting_change_triggers_once_and_counts_transition_frames() -> None:
    detector = LightingChangeDetector(
        area_threshold_px=100,
        stabilization_frames=2,
    )

    assert not detector.observe(100).changed
    changed = detector.observe(101)
    assert changed.changed
    assert changed.transitioning
    assert detector.observe(999).transitioning
    last = detector.observe(999)
    assert last.transitioning
    assert last.remaining_frames == 0
    assert detector.observe(50).transitioning is False
