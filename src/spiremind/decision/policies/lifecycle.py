from spiremind.config import GameConfig
from spiremind.core.decision import Decision
from spiremind.core.enums import ActionKind, Scene
from spiremind.core.state import GameState


def lifecycle_decision(state: GameState, config: GameConfig, *, new_run=False) -> Decision | None:
    if state.scene == Scene.GAME_OVER:
        action = next(
            (a for a in state.legal_actions if a.kind == ActionKind.RETURN_TO_MAIN_MENU),
            None,
        )
        if action:
            return Decision(action=action, reason="Clear the previous terminal screen before a new run")
        return None
    if state.scene == Scene.MAIN_MENU:
        if new_run and any(a.kind == ActionKind.CONTINUE_RUN for a in state.legal_actions):
            raise ValueError(
                "An existing run is available. Use resume, or finish/abandon it in the game first."
            )
        for kind in (ActionKind.OPEN_RUN,) if new_run else (ActionKind.CONTINUE_RUN, ActionKind.OPEN_RUN):
            action = next((a for a in state.legal_actions if a.kind == kind), None)
            if action:
                return Decision(
                    action=action, reason="Continue existing run or open standard character select"
                )
        close_submenu = next(
            (a for a in state.legal_actions if a.kind == ActionKind.CLOSE_MENU),
            None,
        )
        if close_submenu:
            return Decision(action=close_submenu, reason="Close the current submenu to reveal run entry")
        raise ValueError("No supported standard run entry on the main menu")
    if state.scene == Scene.CHARACTER_SELECT:
        facts = state.scene_facts.unpack()
        if facts.get("is_multiplayer") or facts.get("is_custom"):
            raise ValueError("v1 lifecycle supports standard single-player runs")
        action = next(
            (
                a
                for a in state.legal_actions
                if a.kind == ActionKind.SELECT_CHARACTER
                and a.character == config.character.lower()
                and a.ascension == config.ascension
            ),
            None,
        )
        if action:
            return Decision(action=action, reason="Select configured character and exact ascension")
        selected = str(facts.get("selected_character_id", "")).lower()
        if selected != config.character.lower() or facts.get("ascension") != config.ascension:
            raise ValueError("Configured character/ascension is not available")
        action = next((a for a in state.legal_actions if a.kind == ActionKind.EMBARK), None)
        if action:
            return Decision(action=action, reason="Start configured standard run")
        raise ValueError("Configured run cannot embark yet")
    return None
