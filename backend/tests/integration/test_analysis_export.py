from __future__ import annotations

import json
import re
import zipfile

from tests.integration.analysis_test_support import (
    assert_raw_unchanged,
    create_analysis_service,
    create_validated_run,
    wait_for_status,
)


REQUIRED_EXPORTS = {
    "analysis.json",
    "parameters.json",
    "frame_pairs.csv",
    "top_detections.csv",
    "side_detections.csv",
    "manual_corrections.json",
    "resolved_top_positions.csv",
    "resolved_side_positions.csv",
    "trajectory_3d.csv",
    "reprojection_errors.csv",
    "detection_summary.json",
    "calibration_reference.json",
}
FORMAL_RESULT_EXPORTS = {
    "trajectory_3d.csv",
    "reprojection_errors.csv",
    "detection_summary.json",
    "reconstruction/trajectory_3d.csv",
    "reconstruction/reprojection_errors.csv",
    "summaries/detection_summary.json",
}
PAPER_COMPARISON_NOTICE = (
    "論文報告值僅供方法比較，不代表本次結果通過或保證相同表現。"
)
CONSCIOUSNESS_CLAIMS = (
    re.compile(r"植物(?:是|為|具有|有|沒有|不具有|無)意識"),
    re.compile(
        r"\bplants?\s+(?:is|are|has|have|does\s+not\s+have|"
        r"is\s+not|are\s+not)\s+conscious(?:ness)?\b",
        re.IGNORECASE,
    ),
)


def _assert_no_consciousness_contract(value) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).lower()
            assert "conscious" not in normalized_key
            assert "意識" not in normalized_key
            _assert_no_consciousness_contract(item)
        return
    if isinstance(value, list):
        for item in value:
            _assert_no_consciousness_contract(item)
        return
    if not isinstance(value, str):
        return
    for pattern in CONSCIOUSNESS_CLAIMS:
        assert pattern.search(value) is None


def test_completed_analysis_exports_flat_and_grouped_contracts(
    tmp_path,
    monkeypatch,
) -> None:
    service, dataset = create_analysis_service(tmp_path, monkeypatch)
    try:
        run = create_validated_run(service, manual_review_required=False)
        service.start(run.analysis_id)
        completed = wait_for_status(service, run.analysis_id, {"completed", "failed"})
        assert completed.status == "completed", completed.last_error

        output = service.settings.paths.analysis_dir / run.record_id / run.analysis_id
        assert REQUIRED_EXPORTS.issubset({path.name for path in output.iterdir()})
        assert (output / "detections" / "top_automatic.csv").is_file()
        assert (output / "detections" / "resolved_side.csv").is_file()
        assert (output / "reconstruction" / "trajectory_3d.csv").is_file()
        assert (output / "summaries" / "detection_summary.json").is_file()
        assert (output / "logs" / "analysis.log").is_file()

        summary = json.loads(
            (output / "detection_summary.json").read_text(encoding="utf-8")
        )
        assert set(summary["top"]) == {
            "Automatic",
            "Estimated",
            "Interpolated",
            "Manual",
            "Missing",
            "Invalid",
        }
        assert summary["paper_comparison_notice"] == PAPER_COMPARISON_NOTICE

        result_interface = {
            "trajectory": [
                item.model_dump(mode="json")
                for item in service.get_trajectory(run.analysis_id)
            ],
            "reprojection_errors": [
                item.model_dump(mode="json")
                for item in service.get_reprojection_errors(run.analysis_id)
            ],
            "detection_summary": service.get_detection_summary(
                run.analysis_id
            ).model_dump(mode="json"),
        }
        assert (
            result_interface["detection_summary"]["paper_comparison_notice"]
            == PAPER_COMPARISON_NOTICE
        )
        _assert_no_consciousness_contract(result_interface)

        for relative_path in FORMAL_RESULT_EXPORTS:
            exported_text = (output / relative_path).read_text(encoding="utf-8-sig")
            for pattern in CONSCIOUSNESS_CLAIMS:
                assert pattern.search(exported_text) is None

        archive_path = service.export(run.analysis_id)
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            assert REQUIRED_EXPORTS.issubset(names)
            assert FORMAL_RESULT_EXPORTS.issubset(names)
            assert "logs/analysis.log" in names
            for relative_path in FORMAL_RESULT_EXPORTS:
                exported_text = archive.read(relative_path).decode("utf-8-sig")
                for pattern in CONSCIOUSNESS_CLAIMS:
                    assert pattern.search(exported_text) is None
        assert_raw_unchanged(dataset)
    finally:
        service.close()
        dataset["database"].close()
