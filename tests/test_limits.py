import json

import pytest
from pydantic import ValidationError

from spiremind.cli import build_parser, execute
from spiremind.config import Config
from spiremind.providers.protocols import BudgetExceeded, RequestBudget


@pytest.mark.parametrize("field", ["max_steps", "max_seconds", "max_total_tokens"])
def test_toml_false_disables_limits_but_zero_is_invalid(field, tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(f"[runtime]\n{field}=false\n", encoding="utf-8")
    assert getattr(Config.load(path).runtime, field) is None
    with pytest.raises(ValidationError):
        Config.model_validate({"runtime": {field: 0}})


def test_unlimited_request_budget_has_no_numeric_sentinel():
    budget = RequestBudget(None, None)
    for _ in range(3):
        reserved = budget.reserve(10**20)
        budget.settle(reserved, 10**20)
    assert budget.report() == {
        "requests": 3,
        "tokens": 3 * 10**20,
        "reserved": 0,
        "max_requests": None,
        "max_tokens": None,
    }


def test_unlimited_child_still_honors_finite_parent():
    parent = RequestBudget(1, 100)
    child = RequestBudget(None, None, parent)
    reservation = child.reserve(80)
    child.settle(reservation, 20)
    with pytest.raises(BudgetExceeded):
        child.reserve(1)
    assert child.requests == parent.requests == 1
    assert child.reserved == parent.reserved == 0


def test_each_request_budget_dimension_can_be_disabled():
    requests_only = RequestBudget(1, None)
    requests_only.reserve(10**20)
    with pytest.raises(BudgetExceeded):
        requests_only.reserve(1)
    tokens_only = RequestBudget(None, 100)
    reservation = tokens_only.reserve(90)
    tokens_only.settle(reservation, 1)
    with pytest.raises(BudgetExceeded):
        tokens_only.reserve(100)
    for _ in range(3):
        tokens_only.settle(tokens_only.reserve(1), 1)
    assert tokens_only.requests == 4


async def test_no_limits_overrides_all_run_caps_until_terminal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "config.toml"
    path.write_text("[runtime]\nmax_steps=1\nmax_seconds=0.001\nmax_total_tokens=1\n", encoding="utf-8")
    result = await execute(
        build_parser().parse_args(
            ["--config", str(path), "start", "--environment", "mock", "--policy", "rules", "--no-limits"]
        )
    )
    assert result["complete"] and result["verified_actions"] == 10
    assert result["request_budget"]["max_tokens"] is None
    manifest = json.loads((tmp_path / "runs" / result["attempt_id"] / "manifest.json").read_text())
    for field in ("max_steps", "max_seconds", "max_total_tokens"):
        assert manifest["configuration"]["runtime"][field] is None


async def test_step_remains_one_action_with_unlimited_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "config.toml"
    path.write_text("[runtime]\nmax_steps=false\n", encoding="utf-8")
    result = await execute(
        build_parser().parse_args(
            ["--config", str(path), "step", "--environment", "mock", "--policy", "rules"]
        )
    )
    assert not result["complete"] and result["verified_actions"] == result["steps"] == 1
