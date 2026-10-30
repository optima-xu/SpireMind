"""The in-flight action survives process restarts until memory commits it."""

from dataclasses import dataclass, field
from uuid import uuid4

from spiremind.core.actions import ActionResult
from spiremind.core.context import MemoryContext
from spiremind.core.decision import Decision
from spiremind.core.state import GameState


@dataclass
class PendingTransition:
    state: GameState
    decision: Decision
    receipt: ActionResult
    context: MemoryContext | None
    producer: str
    row: dict
    id: str = field(default_factory=lambda: uuid4().hex)

    def serialize(self):
        return {
            "schema": 1,
            "id": self.id,
            "state": self.state.model_dump(mode="json"),
            "decision": self.decision.model_dump(mode="json"),
            "receipt": self.receipt.model_dump(mode="json"),
            "context": {
                "snapshot_id": self.context.snapshot_id,
                "instance_id": self.context.instance_id,
                "policy_version": self.context.policy_version,
            }
            if self.context
            else None,
            "producer": self.producer,
            "row": self.row,
        }

    @classmethod
    def restore(cls, value):
        if value.get("schema") != 1:
            raise ValueError("Unsupported pending execution schema")
        return cls(
            GameState.model_validate(value["state"]),
            Decision.model_validate(value["decision"]),
            ActionResult.model_validate(value["receipt"]),
            MemoryContext(run={}, working={}, skills=(), **value["context"]) if value["context"] else None,
            value["producer"],
            value["row"],
            value["id"],
        )
