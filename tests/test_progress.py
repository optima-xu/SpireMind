import json
from pathlib import Path

import pytest

from spiremind.core.actions import Action
from spiremind.core.enums import ActionKind, Scene
from spiremind.core.state import GameState, PublicFacts, RunState
from spiremind.environment.normalize import normalize
from spiremind.runtime.progress import NoProgress, ProgressGuard


def selection(count, decision):
    return GameState(
        scene=Scene.CARD_SELECTION,
        run=RunState(id="real-regression", floor=12),
        revision=count + 1,
        decision_id=decision,
        game_version="v0.111.0",
        scene_facts=PublicFacts.of(
            {
                "kind": "simple_card_select",
                "prompt": "Choose two cards",
                "selected_count": count,
                "min_select": 2,
                "max_select": 2,
                "requires_confirmation": False,
            }
        ),
        legal_actions=tuple(
            Action(id=f"select:{i}", decision_id=decision, kind=ActionKind.SELECT_CARD, card_id=f"ref:{i}")
            for i in range(3)
        ),
    )


def test_multiselect_retains_choice_and_reaches_required_count():
    guard = ProgressGuard()
    state = selection(0, "none")
    # A model that always picks the first offered card used to toggle it forever.
    first = guard.policy_state(state).legal_actions[0]
    after = selection(1, "one")
    guard.confirmed(state, first, after)
    policy = guard.policy_state(after)
    assert first.id not in {a.id for a in policy.legal_actions}
    assert policy.scene_facts.unpack()["known_selected_card_refs"] == [first.card_id]
    second = policy.legal_actions[0]
    assert second.card_id != first.card_id
    guard.confirmed(after, second, selection(2, "two"))
    assert len(guard.selected) == 2
    # Original environment actions stay unchanged, so validation remains authoritative.
    assert len(after.legal_actions) == 3


def test_restart_with_unknown_selection_recovers_from_count_delta():
    guard = ProgressGuard()
    before = selection(1, "one")
    toggled = guard.policy_state(before).legal_actions[0]
    after = selection(0, "none")
    guard.confirmed(before, toggled, after)
    assert not guard.selected
    first = guard.policy_state(after).legal_actions[0]
    guard.confirmed(after, first, before)
    assert first.id not in {a.id for a in guard.policy_state(before).legal_actions}


def test_inconsistent_count_and_selection_exit_clear_inferred_state():
    guard = ProgressGuard()
    before, after = selection(0, "none"), selection(1, "one")
    guard.policy_state(before)
    guard.confirmed(before, before.legal_actions[0], after)
    guard.policy_state(before)
    assert not guard.selected
    guard.confirmed(before, before.legal_actions[0], after)
    guard.policy_state(after.model_copy(update={"scene": Scene.EVENT}))
    assert not guard.selected


def test_repeated_verified_cycles_are_bounded():
    guard = ProgressGuard()
    before = selection(0, "stuck")
    for action in before.legal_actions:
        for _ in range(3):
            guard.confirmed(before, action, before)
    with pytest.raises(NoProgress):
        guard.policy_state(before)


def test_captured_game_multiselect_does_not_toggle_first_card_forever():
    raw = json.loads(
        (Path(__file__).parent / "fixtures/v0.111.0-multiselect.json").read_text(encoding="utf-8")
    )
    guard = ProgressGuard()
    empty = normalize(raw, 1, "v0.111.0")
    first = guard.policy_state(empty).legal_actions[-1]
    raw["context"]["selection"]["selected_count"] = 1
    raw["decision_id"] = "acceptance:selection:one"
    one = normalize(raw, 2, "v0.111.0")
    guard.confirmed(empty, first, one)
    assert first.id not in {a.id for a in guard.policy_state(one).legal_actions}
    assert len(guard.policy_state(one).legal_actions) == 7
