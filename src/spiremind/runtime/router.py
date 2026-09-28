from spiremind.core.enums import Scene
from spiremind.core.state import GameState


class SceneRouter:
    def __init__(self, combat, run, map_strategy, event):
        self.strategies = {"combat": combat, "run": run, "map": map_strategy, "event": event}

    def route(self, state: GameState):
        if state.terminal:
            raise ValueError("Terminal states do not require a strategy")
        if state.scene == Scene.COMBAT:
            name = "combat"
        elif state.scene == Scene.CARD_SELECTION:
            name = "combat" if state.combat or state.scene_facts.unpack().get("in_combat") else "run"
        elif state.scene in {Scene.CARD_REWARD, Scene.SHOP, Scene.REST}:
            name = "run"
        elif state.scene == Scene.MAP:
            name = "map"
        elif state.scene in {
            Scene.EVENT,
            Scene.TREASURE,
            Scene.MODAL,
            Scene.MAIN_MENU,
            Scene.CHARACTER_SELECT,
        }:
            name = "event"
        else:
            raise ValueError(f"Unsupported scene: {state.scene.value}")
        return self.strategies[name]
