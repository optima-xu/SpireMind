from spiremind.core.decision import Decision
from spiremind.core.enums import ActionKind, Scene
from spiremind.core.state import GameState
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
                "none improves the deck. Never use reward:proceed to avoid inspecting an unopened card "
                "reward. Claim free material rewards before leaving."
            )
        if state.scene == Scene.SHOP:
            return (
                "Shopping is optional. Compare every purchase and removal against saving all gold for a "
                "later shop; affordability or synergy alone does not justify spending. Never open the "
                "inventory or buy something merely because it is available. Buy only when the option's "
                "marginal value clearly exceeds keeping the gold, and reassess after every purchase rather "
                "than chaining purchases by default. If nothing clears that threshold, leave with no "
                "purchase. Use shop:close_inventory to return to the shop overview, then shop:proceed to "
                "leave. A prior plan to buy one named item is complete once that item is owned; then prefer "
                "leaving unless a separate exceptional purchase is independently justified."
            )
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
        return await super().decide(state, memory)


class DeckAnalyzer:
    """Transparent heuristic profile, recomputed from facts; not a learned value model."""

    def __init__(self, library: StrategyLibrary):
        self.library = library

    @staticmethod
    def _starter(card_id: str) -> bool:
        value = card_id.lower()
        return value == "bash" or value.startswith(("strike", "defend"))

    def analyze(self, state: GameState) -> dict:
        deck = state.run.deck
        roles = {
            "block": ("block", "defend", "shrug", "格挡"),
            "aoe": ("all enemies", "whirlwind", "cleave", "dagger_spray", "所有敌人"),
            "draw": ("draw", "pommel_strike", "acrobatics", "burning_pact", "抽"),
            "energy": ("gain energy", "offering", "turbo", "能量"),
            "scaling": ("strength", "poison", "focus", "demon_form", "accuracy", "力量"),
        }
        total_cards = sum(card.count for card in deck)
        densities = {}
        meaningful = {}
        for role, words in roles.items():
            matching = [
                card for card in deck if any(word in (card.id + " " + card.text).lower() for word in words)
            ]
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
        readiness = (state.run.hp / max(1, state.run.max_hp)) * (
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
            elite_readiness=round(readiness, 3),
            derived_metrics=metrics,
        )
