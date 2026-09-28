from spiremind.core.actions import Action
from spiremind.core.enums import ActionKind
from spiremind.core.state import GameState
from spiremind.environment.base import StaleDecision


class ActionValidator:
    def validate(self, state: GameState, action: Action) -> None:
        if state.terminal and action.kind != ActionKind.RETURN_TO_MAIN_MENU:
            raise ValueError("Run is already over")
        if action.decision_id != state.decision_id:
            raise StaleDecision("Action belongs to a different decision")
        if action not in state.legal_actions:
            raise ValueError("Action is not an exact member of current legal actions")
