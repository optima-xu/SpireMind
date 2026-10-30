"""One observed state, one assessment, one set of admissible actions.

Policies can rank these actions but cannot widen the execution boundary. Unknown
effects stay unknown; only supported, explicit HP costs impose a hard exclusion.
"""

from dataclasses import dataclass, replace

from spiremind.core.context import MemoryContext
from spiremind.core.decision import Decision
from spiremind.core.enums import Scene
from spiremind.core.state import GameState
from spiremind.core.validation import ActionValidator
from spiremind.decision.combat import assess
from spiremind.knowledge.library import version_matches


@dataclass(frozen=True)
class DecisionFrame:
    observed: GameState
    policy_state: GameState
    memory: MemoryContext | None
    excluded: dict[str, str]

    @classmethod
    def prepare(cls, state: GameState, memory: MemoryContext | None):
        facts, excluded = None, {}
        if state.scene == Scene.COMBAT and state.combat:
            experience = (memory.experiences if memory else None) or {}
            disabled = any(w.get("tactic") == "rage_before_attack" for w in experience.get("warnings", []))
            facts = assess(
                state,
                lost_hp_this_turn=bool(memory and memory.working.get("lost_hp_this_turn")),
                disabled_cards=("rage",) if disabled else (),
            )
            facts["binding"] = [state.decision_id, state.revision]
            if version_matches("0.111.x", state.game_version):
                excluded = {
                    row["action_id"]: "visible_hp_cost_exhausts_hp"
                    for row in facts.get("evaluated_actions", [])
                    if row.get("self_lethal") and row.get("status_effect_known")
                }
        legal = tuple(action for action in state.legal_actions if action.id not in excluded)
        if not legal:
            raise ValueError("No action satisfies the visible HP-cost constraint")
        policy_state = state.model_copy(update={"legal_actions": legal})
        context = replace(memory, assessment=facts) if memory and facts is not None else memory
        return cls(state, policy_state, context, excluded)

    def validate(self, decision: Decision) -> None:
        ActionValidator().validate(self.observed, decision.action)
        if decision.action.id in self.excluded:
            raise ValueError(f"Action blocked: {self.excluded[decision.action.id]}")
