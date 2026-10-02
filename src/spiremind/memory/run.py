from uuid import uuid4

from pydantic import BaseModel, Field


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
    key_decisions: list[str] = Field(default_factory=list)
    outcome: str | None = None
