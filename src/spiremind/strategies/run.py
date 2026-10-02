import re
from copy import deepcopy

from spiremind.context.route_horizon import last_known_shop_before_boss
from spiremind.core.cache import LRU
from spiremind.core.decision import Decision
from spiremind.core.enums import ActionKind, Scene
from spiremind.core.state import GameState
from spiremind.knowledge.cards import CardDB
from spiremind.knowledge.library import StrategyLibrary

from .base import LLMStrategy


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


class DeckAnalyzer:
    """Transparent heuristic profile, recomputed from facts; not a learned value model."""

    def __init__(self, library: StrategyLibrary, cards: CardDB | None = None):
        self.library = library
        self.cards = cards
        self.cache = LRU(128)

    @staticmethod
    def _starter(card_id: str) -> bool:
        value = card_id.lower()
        return value == "bash" or value.startswith(("strike", "defend"))

    def analyze(self, state: GameState) -> dict:
        key = (
            state.game_version,
            state.run.character,
            state.run.deck,
            state.run.relics,
            self.cards.generation if self.cards else 0,
            self.library.knowledge_version,
        )
        found, profile = self.cache.get(key)
        if not found:
            profile = self._compute(state)
            self.cache.put(key, profile)
        result = deepcopy(profile)
        factor = result.pop("_readiness_factor")
        result["elite_readiness"] = round(state.run.hp / max(1, state.run.max_hp) * factor, 3)
        return result

    def _compute(self, state: GameState) -> dict:
        deck = state.run.deck
        facts = (
            {
                (fact.card_id, fact.upgraded): fact
                for fact in self.cards.lookup({(card.id, card.upgraded) for card in deck}, state.game_version)
            }
            if self.cards
            else {}
        )
        roles = {
            "block": ("defend", "shrug", "flame_barrier", "iron_wave"),
            "aoe": ("all enemies", "whirlwind", "cleave", "dagger_spray", "所有敌人"),
            "draw": ("pommel_strike", "acrobatics", "burning_pact"),
            "energy": ("offering", "turbo"),
            "scaling": ("inflame", "demon_form", "poison", "focus", "accuracy"),
        }

        def matches(card, role, words):
            fact = facts.get((card.id, card.upgraded))
            text = re.sub(r"\[[^\]]+\]", "", card.text or (fact.text if fact else "")).lower()
            values = card.values.unpack() or (fact.values.unpack() if fact else {})
            identity = card.id.lower()
            if any(word in identity for word in words):
                return True
            if role == "block":
                return bool(values.get("Block", values.get("CalculatedBlock", 0))) or bool(
                    re.search(r"(?:获得|gain).{0,24}(?:点格挡|block)", text)
                )
            if role == "aoe":
                return "所有敌人" in text or "all enemies" in text
            if role == "draw":
                return bool(values.get("Cards", 0)) or bool(
                    re.search(r"抽(?:\{[^}]+\}|\d+|[一二三两])张牌|draw (?:\d+|a|one) card", text)
                )
            if role == "energy":
                return bool(values.get("Energy", 0)) or bool(
                    re.search(r"(?:获得|gain).{0,24}(?:点能量|energy)", text)
                )
            if role == "scaling":
                persistent_value = any(
                    bool(value)
                    and (
                        str(key).lower().endswith("power")
                        or str(key).lower() in {"strength", "dexterity", "focus"}
                    )
                    for key, value in values.items()
                )
                return (
                    persistent_value
                    or bool(values.get("StrengthPerVulnerable", 0))
                    or bool(re.search(r"(?:获得|gain).{0,24}(?:点力量|strength)", text))
                )
            return False

        total_cards = sum(card.count for card in deck)
        densities = {}
        meaningful = {}
        for role, words in roles.items():
            matching = [card for card in deck if matches(card, role, words)]
            meaningful[role] = sum(card.count for card in matching if not self._starter(card.id))
            # Starter Defends contribute to basic survival, but are not evidence
            # that the deck has built a block engine or solved its defense.
            quality = sum(
                card.count * (0.35 if role == "block" and self._starter(card.id) else 1.0)
                for card in matching
            )
            densities[role] = quality / max(1, total_cards)
        targets = {"block": 0.3, "aoe": 0.1, "draw": 0.15, "energy": 0.1, "scaling": 0.1}
        needs = {key: round(max(0, 1 - densities[key] / target), 3) for key, target in targets.items()}
        scores = {package.archetype: score for score, package in self.library.scores(state)}
        improvements = sum(card.count for card in deck if not self._starter(card.id))
        improvement_quality = min(1.0, improvements / max(3, total_cards * 0.2))
        readiness = (
            0.25 + 0.35 * (1 - needs["block"]) + 0.25 * (1 - needs["scaling"]) + 0.15 * improvement_quality
        )
        metrics = {}
        if state.run.character == "regent":
            relevant = [p for _, p in self.library.scores(state) if p.archetype == "stars"]
            if relevant:
                p = relevant[0]
                # Counts, not fictional Star yields when static facts are unavailable.
                metrics = dict(
                    star_generator_count=sum(c.id in p.enablers for c in deck),
                    star_spender_count=sum(c.id in p.payoffs for c in deck),
                    star_reserve_target=0,
                )
        return dict(
            archetype_scores=scores,
            needs=needs,
            strengths=[key for key, value in needs.items() if value < 0.25 and meaningful[key] > 0],
            weaknesses=[k for k, v in needs.items() if v > 0.6],
            _readiness_factor=readiness,
            derived_metrics=metrics,
        )
