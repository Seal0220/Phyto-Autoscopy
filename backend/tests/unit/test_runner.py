from __future__ import annotations

from argparse import Namespace

import pytest

import run


@pytest.mark.parametrize(
    ("mock", "expected"),
    [
        (False, "0"),
        (True, "1"),
    ],
)
def test_runner_sets_hardware_mode_explicitly(
    monkeypatch,
    mock: bool,
    expected: str,
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
            mock=mock,
            reload=False,
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

    assert run.os.environ["PHYTO_AUTOSCOPY_MOCK"] == expected
    assert len(calls) == 1
