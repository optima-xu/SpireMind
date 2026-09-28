from pydantic import BaseModel, ConfigDict

from .enums import ActionKind


class Action(BaseModel):
    """A command bound to a single observed decision, never free-form model params."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    decision_id: str
    kind: ActionKind
    label: str = ""
    description: str = ""
    card_id: str | None = None
    target_id: str | None = None
    node_id: str | None = None
    item_id: str | None = None
    option_id: str | None = None
    character: str | None = None
    ascension: int | None = None
    risk_tags: tuple[str, ...] = ()


class ActionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: str
    action_id: str
    previous_decision_id: str
    next_decision_id: str | None = None
    error: str | None = None
