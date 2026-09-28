"""Re-evaluate saved v0.111.0 combat states without executing game actions.

--use-model explicitly sends the selected historical state and memory to the
configured provider. Without it, only local arithmetic and policy rules run.
The default selects the original five boss cases; --revisions selects exact
state revisions from any trace.
"""

import argparse
import asyncio
import json
from pathlib import Path

from spiremind.config import Config
from spiremind.context.budget import ContextBudget
from spiremind.context.compiler import ContextCompiler
from spiremind.core.state import GameState
from spiremind.knowledge.cards import CardDB
from spiremind.knowledge.library import StrategyLibrary
from spiremind.memory.manager import MemoryContext
from spiremind.providers.openai import OpenAIProvider
from spiremind.strategies.combat import CombatStrategy
from spiremind.strategies.combat_tactics import assess, forced_survival_action
from spiremind.strategies.fallback import conservative_choice

CASES = [
    ("shield_heavy_hit", 3, 3),
    ("unused_energy", 7, 2),
    ("fatal_one_energy", 9, 1),
    ("fatal_zero_energy", 9, 0),
    ("enemy_strength", 8, 2),
]


async def evaluate(args):
    if args.use_model and args.config is None:
        raise ValueError("--config is required with --use-model")
    config = Config.load(args.config)
    states = [
        GameState.model_validate_json(x)
        for x in (args.trace / "states.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    if args.revisions:
        by_revision = {state.revision: state for state in states}
        missing = [revision for revision in args.revisions if revision not in by_revision]
        if missing:
            raise ValueError(f"Trace does not contain revisions: {missing}")
        cases = [(f"revision_{revision}", by_revision[revision]) for revision in args.revisions]
    else:
        cases = [
            (
                name,
                next(
                    state
                    for state in states
                    if state.combat
                    and state.combat.turn == turn
                    and state.combat.energy == energy
                    and state.combat.hand
                ),
            )
            for name, turn, energy in CASES
        ]
    decisions = {
        r["decision_id"]: r
        for r in map(json.loads, (args.trace / "decisions.jsonl").read_text(encoding="utf-8").splitlines())
    }
    contexts = {
        r["id"]: r
        for r in map(json.loads, (args.trace / "contexts.jsonl").read_text(encoding="utf-8").splitlines())
    }
    cards = CardDB(config.runtime.runs_dir / "cards.sqlite")
    provider = OpenAIProvider(config.model) if args.use_model else None
    compiler = ContextCompiler(
        StrategyLibrary(),
        cards,
        ContextBudget(config.runtime.context_tokens, config.runtime.max_context_tokens),
    )
    strategy = CombatStrategy(compiler, provider, conservative_choice, config.strategy)
    results = []
    try:
        for name, state in cases:
            old = decisions[state.decision_id]
            previous = json.loads(contexts[old["context_id"]]["user"])
            memory = MemoryContext("saved-case", previous.get("L2_run_strategy", {}), {}, ())
            facts = assess(state)
            forced = forced_survival_action(state, facts, config.strategy.boss_potion_damage_fraction)
            if args.use_model or forced:
                decision = await strategy.decide(state, memory)
                chosen, rule, reason = decision.action.id, decision.policy_rule, decision.reason
            else:
                chosen, rule, reason = None, None, "Local facts only; model was not requested"
            row = {
                "case": name,
                "old_action": old["action"]["id"],
                "new_action": chosen,
                "policy_rule": rule,
                "reason": reason,
                "combat_check": facts,
            }
            results.append(row)
            print(
                json.dumps({k: v for k, v in row.items() if k != "combat_check"}, ensure_ascii=False),
                flush=True,
            )
    finally:
        if provider:
            await provider.close()
        cards.close()
    report = {
        "scope": "saved-state regression; no game actions executed",
        "cases": results,
        "model": provider.last_model if provider else None,
        "model_calls": provider.calls if provider else 0,
        "reasoning_responses": provider.reasoning_responses if provider else 0,
        "incomplete_responses": provider.incomplete_responses if provider else 0,
        "invalid_responses": provider.invalid_responses if provider else 0,
        "transport_errors": provider.transport_errors if provider else 0,
        "input_tokens": provider.input_tokens if provider else 0,
        "output_tokens": provider.output_tokens if provider else 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="Provider config; required with --use-model")
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--revisions", type=int, nargs="+")
    parser.add_argument("--use-model", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("runs/combat-strategy-evaluation-final.json"))
    asyncio.run(evaluate(parser.parse_args()))
