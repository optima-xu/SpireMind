"""Offline policy checks against explicit action oracles, separate from mock playback."""

import hashlib
import json
from pathlib import Path

from spiremind.adapters.telemetry.trace import source_fingerprint
from spiremind.core.context import MemoryContext
from spiremind.core.state import GameState
from spiremind.decision.frame import DecisionFrame
from spiremind.decision.policies.combat import CombatStrategy
from spiremind.decision.policies.event import EventStrategy
from spiremind.decision.policies.fallback import conservative_choice
from spiremind.decision.policies.map import MapStrategy
from spiremind.decision.policies.run import RunStrategy
from spiremind.decision.router import SceneRouter

DEFAULT_CASES = Path(__file__).with_name("cases") / "quality.json"


async def evaluate(dataset: Path | None = None):
    raw = (dataset or DEFAULT_CASES).read_bytes()
    cases = json.loads(raw)["cases"]
    router = SceneRouter(
        *(
            policy(None, None, conservative_choice)
            for policy in (CombatStrategy, RunStrategy, MapStrategy, EventStrategy)
        )
    )
    rows = []
    for case in cases:
        state = GameState.model_validate(case["state"])
        frame = DecisionFrame.prepare(state, MemoryContext("offline", {}, {}, ()))
        decision = await router.route(state).decide(frame.policy_state, frame.memory)
        frame.validate(decision)
        expected = set(case["expected_actions"])
        passed = decision.action.id in expected
        if "expected_exclusions" in case:
            passed &= set(frame.excluded) == set(case["expected_exclusions"])
        if "survival_status" in case:
            passed &= frame.memory.assessment["survival_status"] == case["survival_status"]
        rows.append(
            {
                "case": case["id"],
                "selected": decision.action.id,
                "expected_actions": sorted(expected),
                "passed": passed,
                "excluded": frame.excluded,
                "policy_rule": decision.policy_rule,
            }
        )
    return {
        "mode": "offline_rules",
        "model_calls": 0,
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "source_sha256": source_fingerprint(),
        "passed": sum(row["passed"] for row in rows),
        "total": len(rows),
        "scope": "Labeled policy regressions; not a win-rate estimate or model evaluation",
        "cases": rows,
    }
