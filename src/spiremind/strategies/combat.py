import json
from dataclasses import replace

from spiremind.config import StrategyConfig
from spiremind.core.decision import Decision
from spiremind.core.enums import Scene

from .base import LLMStrategy
from .combat_tactics import (
    assess,
    early_boss_potion_action,
    forced_combat_selection_action,
    forced_survival_action,
)


class CombatStrategy(LLMStrategy):
    name = "combat"
    task = (
        "Choose one legal combat action. Compare whole-turn damage, HP saved and setup value using "
        "live effects. Respect energy, targeting, hand space and future resources; harmful plays "
        "can be worse than ending."
    )

    def __init__(self, compiler, provider, fallback, settings: StrategyConfig | None = None):
        super().__init__(compiler, provider, fallback)
        self.settings = settings or StrategyConfig()

    def task_for(self, state, memory, assessment=None):
        if state.scene == Scene.CARD_SELECTION:
            facts = state.scene_facts.unpack()
            return (
                self.task
                + " This is a selection operation, not a card play. Apply operation and operation_effect "
                "literally; never claim the selected card's text happens now. Preserve cards needed to "
                "survive the combat_summary incoming damage.\nselection_check="
                + json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
            )
        facts = (
            assessment
            if assessment is not None
            else assess(
                state,
                lost_hp_this_turn=bool(memory and memory.working.get("lost_hp_this_turn")),
            )
        )
        return (
            self.task
            + (
                " Live values include owner bonuses; do not add Strength/Dexterity again. Enemy Strength "
                "never belongs to you. target_hp_after and verified_lethal are authoritative only for "
                "supported effects. Unknown mechanics require live text reasoning. Respect damage caps, "
                "remaining_card_plays, setup costs and Minion leader death. Compare whole-turn offense "
                "and survival; when minimum_additional_block_to_survive is 0, weigh Block's HP saving "
                "against turns-to-kill. Never choose self_lethal. Spend HP only for a better complete "
                "turn with a credible reserve. Potions remain legal at zero energy; use boss scaling "
                "potions early. Slow changes received damage only. Searches omit unknown/end-turn "
                "effects; truncation cannot prove safety or impossibility. The repeated-intent scenario "
                "is illustrative, not a forecast.\ncombat_check="
            )
            + json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
        )

    async def decide(self, state, memory):
        self.last_context = None
        facts = None
        forced_selection = forced_combat_selection_action(state)
        if forced_selection:
            action, rule = forced_selection
            return Decision(
                action=action,
                policy_rule=rule,
                confidence=1,
                reason=f"{rule}; selection operation exhausts the chosen card without playing it",
            )
        if self.settings.combat_guards and state.scene == Scene.COMBAT:
            facts = assess(
                state,
                lost_hp_this_turn=bool(memory and memory.working.get("lost_hp_this_turn")),
            )
            forced = forced_survival_action(state, facts, self.settings.boss_potion_damage_fraction)
            if forced:
                action, rule = forced
                return Decision(
                    action=action,
                    policy_rule=rule,
                    confidence=0.95,
                    reason=f"{rule}; end-now HP from visible intents={facts['hp_after_intents_if_end_now']}",
                )
            early_potion = early_boss_potion_action(state, facts)
            if early_potion:
                action, rule = early_potion
                return Decision(
                    action=action,
                    policy_rule=rule,
                    confidence=0.8,
                    reason=f"{rule}; use the persistent benefit while the boss still has substantial HP",
                )
            if (
                facts.get("survival_status") == "dead"
                and len(state.legal_actions) == 1
                and state.legal_actions[0].kind.value == "end_turn"
            ):
                return Decision(
                    action=state.legal_actions[0],
                    policy_rule="forced_lethal_end_turn",
                    confidence=1,
                    reason="forced_lethal_end_turn; all supported visible survival actions are exhausted",
                )
        if state.scene == Scene.COMBAT and facts is None:
            facts = assess(state, lost_hp_this_turn=bool(memory and memory.working.get("lost_hp_this_turn")))
        if memory is not None and facts is not None:
            memory = replace(memory, assessment=facts)
        task = self.task_for(state, memory, facts) if self.provider and len(state.legal_actions) > 1 else None
        return await super().decide(state, memory, task_override=task)
