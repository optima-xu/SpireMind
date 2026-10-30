from spiremind.core.actions import Action
from spiremind.core.enums import ActionKind
from spiremind.core.state import GameState


def verify_transition(before: GameState, action: Action, after: GameState) -> bool:
    run_boundary = action.kind in {
        ActionKind.EMBARK,
        ActionKind.CONTINUE_RUN,
        ActionKind.RETURN_TO_MAIN_MENU,
        ActionKind.OPEN_RUN,
        ActionKind.SELECT_CHARACTER,
    }
    return (
        action in before.legal_actions
        and action.decision_id == before.decision_id
        and after.decision_id != before.decision_id
        and after.game_version == before.game_version
        and (run_boundary or after.run.id == before.run.id)
        and (run_boundary or after.run.character == before.run.character)
        and (after.revision > before.revision or (run_boundary and after.run.id != before.run.id))
    )
