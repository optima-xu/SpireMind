import re
from copy import deepcopy

from spiremind.core.cache import LRU
from spiremind.core.enums import Scene
from spiremind.core.ports import CardCatalog
from spiremind.core.state import GameState
from spiremind.knowledge.library import StrategyLibrary


class DeckAnalyzer:
    """Transparent heuristic profile, recomputed from facts; not a learned value model."""

    def __init__(self, library: StrategyLibrary, cards: CardCatalog | None = None):
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

    def compare_choices(self, state: GameState) -> tuple[dict, ...]:
        """Marginal deck gaps, with skipping as zero; these are not utility scores."""
        if state.scene != Scene.CARD_REWARD or not state.choices:
            return ()
        baseline = self.analyze(state)["needs"]
        comparisons = []
        for choice in state.choices:
            if choice.card is None:
                continue
            run = state.run.model_copy(update={"deck": (*state.run.deck, choice.card)})
            changed = self.analyze(state.model_copy(update={"run": run}))["needs"]
            comparisons.append(
                {
                    "choice_id": choice.id,
                    "price": choice.price,
                    "need_reduction_vs_skip": {
                        key: round(baseline[key] - changed[key], 3)
                        for key in baseline
                        if abs(baseline[key] - changed[key]) >= 0.001
                    },
                    "basis": "heuristic_deck_density_not_proven_value",
                }
            )
        return tuple(comparisons)
