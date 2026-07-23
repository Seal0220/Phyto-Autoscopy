from __future__ import annotations

import ast
from pathlib import Path
import re
import tomllib


BACKEND_ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_SOURCES = (
    *sorted((BACKEND_ROOT / "app" / "analysis").rglob("*.py")),
    BACKEND_ROOT / "app" / "services" / "analysis_service.py",
)

FORBIDDEN_DEPENDENCIES = {
    "deep-sort-realtime",
    "detectron2",
    "diff-gaussian-rasterization",
    "filterpy",
    "flax",
    "jax",
    "keras",
    "mmdet",
    "mmtrack",
    "onnxruntime",
    "scikit-learn",
    "tensorflow",
    "transformers",
    "ultralytics",
}
FORBIDDEN_IDENTIFIER_FRAGMENTS = (
    "behavior_classifier",
    "botsort",
    "bytetrack",
    "deep_sort",
    "deepsort",
    "gaussian_splat",
    "gaussiansplat",
    "kalman",
    "opticalflow",
    "tracker",
)


def _dependency_name(requirement: str) -> str:
    name = re.split(r"[<>=!~;\[\s]", requirement.strip(), maxsplit=1)[0]
    return name.lower().replace("_", "-")


def _analysis_ast_identifiers() -> dict[Path, set[str]]:
    identifiers = {}
    for path in ANALYSIS_SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        values = {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
        }
        values.update(
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                values.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    values.add(node.module)
                values.update(alias.name for alias in node.names)
        identifiers[path] = values
    return identifiers


def test_analysis_dependencies_exclude_disallowed_tracking_methods() -> None:
    project = tomllib.loads(
        (BACKEND_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    declared = {
        _dependency_name(item)
        for item in project["project"]["dependencies"]
    }
    requirements = {
        _dependency_name(line)
        for line in (BACKEND_ROOT / "requirements.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert declared.isdisjoint(FORBIDDEN_DEPENDENCIES)
    assert requirements.isdisjoint(FORBIDDEN_DEPENDENCIES)


def test_analysis_python_ast_excludes_disallowed_trackers() -> None:
    violations = {}
    for path, identifiers in _analysis_ast_identifiers().items():
        matches = sorted({
            identifier
            for identifier in identifiers
            if any(
                fragment.replace("_", "")
                in identifier.lower().replace("_", "")
                for fragment in FORBIDDEN_IDENTIFIER_FRAGMENTS
            )
        })
        if matches:
            violations[str(path.relative_to(BACKEND_ROOT))] = matches

    assert violations == {}
