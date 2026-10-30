"""Values exchanged between preparation, policies and model transports."""

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field


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
