from pathlib import Path

import yaml

from spiremind.core.context import Skill
from spiremind.core.state import GameState
from spiremind.knowledge.library import version_matches


class SkillMemory:
    def __init__(self, skills: list[Skill] | None = None):
        path = Path(__file__).parents[1] / "knowledge" / "skills" / "tactics.yaml"
        self.skills = (
            skills
            if skills is not None
            else [Skill.model_validate(x) for x in yaml.safe_load(path.read_text(encoding="utf-8"))]
        )

    def triggered(self, state: GameState) -> list[Skill]:
        if not state.combat:
            return []
        hand = {c.id for c in state.combat.hand}
        powers = {p.id.removesuffix("_power") for p in state.combat.powers}
        return [
            s
            for s in self.skills
            if s.confirmed
            and s.character == state.run.character
            and version_matches(s.game_version, state.game_version)
            and set(s.required_hand) <= hand
            and set(s.required_powers) <= powers
        ]
