from collections import Counter

from spiremind.core.actions import Action
from spiremind.core.enums import ActionKind, Scene
from spiremind.core.state import GameState, PublicFacts
from spiremind.environment.base import EnvironmentError


class NoProgress(EnvironmentError):
    """A repeated state/action cycle must stop instead of consuming an entire budget."""


class ProgressGuard:
    def __init__(self):
        self.completed = Counter()
        self.selection_key = None
        self.selected: set[str] = set()

    @staticmethod
    def selection_scope(state: GameState):
        if state.scene != Scene.CARD_SELECTION:
            return None
        facts = state.scene_facts.unpack()
        return (
            state.run.id,
            state.run.floor,
            state.combat.turn if state.combat else None,
            facts.get("kind"),
            facts.get("prompt"),
            tuple(sorted(a.card_id or a.id for a in state.legal_actions if a.kind == ActionKind.SELECT_CARD)),
        )

    def policy_state(self, state: GameState) -> GameState:
        """Narrow policy candidates without changing the environment's legal-action contract."""
        key = self.selection_scope(state)
        facts = state.scene_facts.unpack()
        if key != self.selection_key or facts.get("selected_count") == 0:
            self.selected.clear()
        self.selection_key = key
        if self.selected and len(self.selected) > facts.get("selected_count", 0):
            self.selected.clear()  # External edits/unknown transitions invalidate inference.
        actions = tuple(
            a
            for a in state.legal_actions
            if self.completed[(state.decision_id, a.id)] < 3
            and not (key and a.kind == ActionKind.SELECT_CARD and (a.card_id or a.id) in self.selected)
        )
        if state.legal_actions and not actions:
            raise NoProgress("All policy candidates would repeat a verified state/action cycle")
        if key:
            facts |= {
                "known_selected_card_refs": sorted(self.selected),
                "selection_policy": "Keep confirmed selections; add a different card or confirm when ready.",
            }
        return state.model_copy(update={"legal_actions": actions, "scene_facts": PublicFacts.of(facts)})

    def confirmed(self, before: GameState, action: Action, after: GameState):
        self.completed[(before.decision_id, action.id)] += 1
        key = self.selection_scope(before)
        if not key or key != self.selection_scope(after):
            self.selection_key = None
            self.selected.clear()
            return
        old_count = before.scene_facts.unpack().get("selected_count")
        new_count = after.scene_facts.unpack().get("selected_count")
        if action.kind != ActionKind.SELECT_CARD or old_count is None or new_count is None:
            return
        identity = action.card_id or action.id
        if new_count == old_count + 1:
            self.selected.add(identity)
        elif new_count == old_count - 1:
            self.selected.discard(identity)
        elif new_count != old_count:
            self.selected.clear()
        if new_count == 0:
            self.selected.clear()
