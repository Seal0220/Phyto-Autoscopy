from app.analysis.tracking.temporal_selection import select_temporal_candidate


def test_candidate_selection_classifies_all_temporal_cases() -> None:
    assert select_temporal_candidate([], None).detection_type == "Missing"
    automatic = select_temporal_candidate([(1, 2)], None)
    assert automatic.selected == (1, 2)
    assert automatic.detection_type == "Automatic"
    estimated = select_temporal_candidate([(0, 0), (9, 9)], (8, 8))
    assert estimated.selected == (9, 9)
    assert estimated.detection_type == "Estimated"


def test_first_multiple_candidates_require_manual_initialization() -> None:
    result = select_temporal_candidate([(0, 0), (1, 1)], None)
    assert result.selected is None
    assert result.requires_manual_initialization
