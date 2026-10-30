from spiremind.core.routing import owner_for
from spiremind.core.state import GameState


class SceneRouter:
    def __init__(self, combat, run, map_strategy, event):
        self.strategies = {"combat": combat, "run": run, "map": map_strategy, "event": event}

    def route(self, state: GameState):
        if state.terminal:
            raise ValueError("Terminal states do not require a strategy")
        return self.strategies[owner_for(state)]
