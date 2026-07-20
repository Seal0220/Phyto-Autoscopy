from __future__ import annotations

from app.calibration.camera_models import compare_camera_models
from app.calibration.quality_metrics import (
    MINIMUM_INTRINSIC_SAMPLES,
    intrinsic_quality_status,
    sample_coverage,
)
from app.models.calibration_models import IntrinsicRun


def solve_intrinsic_run(
    run: IntrinsicRun,
) -> tuple[dict[str, dict], dict]:
    accepted = [sample for sample in run.samples if sample.accepted]
    if len(accepted) < MINIMUM_INTRINSIC_SAMPLES:
        raise ValueError(
            f"{run.camera_id} 內參校正至少需要 {MINIMUM_INTRINSIC_SAMPLES} 張有效樣本，"
            f"目前只有 {len(accepted)} 張。"
        )
    resolutions = {tuple(sample.resolution) for sample in accepted}
    if len(resolutions) != 1:
        raise ValueError(f"{run.camera_id} 內參樣本解析度不一致，請重新建立校正工作。")
    width, height = next(iter(resolutions))
    coverage = sample_coverage(accepted)
    if not coverage["ready"]:
        raise ValueError(
            f"{run.camera_id} 內參樣本覆蓋或姿態多樣性不足，"
            "請補拍畫面邊緣、不同距離與不同傾斜角度。"
        )
    candidates, selected = compare_camera_models(
        accepted,
        (int(width), int(height)),
        run.requested_camera_model,
    )
    candidate_payloads = {
        name: result.to_dict()
        for name, result in candidates.items()
    }
    selected_payload = selected.to_dict()
    selected_payload["width"] = int(width)
    selected_payload["height"] = int(height)
    selected_payload["sample_count"] = len(accepted)
    selected_payload["coverage"] = coverage
    selected_payload["quality_status"] = intrinsic_quality_status(
        selected.reprojection_error_px,
        selected.validation_error_px,
        coverage,
    )
    return candidate_payloads, selected_payload
