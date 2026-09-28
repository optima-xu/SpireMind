from spiremind.core.actions import Action
from spiremind.core.state import GameState


def verify_transition(before: GameState, action: Action, after: GameState) -> bool:
    return (
        action in before.legal_actions
        and action.decision_id == before.decision_id
        and after.decision_id != before.decision_id
        and after.revision > before.revision
    )
