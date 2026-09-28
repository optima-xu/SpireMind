from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from .actions import Action

RoutePreference = Annotated[str, Field(max_length=120)]


class StrategyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    boss_plan: str | None = Field(default=None, max_length=500)
    potion_policy: str | None = Field(default=None, max_length=300)
    gold_policy: str | None = Field(default=None, max_length=300)
    route_preferences: list[RoutePreference] | None = Field(default=None, max_length=5)
    current_goal: str | None = Field(default=None, max_length=300)


class ModelChoice(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action_id: str = Field(min_length=1, max_length=300)
    reason: str = Field(max_length=800)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    strategy_update: StrategyUpdate | None = None


class Decision(BaseModel):
    action: Action
    reason: str
    confidence: float = 0
    strategy_update: StrategyUpdate | None = None
    model_name: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    fallback: bool = False
    provider_error: str | None = None
    context_id: str | None = None
    policy_rule: str | None = None
