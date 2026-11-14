"""Scene router, DecisionFrame safety boundary, deterministic policies, and LLM strategy policies."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from typing import Protocol

from spiremind.agent.context import ContextCompiler, last_known_shop_before_boss, route_options
from spiremind.agent.mechanics.effects import free_rage_action
from spiremind.agent.mechanics.planner import (
    assess,
    early_boss_potion_action,
    forced_combat_selection_action,
    forced_survival_action,
)
from spiremind.config import GameConfig, StrategyConfig
from spiremind.domain.decision import (
    ContextOverflow,
    Decision,
    DecisionProvider,
    MemoryContext,
    ProviderError,
)
from spiremind.domain.safety import ActionValidator
from spiremind.domain.state import ActionKind, GameState, Scene, owner_for
from spiremind.knowledge.loader import version_matches

# --- from decision/frame.py ---


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
            facts = assess(
                state,
                lost_hp_this_turn=bool(memory and memory.working.get("lost_hp_this_turn")),
                disabled_cards=(),
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


# --- from decision/router.py ---


class SceneRouter:
    def __init__(self, combat, run, map_strategy, event):
        self.strategies = {"combat": combat, "run": run, "map": map_strategy, "event": event}

    def route(self, state: GameState):
        if state.terminal:
            raise ValueError("Terminal states do not require a strategy")
        return self.strategies[owner_for(state)]


# --- from decision/policies/fallback.py ---


def conservative_choice(state: GameState, memory: MemoryContext) -> Decision:
    """A deterministic outage policy, explicitly labelled, not a claimed expert policy."""

    if state.scene == Scene.COMBAT:
        facts = memory.assessment if memory and memory.assessment is not None else assess(state)
        forced = forced_survival_action(state, facts)
        if forced:
            action, rule = forced
            return Decision(
                action=action,
                reason=f"Deterministic outage safety rule: {rule}",
                confidence=0,
                fallback=True,
                policy_rule=f"fallback_{rule}",
            )

    def score(action):
        risk_cost = {
            "lethal": 1000,
            "incoming_damage": 80,
            "hp_loss": 50,
            "curse": 40,
            "automatic_consumable": 25,
            "deck_thickening": 15,
            "irreversible": 8,
        }
        value = -sum(risk_cost.get(tag, 0) for tag in action.risk_tags)
        text = f"{action.label} {action.description}".lower()
        if "discard_potion" in action.id or "close_main_menu" in action.id or "cancel" in action.id:
            value -= 50
        if state.scene == Scene.SHOP:
            if action.kind in {ActionKind.BUY_ITEM, ActionKind.REMOVE_CARD}:
                value -= 10
            if action.id in {"shop:close_inventory", "shop:proceed"}:
                value += 20
        if action.kind == ActionKind.PLAY_CARD:
            value += 15
            if state.combat:
                card = next((c for c in state.combat.hand if action.card_id in {c.id, c.ref}), None)
                incoming = sum(
                    (i.damage or 0) * (i.hits or 1) for e in state.combat.enemies for i in e.intents
                )
                if card and ("block" in card.text.lower() or "格挡" in card.text):
                    value += 15 if incoming > state.combat.block else -10
                if card:
                    values = card.values.unpack()
                    block = values.get("CalculatedBlock", values.get("Block", 0))
                    damage = values.get("CalculatedDamage", values.get("Damage", 0))
                    if isinstance(block, (int, float)):
                        value += min(max(block, 0), max(incoming - state.combat.block, 0)) * 2
                    if isinstance(damage, (int, float)):
                        value += min(max(damage, 0), 30) / 3
        if action.kind == ActionKind.END_TURN:
            value -= 10
            if state.combat:
                incoming = sum(
                    (i.damage or 0) * (i.hits or 1) for e in state.combat.enemies for i in e.intents
                )
                value -= max(0, incoming - state.combat.block) * 3
        if action.kind == ActionKind.USE_POTION:
            value += 20 if state.run.hp < state.run.max_hp * 0.35 else -15
        if action.kind == ActionKind.CHOOSE_MAP_NODE and state.map:
            node = next((n for n in state.map.nodes if n.id == action.node_id), None)
            if node and "elite" in node.type.lower():
                value -= 25 * (1 - memory.run.get("elite_readiness", 0))
        if state.scene == Scene.CARD_REWARD and action.kind == ActionKind.SKIP:
            value += 5  # don't bloat a deck during an outage without card valuation
        if state.scene == Scene.CARD_REWARD:
            if action.id.startswith("reward:claim:"):
                # The reward overview contains gold, potion, relic and card-reward
                # entry actions. Claim these before considering the destructive
                # "leave remaining rewards" action.
                value += 100
                if "gold" in text or "金币" in text:
                    value += 20
            if action.id == "reward:proceed":
                value -= 100
        if action.kind == ActionKind.CHOOSE_EVENT_OPTION:
            numbers = [int(item) for item in re.findall(r"\d+", text)]
            amount = max(numbers, default=0)
            if any(marker in text for marker in ("最大生命", "max hp", "maximum hp")) and any(
                marker in text for marker in ("失去", "lose", "loss")
            ):
                value -= 100 + amount
            elif any(marker in text for marker in ("失去", "lose", "take")) and any(
                marker in text for marker in ("生命", " hp", "damage", "伤害")
            ):
                value -= 30 + amount
            if any(marker in text for marker in ("离开", "停止", "leave", "stop", "decline")):
                value += 40
        if action.kind == ActionKind.PROCEED:
            value += 2
        return value

    action = max(state.legal_actions, key=score)
    return Decision(action=action, reason="Deterministic conservative fallback", confidence=0, fallback=True)


# --- from decision/policies/lifecycle.py ---


def lifecycle_decision(state: GameState, config: GameConfig, *, new_run=False) -> Decision | None:
    if state.scene == Scene.GAME_OVER:
        action = next(
            (a for a in state.legal_actions if a.kind == ActionKind.RETURN_TO_MAIN_MENU),
            None,
        )
        if action:
            return Decision(action=action, reason="Clear the previous terminal screen before a new run")
        return None
    if state.scene == Scene.MAIN_MENU:
        if new_run and any(a.kind == ActionKind.CONTINUE_RUN for a in state.legal_actions):
            raise ValueError(
                "An existing run is available. Use resume, or finish/abandon it in the game first."
            )
        for kind in (ActionKind.OPEN_RUN,) if new_run else (ActionKind.CONTINUE_RUN, ActionKind.OPEN_RUN):
            action = next((a for a in state.legal_actions if a.kind == kind), None)
            if action:
                return Decision(
                    action=action, reason="Continue existing run or open standard character select"
                )
        close_submenu = next(
            (a for a in state.legal_actions if a.kind == ActionKind.CLOSE_MENU),
            None,
        )
        if close_submenu:
            return Decision(action=close_submenu, reason="Close the current submenu to reveal run entry")
        raise ValueError("No supported standard run entry on the main menu")
    if state.scene == Scene.CHARACTER_SELECT:
        facts = state.scene_facts.unpack()
        if facts.get("is_multiplayer") or facts.get("is_custom"):
            raise ValueError("v1 lifecycle supports standard single-player runs")
        action = next(
            (
                a
                for a in state.legal_actions
                if a.kind == ActionKind.SELECT_CHARACTER
                and a.character == config.character.lower()
                and a.ascension == config.ascension
            ),
            None,
        )
        if action:
            return Decision(action=action, reason="Select configured character and exact ascension")
        selected = str(facts.get("selected_character_id", "")).lower()
        if selected != config.character.lower() or facts.get("ascension") != config.ascension:
            raise ValueError("Configured character/ascension is not available")
        action = next((a for a in state.legal_actions if a.kind == ActionKind.EMBARK), None)
        if action:
            return Decision(action=action, reason="Start configured standard run")
        raise ValueError("Configured run cannot embark yet")
    return None


# --- from decision/policies/base.py ---


class DecisionStrategy(Protocol):
    name: str

    async def decide(self, state: GameState, memory: MemoryContext) -> Decision: ...


class LLMStrategy:
    name = "event"
    task = "Choose the most useful legal option."

    def __init__(self, compiler: ContextCompiler, provider: DecisionProvider | None, fallback):
        self.compiler, self.provider, self.fallback = compiler, provider, fallback
        self.last_context = None

    def task_for(self, state: GameState, memory: MemoryContext) -> str:
        return self.task

    async def decide(
        self, state: GameState, memory: MemoryContext, *, task_override: str | None = None
    ) -> Decision:
        if not state.legal_actions:
            raise ValueError("No legal actions at this decision")
        self.last_context = None
        if len(state.legal_actions) == 1:
            return Decision(action=state.legal_actions[0], reason="Only one legal action", confidence=1)
        if self.provider is None:
            return self.fallback(state, memory)
        try:
            context = await self.compiler.build(
                state, self.name, memory, task_override or self.task_for(state, memory)
            )
            self.last_context = context
            result = await self.provider.choose(context, {a.id for a in state.legal_actions})
            choice = result.choice
            return Decision(
                action=next(a for a in state.legal_actions if a.id == choice.action_id),
                reason=choice.reason,
                confidence=choice.confidence,
                strategy_update=choice.strategy_update,
                model_name=result.model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                calculations=list(result.calculations),
                context_id=context.id,
                action_evaluation=next(
                    (row for row in context.action_evaluations if row["action_id"] == choice.action_id), None
                ),
            )
        except (ProviderError, ContextOverflow) as error:
            decision = self.fallback(state, memory)
            decision.provider_error = str(error)
            return decision


# --- from decision/policies/combat.py ---


def assessment_view(facts):
    """Keep decision facts, omitting internal search keys and repeated zero effects."""
    keys = {
        "action_id",
        "cost",
        "hp_loss",
        "energy_gain",
        "heal",
        "block_gain",
        "draw",
        "rage_per_attack",
        "tainted_gain",
        "status_effect_known",
        "self_lethal",
        "target_ref",
        "hp_damage",
        "target_hp_after",
        "verified_lethal",
        "incoming_damage_after_status",
        "hp_after_intents",
        "hp_after_intents_if_played",
        "survival_effect_complete",
        "intent_reduction_estimate",
        "triggers_visible_stun",
    }
    explicit = {
        "cost",
        "status_effect_known",
        "self_lethal",
        "verified_lethal",
        "survival_effect_complete",
        "target_hp_after",
    }
    result = dict(facts)
    result.pop("action_evaluations", None)
    result["evaluated_actions"] = [
        {
            key: value
            for key, value in row.items()
            if key in keys and (key in explicit or value is not None and value != 0)
        }
        for row in facts.get("evaluated_actions", [])
    ]
    result.pop("same_attack_twice_hp_scenario", None)
    result.pop("player_strength", None)
    if "survival_search" in result:
        result["survival_search"] = {
            key: value
            for key, value in result["survival_search"].items()
            if key in {"transition_limit", "truncated", "optimal", "skipped"}
        }
    return result


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
                + json.dumps(
                    {
                        key: value
                        for key, value in facts.items()
                        if key in {"operation", "operation_effect", "in_combat"}
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
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
                "potions early. Slow changes received damage only. Searches include shown Plating; "
                "other unknown/end-turn effects remain unmodeled. Truncation cannot prove safety "
                "or impossibility.\ncombat_check="
            )
            + json.dumps(assessment_view(facts), ensure_ascii=False, separators=(",", ":"))
        )

    async def decide(self, state, memory):
        self.last_context = None
        facts = memory.assessment if memory else None
        if facts and facts.get("binding") != [state.decision_id, state.revision]:
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
            facts = (
                facts
                if facts is not None
                else assess(
                    state,
                    lost_hp_this_turn=bool(memory and memory.working.get("lost_hp_this_turn")),
                    disabled_cards=(),
                )
            )
            forced = forced_survival_action(state, facts, self.settings.boss_potion_damage_fraction)
            rage = free_rage_action(state)
            if rage and not facts.get("verified_lethal_plan"):
                return Decision(
                    action=rage,
                    policy_rule="play_free_rage_before_attack",
                    confidence=0.95,
                    reason="Free Rage increases Block from later attacks; "
                    "local ordering only, survival remains conditional",
                )
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
            facts = assess(
                state,
                lost_hp_this_turn=bool(memory and memory.working.get("lost_hp_this_turn")),
                disabled_cards=(),
            )
        if memory is not None and facts is not None:
            memory = replace(memory, assessment=facts)
        task = self.task_for(state, memory, facts) if self.provider and len(state.legal_actions) > 1 else None
        return await super().decide(state, memory, task_override=task)


# --- from decision/policies/run.py ---


class RunStrategy(LLMStrategy):
    name = "run"
    task = (
        "Choose a reward, purchase, removal, upgrade, rest or deck selection. Improve current deck "
        "needs and prepare for the known boss; skip weak additions. Evaluate price and survival. "
        "Use strategy_update to maintain a short boss plan and resource/route policy across scenes."
    )

    def task_for(self, state: GameState, memory) -> str:
        if state.scene == Scene.CARD_REWARD:
            return (
                "Resolve combat rewards deliberately. An open_card_reward action only reveals the offered "
                "cards and never adds one to the deck. Inspect those candidates first. Once concrete card "
                "choices are visible, compare every card with skipping and choose skip_reward_cards when "
                "none improves the deck. Check L4_deck_facts for the actual effects of cards already owned; "
                "do not infer effects from names or claim that a card grants Strength without evidence. "
                "For a Power card, estimate how many remaining turns and concrete deck triggers can repay "
                "its setup energy; do not reject Powers as a class, and do not take one merely because it "
                "is persistent. Treat explicit HpLoss as a resource cost and explicit Energy as its return. "
                "Never use reward:proceed to avoid inspecting an unopened card "
                "reward. Claim free material rewards before leaving."
            )
        if state.scene == Scene.SHOP:
            guidance = (
                "Shopping is optional. Compare every purchase and removal against saving all gold for a "
                "later shop only when a later shop is visible or plausible; affordability or synergy "
                "alone does not justify spending. Never open the "
                "inventory or buy something merely because it is available. Buy only when the option's "
                "marginal value clearly exceeds keeping the gold, and reassess after every purchase rather "
                "than chaining purchases by default. If nothing clears that threshold, leave with no "
                "purchase. Use shop:close_inventory to return to the shop overview, then shop:proceed to "
                "leave. A prior plan to buy one named item is complete once that item is owned; then prefer "
                "leaving unless a separate exceptional purchase is independently justified."
            )
            horizon = memory.run.get("route_horizon", {})
            if last_known_shop_before_boss(state, horizon):
                guidance += (
                    " The visible route has no later shop before the boss. Do not reserve gold for a "
                    "nonexistent later shop: evaluate immediate boss value of potions, cards, relics and "
                    "removal, especially at low HP. Opening inventory only reveals legal purchases; it "
                    "does not commit gold. Leaving is still correct if every offer is weak."
                )
            return guidance
        return self.task

    async def decide(self, state: GameState, memory) -> Decision:
        self.last_context = None
        unopened = next(
            (action for action in state.legal_actions if action.kind == ActionKind.OPEN_CARD_REWARD),
            None,
        )
        if unopened is not None:
            return Decision(
                action=unopened,
                reason=(
                    "Card candidates are still hidden; this action only reveals them and does not add a card"
                ),
                confidence=1,
                policy_rule="inspect_card_reward_before_skip",
            )
        if state.scene == Scene.SHOP and state.run.max_hp:
            horizon = memory.run.get("route_horizon", {})
            boss_floors = horizon.get("boss_game_floors", [])
            affordable = any(
                choice.price is not None and choice.price <= state.run.gold for choice in state.choices
            )
            open_shop = next(
                (action for action in state.legal_actions if action.kind == ActionKind.OPEN_SHOP), None
            )
            if (
                open_shop is not None
                and state.run.hp / state.run.max_hp <= 0.35
                and last_known_shop_before_boss(state, horizon)
                and min(boss_floors) - state.run.floor <= 3
                and (affordable or not state.choices)
            ):
                return Decision(
                    action=open_shop,
                    reason="Critical HP at the last visible shop before the boss; inspect affordable options",
                    confidence=1,
                    policy_rule="inspect_critical_last_shop",
                )
        return await super().decide(state, memory)


# --- from decision/policies/map.py ---


class MapStrategy(LLMStrategy):
    name = "map"
    task = (
        "Compare L1_current_state.route_options before choosing a reachable map node. Treat shared "
        "reachable shops/rests as available after multiple choices, not a unique benefit of one route. "
        "Compare unavoidable elites, HP risk, potion supply and boss distance before valuing rewards. "
        "The fewest_elites_path is a visible map path, not a combat outcome prediction."
    )

    async def decide(self, state, memory) -> Decision:
        self.last_context = None
        if state.run.max_hp and state.run.hp / state.run.max_hp <= 0.5:
            horizon = route_options(state)
            options = horizon["options"] if horizon else []
            readiness = memory.run.get("elite_readiness", 1)
            if readiness < 0.5:
                for safer in options:
                    if safer["node_type"] == "Elite" or not safer["all_paths_to_boss"]:
                        continue
                    safe_path = [node["node_id"] for node in safer["fewest_elites_path"]]
                    bosses = safer["boss_game_floors"]
                    if not bosses or min(bosses) - state.run.floor > 4:
                        continue
                    for elite in options:
                        elite_path = [node["node_id"] for node in elite["fewest_elites_path"]]
                        if (
                            elite["node_type"] == "Elite"
                            and elite["all_paths_to_boss"]
                            and safer["min_elites"] < elite["min_elites"]
                            and safe_path[1:] == elite_path[1:]
                        ):
                            action = next(a for a in state.legal_actions if a.id == safer["action_id"])
                            return Decision(
                                action=action,
                                reason="Lower-risk route reaches the same downstream nodes before the boss",
                                confidence=1,
                                policy_rule="low_hp_shared_route_avoid_elite",
                            )
        return await super().decide(state, memory)


# --- from decision/policies/event.py ---


class EventStrategy(LLMStrategy):
    name = "event"
    task = (
        "Choose an event, treasure or modal option using its visible costs and outcomes, deck needs, "
        "HP/gold policy and relic interactions. Do not assume undisclosed outcomes."
    )
