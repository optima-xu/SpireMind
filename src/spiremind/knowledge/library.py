from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from spiremind.core.state import GameState


def version_matches(pattern: str, version: str) -> bool:
    pattern, version = pattern.removeprefix("v"), version.removeprefix("v")
    return version.startswith(pattern[:-1]) if pattern.endswith("x") else pattern == version


class StrategyPackage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    character: str
    game_version: str
    source: str
    archetype: str
    strong_signals: tuple[str, ...]
    enablers: tuple[str, ...]
    payoffs: tuple[str, ...]
    goals: tuple[str, ...]
    hard_rules: tuple[str, ...]
    heuristics: tuple[str, ...]
    anti_patterns: tuple[str, ...]
    scenes: tuple[str, ...] = ("combat", "run", "map")


class StrategyLibrary:
    def __init__(self, root: Path | None = None):
        root = root or Path(__file__).parent / "strategies"
        self.packages = [
            StrategyPackage.model_validate(p)
            for path in sorted(root.glob("*/*.yaml"))
            for p in yaml.safe_load(path.read_text(encoding="utf-8"))
        ]

    def scores(self, state: GameState) -> list[tuple[float, StrategyPackage]]:
        """Return persistent deck fit scores.

        The score deliberately excludes the current hand. A shuffled draw must not
        make the long-lived run memory oscillate between archetypes.
        """
        deck = [card.id for card in state.run.deck for _ in range(card.count)]
        present = set(deck) | {r.id for r in state.run.relics}
        result = []
        for p in self.packages:
            if p.character != state.run.character or not version_matches(p.game_version, state.game_version):
                continue
            core = len(present & set(p.strong_signals)) / max(1, len(p.strong_signals))
            enabler = min(1, sum(c in p.enablers for c in deck) / max(1, len(deck) * 0.15))
            payoff = min(1, sum(c in p.payoffs for c in deck) / max(1, len(deck) * 0.1))
            fit = min(enabler, payoff)
            penalty = 0.15 if enabler and not payoff else 0
            score = max(0, 0.35 * core + 0.25 * enabler + 0.25 * payoff + 0.15 * fit - penalty)
            result.append((round(score, 3), p))
        return sorted(result, key=lambda pair: (-pair[0], pair[1].id))

    @staticmethod
    def _scene_relevance(state: GameState, package: StrategyPackage) -> float:
        """Score only the cards visible at this decision, separately from deck fit."""
        if state.combat:
            visible = {card.id for card in state.combat.hand}
        else:
            visible = {choice.card.id for choice in state.choices if choice.card}
            visible.update(action.card_id for action in state.legal_actions if action.card_id)
        if visible & set(package.strong_signals):
            return 1.0
        if visible & set(package.payoffs):
            return 0.75
        if visible & set(package.enablers):
            return 0.5
        return 0.0

    def retrieve_detailed(
        self, state: GameState, agent: str, k: int = 3, minimum: float = 0.35
    ) -> list[tuple[float, float, StrategyPackage]]:
        """Return ``(deck_fit, scene_relevance, package)`` without conflating the two."""
        candidates = []
        for deck_fit, package in self.scores(state):
            if agent not in package.scenes:
                continue
            scene_relevance = self._scene_relevance(state, package)
            # A visible offered/held signal makes anti-patterns and hard rules
            # useful even before the deck has committed to the archetype.
            if deck_fit >= minimum or scene_relevance > 0:
                rank = deck_fit + 0.2 * scene_relevance
                candidates.append((rank, deck_fit, scene_relevance, package))
        candidates.sort(key=lambda row: (-row[0], row[3].id))
        return [
            (deck_fit, scene_relevance, package) for _, deck_fit, scene_relevance, package in candidates[:k]
        ]

    def retrieve(self, state: GameState, agent: str, k: int = 3, minimum: float = 0.35):
        return [
            (round(deck_fit + 0.2 * scene_relevance, 3), package)
            for deck_fit, scene_relevance, package in self.retrieve_detailed(state, agent, k, minimum)
        ]
