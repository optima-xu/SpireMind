import json

from spiremind.config import StrategyConfig
from spiremind.core.decision import Decision
from spiremind.core.enums import Scene

from .base import LLMStrategy
from .combat_tactics import assess, forced_combat_selection_action, forced_survival_action


class CombatStrategy(LLMStrategy):
    name = "combat"
    task = (
        "Choose one card play, selection, potion or end-turn. Use actual card text and enemy intents. "
        "Prefer verified lethal; otherwise compare damage and tempo with HP saved. Handle setup order, "
        "energy, targeting, hand space and long-term resources. Ending the turn may be better than "
        "playing a harmful card."
    )

    def __init__(self, compiler, provider, fallback, settings: StrategyConfig | None = None):
        super().__init__(compiler, provider, fallback)
        self.settings = settings or StrategyConfig()

    def task_for(self, state, memory):
        if state.scene == Scene.CARD_SELECTION:
            facts = state.scene_facts.unpack()
            return (
                self.task
                + " This is a selection operation, not a card play. Apply operation and operation_effect "
                "literally; never claim the selected card's text happens now. Preserve cards needed to "
                "survive the combat_summary incoming damage.\nselection_check="
                + json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
            )
        facts = assess(state)
        return (
            self.task
            + (
                " Enemy Strength belongs to enemies; never add it to your attacks. Live card values already "
                "include owner bonuses. Read damage-cap layers before valuing a big hit; cheap multi-hit "
                "attacks can remove a per-hit HP-loss cap. In the current boss fight, saving potions for "
                "the boss has reached its use condition. Consider legal USE_POTION even at zero energy. "
                "Do not end with useful energy just because you cannot kill this turn: check safe attacks, "
                "block and potions. Do not play harmful cards merely to spend energy. Compare survival "
                "after intents and compare whole-turn plans instead of greedily choosing one card at a "
                "time. Slow increases damage the enemy receives; it never reduces outgoing enemy damage. "
                "visible_max_damage_plan is the best supported remaining-hand attack order. If no forced "
                "defense is required, do not spend most energy on small Block when that attack plan kills "
                "or materially shortens a scaling fight. Block has a survival threshold: when "
                "minimum_additional_block_to_survive is 0, Block is not required to live through the "
                "shown intents, so compare HP saved per energy against damage and turns-to-kill. In that "
                "case, choose Block only for a concrete reason such as a small visible survival margin, "
                "a live full-block trigger, or no meaningful improvement to turns-to-kill; never default "
                "to Block merely because the enemy attacks. "
                "verified_lethal and verified_lethal_plan are "
                "high-confidence hard evidence for supported cards; "
                "for unsupported cards, reason from live card text without claiming guard verification. "
                "visible_survival_plan is an affordable sequence, while no_visible_survival means the "
                "supported visible actions cannot survive the shown attack. This check excludes end-turn "
                "triggers and unknown mechanics.\ncombat_check="
            )
            + json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
        )

    async def decide(self, state, memory):
        self.last_context = None
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
            facts = assess(state)
            forced = forced_survival_action(state, facts, self.settings.boss_potion_damage_fraction)
            if forced:
                action, rule = forced
                return Decision(
                    action=action,
                    policy_rule=rule,
                    confidence=0.95,
                    reason=f"{rule}; end-now HP from visible intents={facts['hp_after_intents_if_end_now']}",
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
        return await super().decide(state, memory)
