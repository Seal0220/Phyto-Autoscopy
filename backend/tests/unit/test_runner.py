from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import run


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_start_mock_option_only_enables_development_servers() -> None:
    source = (PROJECT_ROOT / "start.bat").read_text(encoding="utf-8")

    assert 'if /I "%~1"=="--mock" (' in source
    assert 'set "MODE=development"' in source
    assert (
        'if /I "%MODE%"=="development" '
        'set "BACKEND_COMMAND=%BACKEND_COMMAND% --reload"'
    ) in source
    assert 'set "MOCK=' not in source
    assert 'BACKEND_COMMAND=%BACKEND_COMMAND% --mock' not in source


def test_runner_keeps_physical_hardware_available_in_development(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PHYTO_AUTOSCOPY_MOCK", "1")
    monkeypatch.setattr(run, "load_runtime_environment", lambda: None)
    monkeypatch.setattr(run, "prepare_runtime_paths", lambda: False)
    monkeypatch.setattr(
        run,
        "parse_args",
        lambda: Namespace(
            host="127.0.0.1",
            port=22222,
            reload=True,
        ),
    )
    calls: list[dict] = []
    monkeypatch.setattr(
        run.uvicorn,
        "run",
        lambda *args, **kwargs: calls.append({
            "args": args,
            "kwargs": kwargs,
        }),
    )

    run.main()

    assert run.os.environ["PHYTO_AUTOSCOPY_MOCK"] == "0"
    assert len(calls) == 1
    assert calls[0]["kwargs"]["reload"] is True
