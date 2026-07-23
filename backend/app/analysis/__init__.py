from app.analysis.record_validator import (
    CaptureFrame,
    CaptureRecordValidation,
    CaptureRecordValidator,
    RecordValidationIssue,
    extract_capture_group,
    validate_capture_record,
)

ANALYSIS_METHODS = {
    "round_multiview": {
        "name": "round_multiview",
        "version": "1.0.0",
        "label": "每輪多視角三維重建",
    },
    "top_side_tip_only": {
        "name": "top_side_tip_only",
        "version": "2.0.0",
        "label": "雙鏡頭尖端分析",
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
    "validate_capture_record",
    "ANALYSIS_METHODS",
    "analysis_method",
]
