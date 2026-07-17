from app.analysis.frame_pairing import pair_capture_frames
from app.analysis.record_validator import (
    CaptureFrame,
    CaptureRecordValidation,
    CaptureRecordValidator,
    RecordValidationIssue,
    extract_capture_group,
    validate_capture_record,
)

ANALYSIS_METHODS = {
    "top_side": {
        "name": "top_side",
        "version": "1.0.0",
        "label": "頂+側",
    },
    "top_side_rotating": {
        "name": "top_side_rotating",
        "version": "1.0.0",
        "label": "頂+側+環繞",
    },
}


def analysis_method(method: str) -> dict[str, str]:
    try:
        return dict(ANALYSIS_METHODS[method])
    except KeyError as error:
        raise ValueError(f"不支援的分析方法：{method}") from error

__all__ = [
    "CaptureFrame",
    "CaptureRecordValidation",
    "CaptureRecordValidator",
    "RecordValidationIssue",
    "extract_capture_group",
    "pair_capture_frames",
    "validate_capture_record",
    "ANALYSIS_METHODS",
    "analysis_method",
]
