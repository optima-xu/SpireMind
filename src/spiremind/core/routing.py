"""Scene ownership shared by routing, memory writes and historical evidence."""

from spiremind.core.enums import Scene
from spiremind.core.state import GameState


def owner_for(state: GameState) -> str:
    if state.scene == Scene.UNKNOWN:
        raise ValueError("Unsupported scene: unknown")
    if state.scene == Scene.COMBAT or (
        state.scene == Scene.CARD_SELECTION and (state.combat or state.scene_facts.unpack().get("in_combat"))
    ):
        return "combat"
    if state.scene == Scene.MAP:
        return "map"
    if state.scene in {Scene.CARD_REWARD, Scene.SHOP, Scene.REST, Scene.CARD_SELECTION}:
        return "run"
    return "event"
