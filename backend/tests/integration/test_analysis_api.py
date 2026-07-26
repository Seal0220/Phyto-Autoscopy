from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from app.models.analysis_models import AnalysisRun

from .test_support import authorized_headers, write_test_config


@pytest.mark.parametrize(
    ("request_body", "expected_manual_review_completed"),
    [
        (None, True),
        ({"manual_review_completed": False}, False),
    ],
)
def test_reconstruct_api_accepts_explicit_review_completion_state(
    tmp_path,
    monkeypatch,
    request_body,
    expected_manual_review_completed,
) -> None:
    write_test_config(tmp_path, monkeypatch)
    received = []

    with TestClient(create_app(), headers=authorized_headers()) as client:
        analysis_service = client.app.state.context.analysis_service

        def reconstruct(analysis_id, manual_review_completed=True):
            received.append((analysis_id, manual_review_completed))
            return AnalysisRun(
                analysis_id=analysis_id,
                record_id="record-test",
                method_name="rotating",
                method_version="1.0.0",
                git_commit="test",
                parameters={},
                created_at="2026-07-17T00:00:00+00:00",
                updated_at="2026-07-17T00:00:00+00:00",
                created_by="pytest-operator",
                output_path="analysis-test",
                status="reconstructing",
                stage="reconstructing_round_model",
                progress=0.72,
                manual_review_completed=manual_review_completed,
            )

        monkeypatch.setattr(analysis_service, "reconstruct", reconstruct)
        request_kwargs = (
            {"json": request_body}
            if request_body is not None
            else {}
        )
        response = client.post(
            "/api/analysis/analysis-test/reconstruct",
            **request_kwargs,
        )

    assert response.status_code == 200
    assert received == [
        ("analysis-test", expected_manual_review_completed),
    ]
    assert response.json()["manual_review_completed"] is (
        expected_manual_review_completed
    )
