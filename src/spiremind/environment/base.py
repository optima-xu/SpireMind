from typing import Protocol

from spiremind.core.actions import Action, ActionResult
from spiremind.core.state import GameState


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
