"""Oracle quality regression checks against captured Slay the Spire 2 decision cases."""

from __future__ import annotations

import json
from pathlib import Path

from spiremind.agent.policies import (
    CombatStrategy,
    DecisionFrame,
    EventStrategy,
    MapStrategy,
    RunStrategy,
    SceneRouter,
    conservative_choice,
)
from spiremind.domain.decision import MemoryContext
from spiremind.domain.state import GameState

FIXTURE = Path(__file__).parent / "fixtures" / "quality_cases.json"


async def test_labeled_quality_cases_pass_all_oracles() -> None:
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
    router = SceneRouter(
        *(
            policy(None, None, conservative_choice)
            for policy in (CombatStrategy, RunStrategy, MapStrategy, EventStrategy)
        )
    )
    assert len(cases) == 8

    for case in cases:
        state = GameState.model_validate(case["state"])
        frame = DecisionFrame.prepare(state, MemoryContext("offline", {}, {}, ()))
        decision = await router.route(state).decide(frame.policy_state, frame.memory)
        frame.validate(decision)
        assert decision.action.id in set(case["expected_actions"]), case["id"]
        if "expected_exclusions" in case:
            assert set(frame.excluded) == set(case["expected_exclusions"]), case["id"]
        if "survival_status" in case:
            assert frame.memory.assessment["survival_status"] == case["survival_status"], case["id"]
