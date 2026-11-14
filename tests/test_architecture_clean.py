"""Enforce the refactored SpireMind package DAG and forbid deleted legacy modules."""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "spiremind"

REMOVED_TOP_PACKAGES = {
    "core",
    "decision",
    "application",
    "adapters",
    "learning",
    "evaluation",
    "bootstrap",
}

ALLOWED_LAYER_DEPS: dict[str, set[str]] = {
    "config": {"config"},
    "domain": {"domain"},
    "knowledge": {"domain", "knowledge"},
    "bridge": {"config", "domain", "bridge"},
    "llm": {"config", "domain", "llm"},
    "storage": {"config", "domain", "storage"},
    "agent": {"config", "domain", "knowledge", "bridge", "llm", "storage", "agent"},
    "server": {"config", "domain", "bridge", "llm", "storage", "agent", "server", "__init__"},
    "cli": {"config", "domain", "bridge", "llm", "storage", "agent", "server", "cli", "__init__"},
    "__main__": {"cli"},
    "__init__": {"__init__"},
}


def _layer_for(path: Path) -> str:
    rel = path.relative_to(SRC_ROOT)
    stem = rel.parts[0]
    if stem.endswith(".py"):
        return stem[:-3]
    return stem


def test_source_tree_is_slim_and_follows_acyclic_layer_boundaries() -> None:
    py_files = sorted(SRC_ROOT.rglob("*.py"))
    non_init = [path for path in py_files if path.name not in {"__init__.py", "__main__.py"}]
    assert len(non_init) <= 22
    assert len(py_files) <= 30

    for py_file in py_files:
        layer = _layer_for(py_file)
        assert layer not in REMOVED_TOP_PACKAGES, f"Obsolete module still present: {py_file}"
        allowed = ALLOWED_LAYER_DEPS[layer]
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            target_mod: str | None = None
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("spiremind."):
                target_mod = node.module.split(".")[1]
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("spiremind."):
                        target_mod = alias.name.split(".")[1]
            if target_mod is not None:
                assert target_mod not in REMOVED_TOP_PACKAGES, (
                    f"{py_file.name} imports removed package {target_mod}"
                )
                assert target_mod in allowed, (
                    f"Layer violation in {py_file.relative_to(SRC_ROOT)}: {layer} -> {target_mod}"
                )
