"""Decision contracts, run goals, token budgets, provider & environment ports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from spiremind.domain.state import Action, ActionResult, GameState

# --- from core/decision.py ---

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
    forecast: dict[str, int] | None = Field(default=None, max_length=6)


class Decision(BaseModel):
    action: Action
    reason: str
    confidence: float = 0
    strategy_update: StrategyUpdate | None = None
    model_name: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    calculations: list[dict[str, str]] = Field(default_factory=list)
    fallback: bool = False
    provider_error: str | None = None
    context_id: str | None = None
    policy_rule: str | None = None
    action_evaluation: dict | None = None


# --- from core/run.py ---


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


# --- from core/working.py ---


class WorkingMemory(BaseModel):
    current_goal: str = ""
    combat_floor: int | None = None
    combat_turn: int | None = None
    lost_hp_this_turn: bool = False


# --- from core/context.py ---


class Skill(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    game_version: str
    character: str
    required_hand: tuple[str, ...] = ()
    required_powers: tuple[str, ...] = ()
    instructions: tuple[str, ...]
    confidence: float = Field(ge=0, le=1)
    confirmed: bool
    source: str


@dataclass(frozen=True)
class MemoryContext:
    snapshot_id: str
    run: dict
    working: dict
    skills: tuple[Skill, ...]
    assessment: dict | None = None
    instance_id: str = ""
    policy_version: int = 0
    handoff: dict | None = None
    experiences: dict | None = None
    option_comparisons: tuple[dict, ...] = ()


@dataclass(frozen=True)
class AgentContext:
    id: str
    system: str
    user: str
    estimated_tokens: int
    packages: tuple[str, ...]
    dropped_layers: tuple[str, ...]
    action_evaluations: tuple[dict, ...] = ()


# --- from core/budget.py ---


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def estimate_tokens(value) -> int:
    # Model-independent conservative estimate, not a tokenizer/cost measurement.
    text = value if isinstance(value, str) else encode(value)
    return (len(text.encode("utf-8")) + 2) // 3


@dataclass(frozen=True)
class ContextBudget:
    target: int = 4000
    maximum: int = 16000


class ContextOverflow(ValueError):
    pass


# --- from core/model.py ---


class DecisionProvider(Protocol):
    async def choose(self, context, legal_ids: set[str]): ...


class ReflectionProvider(Protocol):
    async def reflect(self, evidence: list[dict]) -> list[dict]: ...


class BudgetExceeded(RuntimeError):
    pass


class RequestBudget:
    """Reserve the entire possible request before dispatch; reconcile observed usage."""

    def __init__(self, max_requests: int | None, max_tokens: int | None, parent=None):
        self.max_requests, self.max_tokens = max_requests, max_tokens
        self.requests = self.tokens = self.reserved = 0
        self.parent = parent

    def reserve(self, tokens):
        if (self.max_requests is not None and self.requests >= self.max_requests) or (
            self.max_tokens is not None and self.tokens + self.reserved + tokens > self.max_tokens
        ):
            raise BudgetExceeded("request_budget_exhausted")
        if self.parent:
            self.parent.reserve(tokens)
        self.requests += 1
        self.reserved += tokens
        return tokens

    def settle(self, reservation, tokens):
        self.reserved -= reservation
        self.tokens += tokens
        if self.parent:
            self.parent.settle(reservation, tokens)

    def report(self):
        return dict(
            requests=self.requests,
            tokens=self.tokens,
            reserved=self.reserved,
            max_requests=self.max_requests,
            max_tokens=self.max_tokens,
        )


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelResponse:
    choice: ModelChoice
    model: str
    input_tokens: int
    output_tokens: int
    reasoning_present: bool
    calculations: tuple[dict[str, str], ...] = ()


# --- from core/ports.py ---


class EnvironmentError(RuntimeError):
    pass


class StaleDecision(EnvironmentError):
    pass


class TransitionPending(EnvironmentError):
    pass


class GameEnvironment(Protocol):
    async def observe(self) -> GameState: ...
    async def legal_actions(self) -> list[Action]: ...
    async def execute(self, action: Action) -> ActionResult: ...
    async def verify(self, before: GameState, action: Action, after: GameState) -> bool: ...


class CardCatalog(Protocol):
    generation: int

    def lookup(self, ids: set, version: str): ...
