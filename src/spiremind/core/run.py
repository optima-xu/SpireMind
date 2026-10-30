from uuid import uuid4

from pydantic import BaseModel, Field


class RunIntent(BaseModel):
    """A revisable objective derived from public state, not a stored action queue."""

    act: int | None = None
    observed_revision: int
    boss: str = ""
    priorities: list[str] = Field(default_factory=list)
    hp_reserve: int = 0
    release_potions: list[str] = Field(default_factory=list)
    reconsider_when: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class CombatFeedback(BaseModel):
    act: int | None
    floor: int
    hp_lost: int = 0
    hp_restored: int = 0
    unspent_energy: int = 0
    potions_used: int = 0
    observed_actions: int = 0
    ended: bool = False


class RunMemory(BaseModel):
    run_id: str
    game_version: str
    instance_id: str = Field(default_factory=lambda: uuid4().hex)
    policy_version: int = 0
    last_floor: int = 0
    last_act: int | None = 1
    last_character: str = ""
    archetype_scores: dict[str, float] = Field(default_factory=dict)
    needs: dict[str, float] = Field(default_factory=dict)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    boss_plan: str = ""
    potion_policy: str = "Use potions when they prevent substantial HP loss; do not die hoarding them."
    gold_policy: str = "Reserve gold for a meaningful deck improvement."
    route_preferences: list[str] = Field(default_factory=list)
    route_horizon: dict = Field(default_factory=dict)
    elite_readiness: float = 0
    derived_metrics: dict[str, float] = Field(default_factory=dict)
    intent: RunIntent | None = None
    combat_feedback: list[CombatFeedback] = Field(default_factory=list)
    key_decisions: list[str] = Field(default_factory=list)
    outcome: str | None = None
