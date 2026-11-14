"""Action validation, multi-selection loop guards, bounded LRU cache, and atomic file replacement."""

from __future__ import annotations

import time
from collections import Counter, OrderedDict
from typing import Generic, TypeVar

from spiremind.domain.decision import EnvironmentError, StaleDecision
from spiremind.domain.state import Action, ActionKind, GameState, PublicFacts, Scene

# --- from core/files.py ---


def replace_file(temporary, target):
    for attempt in range(5):
        try:
            temporary.replace(target)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.01 * 2**attempt)


# --- from core/cache.py ---

K = TypeVar("K")
V = TypeVar("V")


class LRU(Generic[K, V]):
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.values: OrderedDict[K, V] = OrderedDict()
        self.hits = self.misses = 0

    def get(self, key: K) -> tuple[bool, V | None]:
        if key not in self.values:
            self.misses += 1
            return False, None
        self.hits += 1
        self.values.move_to_end(key)
        return True, self.values[key]

    def put(self, key: K, value: V) -> None:
        self.values[key] = value
        self.values.move_to_end(key)
        while len(self.values) > self.capacity:
            self.values.popitem(last=False)

    def clear(self) -> None:
        self.values.clear()

    def stats(self) -> dict:
        return dict(hits=self.hits, misses=self.misses, size=len(self.values), capacity=self.capacity)


# --- from core/validation.py ---


class ActionValidator:
    def validate(self, state: GameState, action: Action) -> None:
        if state.terminal and action.kind != ActionKind.RETURN_TO_MAIN_MENU:
            raise ValueError("Run is already over")
        if action.decision_id != state.decision_id:
            raise StaleDecision("Action belongs to a different decision")
        if action not in state.legal_actions:
            raise ValueError("Action is not an exact member of current legal actions")


# --- from decision/progress.py ---


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
