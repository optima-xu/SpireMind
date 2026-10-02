import copy
import json
from pathlib import Path

import httpx
import pytest

from spiremind.config import GameConfig
from spiremind.core.actions import Action
from spiremind.core.enums import ActionKind, Scene
from spiremind.core.state import (
    Card,
    CombatState,
    Enemy,
    GameState,
    Intent,
    Pile,
    Power,
    PublicFacts,
    RunState,
)
from spiremind.environment.mcp import MCPEnvironment
from spiremind.strategies.combat import CombatStrategy
from spiremind.strategies.combat_tactics import (
    MAX_SURVIVAL_SEARCH_TRANSITIONS,
    assess,
    early_boss_potion_action,
    forced_survival_action,
    visible_offense_plan,
    visible_survival_plan,
)


@pytest.fixture
def cases():
    rows = json.loads(
        (Path(__file__).parent / "fixtures/v0.111.0-boss-regressions.json").read_text(encoding="utf-8")
    )
    return {x["case"]: GameState.model_validate(x["state"]) for x in rows}


def test_visible_lethal_is_avoided_and_potions_work_at_zero_energy(cases):
    one = cases["fatal_one"]
    action, rule = forced_survival_action(one, assess(one))
    assert action.id == "combat:play:1" and rule == "avoid_visible_lethal_with_block"
    row = next(r for r in assess(one)["evaluated_actions"] if r["action_id"] == action.id)
    assert row["hp_after_intents"] == 4
    zero = cases["fatal_zero"]
    zero_facts = assess(zero)
    action, _ = forced_survival_action(zero, zero_facts)
    assert action.id == "combat:use_potion:0:enemy:0"
    row = next(r for r in zero_facts["evaluated_actions"] if r["action_id"] == action.id)
    assert row["hp_after_intents"] == 2
    assert not zero_facts["no_visible_survival"]


def test_multi_enemy_boss_is_detected_by_boss_floor(cases):
    state = cases["fatal_zero"]
    state = state.model_copy(update={"run": state.run.model_copy(update={"floor": 17, "boss": "Boss Squad"})})

    assert assess(state)["in_boss_fight"] is True


def test_damage_caps_multihit_and_strength_ownership(cases):
    rows = assess(cases["shield"])["evaluated_actions"]
    assert next(r for r in rows if r["action_id"] == "combat:play:0:enemy:0")["hp_damage"] == 1
    boomerang = next(r for r in rows if r["action_id"] == "combat:play:1")
    assert boomerang["hp_damage"] == boomerang["cap_layers_consumed"] == 3
    rows = assess(cases["enemy_strength"])["evaluated_actions"]
    assert next(r for r in rows if r["action_id"] == "combat:play:1:enemy:0")["hp_damage"] == 10


def test_known_neutral_enemy_power_does_not_hide_nonlethal_damage(cases):
    state = cases["enemy_strength"]
    card = next(c for c in state.combat.hand if c.id == "thunderclap").model_copy(
        update={"values": PublicFacts.of({"Damage": 14, "VulnerablePower": 1})}
    )
    enemy = state.combat.enemies[0].model_copy(
        update={
            "hp": 73,
            "powers": (
                Power(id="personal_hive_power", amount=2),
                Power(id="vulnerable_power", amount=1),
            ),
        }
    )
    action = next(a for a in state.legal_actions if a.id == "combat:play:2")
    end = next(a for a in state.legal_actions if a.kind == ActionKind.END_TURN)
    state = state.model_copy(
        update={
            "combat": state.combat.model_copy(update={"hand": (card,), "enemies": (enemy,)}),
            "legal_actions": (end, action),
        }
    )
    row = next(r for r in assess(state)["evaluated_actions"] if r["action_id"] == action.id)
    assert row["hp_damage"] == 21
    assert row["verified_lethal"] is False


def test_minion_trait_does_not_turn_small_hit_into_a_kill(cases):
    state = cases["enemy_strength"]
    follower = state.combat.enemies[0].model_copy(
        update={"hp": 48, "powers": (Power(id="minion_power", amount=1),)}
    )
    state = state.model_copy(update={"combat": state.combat.model_copy(update={"enemies": (follower,)})})
    row = next(
        row for row in assess(state)["evaluated_actions"] if row["action_id"] == "combat:play:1:enemy:0"
    )
    assert row["target_hp"] == 48
    assert row["hp_damage"] == 10
    assert row["target_hp_after"] == 38
    assert row["verified_lethal"] is False


def test_weak_does_not_stack_damage_reduction(cases):
    state = cases["fatal_zero"]
    enemy = state.combat.enemies[0]
    enemy = enemy.model_copy(update={"powers": enemy.powers + (Power(id="weak_power", amount=2),)})
    state = state.model_copy(update={"combat": state.combat.model_copy(update={"enemies": (enemy,)})})
    assert forced_survival_action(state, assess(state)) is None


def test_unknown_powers_and_unknown_version_are_not_precise_predictions(cases):
    state = cases["shield"]
    enemy = state.combat.enemies[0].model_copy(update={"powers": (Power(id="unknown_power", amount=1),)})
    state = state.model_copy(
        update={
            "run": state.run.model_copy(update={"hp": 10}),
            "combat": state.combat.model_copy(update={"enemies": (enemy,)}),
        }
    )
    facts = assess(state)
    assert all("hp_damage" not in r for r in facts["evaluated_actions"])
    assert not facts["visible_survival_known"]
    assert facts["survival_status"] == "unknown"
    assert not facts["no_visible_survival"]
    state = cases["fatal_zero"].model_copy(update={"game_version": "v0.112.0"})
    assert forced_survival_action(state, assess(state)) is None


def two_defend_state(base, hp=2, incoming=10):
    defend = next(c for c in base.combat.hand if c.id == "defend_ironclad")
    second = defend.model_copy(update={"ref": defend.ref + ":second"})
    enemy = base.combat.enemies[0]
    intent = enemy.intents[0].model_copy(update={"damage": incoming, "hits": 1})
    enemy = enemy.model_copy(update={"intents": (intent,)})
    end = next(a for a in base.legal_actions if a.kind == ActionKind.END_TURN)
    actions = tuple(
        Action(
            id=f"combat:play:defend:{index}",
            decision_id=base.decision_id,
            kind=ActionKind.PLAY_CARD,
            label=f"Play defend {index}",
            card_id=card.ref,
        )
        for index, card in enumerate((defend, second))
    )
    combat = base.combat.model_copy(
        update={"energy": 2, "block": 0, "hand": (defend, second), "enemies": (enemy,)}
    )
    return base.model_copy(
        update={
            "run": base.run.model_copy(update={"hp": hp}),
            "combat": combat,
            "legal_actions": (end,) + actions,
        }
    )


def two_enemy_state(base, hp=5, attacks=(4, 6), enemy_hp=6):
    first = base.combat.enemies[0]
    first = first.model_copy(
        update={
            "id": "enemy_a",
            "ref": "enemy:a",
            "name": "A",
            "hp": enemy_hp,
            "max_hp": enemy_hp,
            "block": 0,
            "powers": (),
            "intents": (first.intents[0].model_copy(update={"damage": attacks[0], "hits": 1}),),
        }
    )
    second = first.model_copy(
        update={
            "id": "enemy_b",
            "ref": "enemy:b",
            "name": "B",
            "intents": (first.intents[0].model_copy(update={"damage": attacks[1], "hits": 1}),),
        }
    )
    return base.model_copy(
        update={
            "run": base.run.model_copy(update={"hp": hp, "boss": ""}),
            "combat": base.combat.model_copy(update={"energy": 2, "block": 0, "enemies": (first, second)}),
        }
    )


def bygone_effigy_lethal_state(base):
    """Reproduce the floor-7 turn that the old one-card guard failed to see."""
    twin = Card(
        id="twin_strike",
        ref="card:twin",
        name="Twin Strike",
        type="attack",
        cost=1,
        text="Deal 7 damage twice.",
        values=PublicFacts.of({"Damage": 7}),
        playable=True,
    )
    strike_a = Card(
        id="strike_ironclad",
        ref="card:strike-a",
        name="Strike",
        type="attack",
        cost=1,
        text="Deal 8 damage.",
        values=PublicFacts.of({"Damage": 8}),
        playable=True,
    )
    defend = Card(
        id="defend_ironclad",
        ref="card:defend",
        name="Defend",
        type="skill",
        cost=1,
        text="Gain 5 Block.",
        values=PublicFacts.of({"Block": 5}),
        playable=True,
    )
    strike_b = strike_a.model_copy(update={"ref": "card:strike-b"})
    enemy = Enemy(
        id="bygone_effigy",
        ref="enemy:effigy",
        name="Bygone Effigy",
        hp=32,
        max_hp=127,
        powers=(
            Power(
                id="slow_power",
                amount=1,
                trigger_progress=PublicFacts.of({"parameters": {"SlowAmount": 0, "DisplayAmount": 0}}),
            ),
            Power(id="strength_power", amount=10),
        ),
        intents=(Intent(type="Attack", damage=23, hits=1),),
    )
    cards = (twin, strike_a, defend, strike_b)
    end = next(a for a in base.legal_actions if a.kind == ActionKind.END_TURN)
    actions = tuple(
        Action(
            id=f"combat:play:{index}" + (":enemy:0" if card.type == "attack" else ""),
            decision_id=base.decision_id,
            kind=ActionKind.PLAY_CARD,
            label=f"Play {card.name}",
            card_id=card.ref,
            target_id=enemy.ref if card.type == "attack" else None,
        )
        for index, card in enumerate(cards, start=1)
    )
    return base.model_copy(
        update={
            "run": base.run.model_copy(update={"hp": 12, "max_hp": 91}),
            "combat": base.combat.model_copy(
                update={
                    "energy": 3,
                    "block": 0,
                    "hand": cards,
                    "enemies": (enemy,),
                }
            ),
            "legal_actions": (end,) + actions,
        }
    )


def test_slow_combo_lethal_is_found_and_forced_before_low_value_block(cases):
    state = bygone_effigy_lethal_state(cases["fatal_one"])

    facts = assess(state)
    action, rule = forced_survival_action(state, facts)

    assert facts["visible_damage_plan_known"]
    assert facts["visible_max_damage"] == 32
    assert len(facts["verified_lethal_plan"]) == 3
    assert facts["verified_lethal_plan"][-1] == "combat:play:1:enemy:0"
    assert set(facts["verified_lethal_plan"][:2]) == {
        "combat:play:2:enemy:0",
        "combat:play:4:enemy:0",
    }
    assert action.id == facts["verified_lethal_plan"][0]
    assert action.card_id in {"card:strike-a", "card:strike-b"}
    assert rule == "follow_verified_lethal_plan"
    assert facts["minimum_additional_block_to_survive"] == 12


def test_nonlethal_turn_exposes_damage_plan_without_forcing_reckless_offense(cases):
    state = bygone_effigy_lethal_state(cases["fatal_one"])
    enemy = state.combat.enemies[0].model_copy(update={"hp": 64})
    state = state.model_copy(
        update={
            "run": state.run.model_copy(update={"hp": 51}),
            "combat": state.combat.model_copy(update={"enemies": (enemy,)}),
        }
    )

    facts = assess(state)

    assert facts["visible_max_damage"] == 32
    assert facts["verified_lethal_plan"] == []
    assert facts["minimum_additional_block_to_survive"] == 0
    assert facts["visible_survival_margin_if_end_now"] == 28
    assert forced_survival_action(state, facts) is None
    task = CombatStrategy(None, None, None).task_for(state, None)
    assert "minimum_additional_block_to_survive is 0" in task
    assert '"visible_max_damage":32' in task


def test_unknown_attack_card_makes_offense_plan_abstain(cases):
    state = bygone_effigy_lethal_state(cases["fatal_one"])
    unknown = Card(
        id="mystery_attack",
        ref="card:mystery",
        name="Mystery Attack",
        type="attack",
        cost=0,
        values=PublicFacts.of({"Damage": 99}),
        playable=True,
    )
    action = Action(
        id="combat:play:mystery:enemy:0",
        decision_id=state.decision_id,
        kind=ActionKind.PLAY_CARD,
        card_id=unknown.ref,
        target_id=state.combat.enemies[0].ref,
    )
    state = state.model_copy(
        update={
            "combat": state.combat.model_copy(update={"hand": state.combat.hand + (unknown,)}),
            "legal_actions": state.legal_actions + (action,),
        }
    )

    plan = visible_offense_plan(state)
    facts = assess(state)

    assert not plan["complete"]
    assert plan["max_damage"] is None
    assert not facts["visible_damage_plan_known"]
    assert facts["verified_lethal_plan"] == []


def test_offense_search_abstains_at_its_transition_bound(cases):
    state = bygone_effigy_lethal_state(cases["fatal_one"])

    plan = visible_offense_plan(state, transition_limit=2)

    assert plan["transitions"] == 2
    assert plan["truncated"]
    assert not plan["complete"]
    assert plan["max_damage"] is None
    assert plan["max_damage_plan"] == []
    assert plan["lethal_plan"] == []


def test_multi_action_survival_plan_is_forced_before_one_card_can_save(cases):
    state = two_defend_state(cases["fatal_one"])
    facts = assess(state)
    assert len(facts["visible_survival_plan"]) == 2
    assert all(r.get("hp_after_intents", 0) <= 0 for r in facts["evaluated_actions"])
    action, rule = forced_survival_action(state, facts)
    assert action.id == facts["visible_survival_plan"][0]
    assert rule == "follow_visible_survival_plan"


def test_survival_plan_combines_weak_potion_with_block(cases):
    base = cases["fatal_one"]
    defend = next(c for c in base.combat.hand if c.id == "defend_ironclad")
    enemy = base.combat.enemies[0]
    enemy = enemy.model_copy(update={"intents": (enemy.intents[0].model_copy(update={"damage": 19}),)})
    end = next(a for a in base.legal_actions if a.kind == ActionKind.END_TURN)
    block = next(a for a in base.legal_actions if a.card_id == defend.ref)
    potion = next(a for a in base.legal_actions if a.kind == ActionKind.USE_POTION)
    state = base.model_copy(
        update={
            "combat": base.combat.model_copy(
                update={"energy": 1, "block": 0, "hand": (defend,), "enemies": (enemy,)}
            ),
            "legal_actions": (end, block, potion),
        }
    )
    facts = assess(state)
    assert len(facts["visible_survival_plan"]) == 2
    assert not facts["visible_one_step_survival_actions"]
    _, rule = forced_survival_action(state, facts)
    assert rule == "follow_visible_survival_plan"


def test_exact_zero_hp_is_not_mislabeled_as_a_survival_plan(cases):
    state = two_defend_state(cases["fatal_one"], hp=1, incoming=11)
    facts = assess(state)
    assert facts["visible_survival_plan"] == []
    assert facts["survival_status"] == "dead"
    assert facts["no_visible_survival"]
    assert forced_survival_action(state, facts) is None


def test_killing_one_attacker_twice_does_not_remove_its_damage_twice(cases):
    base = two_enemy_state(cases["fatal_one"])
    strike = next(c for c in base.combat.hand if c.id == "strike_ironclad")
    second = strike.model_copy(update={"ref": f"{strike.ref}:second"})
    end = next(a for a in base.legal_actions if a.kind == ActionKind.END_TURN)
    attacks = tuple(
        Action(
            id=f"combat:play:{index}:enemy:0",
            decision_id=base.decision_id,
            kind=ActionKind.PLAY_CARD,
            label=f"Strike A with card {index}",
            card_id=card.ref,
            target_id="enemy:a",
        )
        for index, card in enumerate((strike, second))
    )
    state = base.model_copy(
        update={
            "combat": base.combat.model_copy(update={"hand": (strike, second)}),
            "legal_actions": (end,) + attacks,
        }
    )

    facts = assess(state)

    assert facts["incoming_attack_damage"] == 10
    assert all(row["verified_lethal"] for row in facts["evaluated_actions"])
    assert facts["visible_survival_plan"] == []
    assert facts["survival_status"] == "dead"
    assert forced_survival_action(state, facts) is None


def test_one_targetable_card_cannot_be_used_against_two_enemies(cases):
    base = two_enemy_state(cases["fatal_one"], hp=4, attacks=(4, 4))
    strike = next(c for c in base.combat.hand if c.id == "strike_ironclad")
    end = next(a for a in base.legal_actions if a.kind == ActionKind.END_TURN)
    attacks = tuple(
        Action(
            id=f"combat:play:0:enemy:{index}",
            decision_id=base.decision_id,
            kind=ActionKind.PLAY_CARD,
            label=f"Strike {enemy.name}",
            card_id=strike.ref,
            target_id=enemy.ref,
        )
        for index, enemy in enumerate(base.combat.enemies)
    )
    state = base.model_copy(
        update={
            "combat": base.combat.model_copy(update={"hand": (strike,)}),
            "legal_actions": (end,) + attacks,
        }
    )

    facts = assess(state)

    assert facts["visible_survival_plan"] == []
    assert facts["survival_status"] == "dead"


def test_one_targetable_weak_potion_cannot_be_used_on_two_enemies(cases):
    base = two_enemy_state(cases["fatal_one"], hp=8)
    end = next(a for a in base.legal_actions if a.kind == ActionKind.END_TURN)
    potions = tuple(
        Action(
            id=f"combat:use_potion:0:enemy:{index}",
            decision_id=base.decision_id,
            kind=ActionKind.USE_POTION,
            label=f"Use Weak Potion on {enemy.name}",
            target_id=enemy.ref,
            item_id="weak_potion",
            option_id="0",
        )
        for index, enemy in enumerate(base.combat.enemies)
    )
    state = base.model_copy(
        update={
            "combat": base.combat.model_copy(update={"energy": 0, "hand": ()}),
            "legal_actions": (end,) + potions,
        }
    )

    facts = assess(state)

    assert facts["visible_survival_plan"] == []
    assert facts["survival_status"] == "dead"


def test_weak_reduction_on_one_target_is_not_stacked(cases):
    base = cases["fatal_one"]
    enemy = base.combat.enemies[0].model_copy(
        update={
            "powers": (),
            "intents": (base.combat.enemies[0].intents[0].model_copy(update={"damage": 12}),),
        }
    )
    end = next(a for a in base.legal_actions if a.kind == ActionKind.END_TURN)
    potions = tuple(
        Action(
            id=f"combat:use_potion:{slot}:enemy:0",
            decision_id=base.decision_id,
            kind=ActionKind.USE_POTION,
            label=f"Use Weak Potion {slot}",
            target_id=enemy.ref,
            item_id="weak_potion",
            option_id=str(slot),
        )
        for slot in (0, 2)
    )
    state = base.model_copy(
        update={
            "run": base.run.model_copy(update={"hp": 7}),
            "combat": base.combat.model_copy(
                update={"energy": 0, "block": 0, "hand": (), "enemies": (enemy,)}
            ),
            "legal_actions": (end,) + potions,
        }
    )

    facts = assess(state)

    assert all(row["intent_reduction_estimate"] == 3 for row in facts["evaluated_actions"])
    assert facts["visible_survival_plan"] == []
    assert facts["survival_status"] == "dead"


def test_unknown_attack_damage_never_counts_as_zero_damage(cases):
    base = cases["fatal_one"]
    enemy = base.combat.enemies[0]
    enemy = enemy.model_copy(update={"intents": (enemy.intents[0].model_copy(update={"damage": None}),)})
    end = next(a for a in base.legal_actions if a.kind == ActionKind.END_TURN)
    state = base.model_copy(
        update={
            "combat": base.combat.model_copy(update={"hand": (), "enemies": (enemy,)}),
            "legal_actions": (end,),
        }
    )

    facts = assess(state)

    assert facts["hp_after_intents_if_end_now"] == state.run.hp
    assert facts["intent_damage_incomplete"]
    assert facts["minimum_additional_block_to_survive"] is None
    assert facts["visible_survival_margin_if_end_now"] is None
    assert facts["visible_survival_plan"] == []
    assert facts["visible_one_step_survival_actions"] == []
    assert facts["survival_status"] == "unknown"
    assert not facts["no_visible_survival"]


def test_bounded_search_returns_stable_best_plan_with_many_target_variants(cases):
    base = cases["fatal_one"]
    state = base.model_copy(
        update={
            "run": base.run.model_copy(update={"hp": 1}),
            "combat": base.combat.model_copy(update={"energy": 18, "block": 0}),
        }
    )
    rows = [
        {
            "action_id": f"combat:play:{card}:enemy:{target}",
            "resource_key": f"card:{card}",
            "target_ref": f"enemy:{target}",
            "cost": 1,
            "block_gain": 100 if (card, target) == (0, 0) else 1,
        }
        for card in range(18)
        for target in range(6)
    ]
    forward_stats = {}
    reverse_stats = {}

    forward = visible_survival_plan(state, rows, 100, search_stats=forward_stats)
    reverse = visible_survival_plan(state, list(reversed(rows)), 100, search_stats=reverse_stats)

    assert forward == reverse == ["combat:play:0:enemy:0"]
    assert forward_stats == reverse_stats
    assert forward_stats["candidate_actions"] == 108
    assert forward_stats["resource_groups"] == 18
    assert forward_stats["expanded_nodes"] < forward_stats["candidate_actions"]
    assert forward_stats["transitions"] == forward_stats["candidate_actions"]
    assert forward_stats["optimal"] and not forward_stats["truncated"]


def test_bounded_search_abstains_when_proof_exceeds_transition_limit(cases):
    base = cases["fatal_one"]
    state = base.model_copy(
        update={
            "run": base.run.model_copy(update={"hp": 1}),
            "combat": base.combat.model_copy(update={"energy": 20, "block": 0}),
        }
    )
    rows = [
        {
            "action_id": f"combat:play:{card}:enemy:{target}",
            "resource_key": f"card:{card}",
            "target_ref": f"enemy:{target}",
            "cost": 1,
            "block_gain": 1,
        }
        for card in range(20)
        for target in range(4)
    ]
    stats = {}

    plan = visible_survival_plan(state, rows, 100, search_stats=stats)

    assert plan == []
    assert stats["transitions"] == MAX_SURVIVAL_SEARCH_TRANSITIONS
    assert stats["transition_limit"] == MAX_SURVIVAL_SEARCH_TRANSITIONS
    assert stats["expanded_nodes"] <= MAX_SURVIVAL_SEARCH_TRANSITIONS + 1
    assert stats["truncated"] and not stats["optimal"]


def test_truncated_survival_search_cannot_certify_visible_death():
    cards = tuple(
        Card(
            id="defend_ironclad",
            ref=f"card:{index}",
            type="skill",
            cost=1,
            values=PublicFacts.of({"Block": 1}),
        )
        for index in range(16)
    )
    enemy = Enemy(id="enemy", ref="enemy:0", hp=40, intents=(Intent(type="Attack", damage=100),))
    state = GameState(
        scene=Scene.COMBAT,
        run=RunState(id="run", hp=1, max_hp=80),
        combat=CombatState(energy=16, hand=cards, enemies=(enemy,)),
        legal_actions=(
            Action(id="end", decision_id="d", kind=ActionKind.END_TURN),
            *(
                Action(id=f"play:{index}", decision_id="d", kind=ActionKind.PLAY_CARD, card_id=card.ref)
                for index, card in enumerate(cards)
            ),
        ),
        revision=1,
        decision_id="d",
        game_version="v0.111.0",
    )
    facts = assess(state)
    assert facts["survival_search"]["truncated"]
    assert facts["survival_status"] == "unknown"
    assert not facts["no_visible_survival"]


def test_survival_search_uses_consumables_then_energy_then_action_count(cases):
    base = cases["fatal_one"]
    state = base.model_copy(
        update={
            "run": base.run.model_copy(update={"hp": 5}),
            "combat": base.combat.model_copy(update={"energy": 2, "block": 0}),
        }
    )
    rows = [
        {
            "action_id": "expensive",
            "resource_key": "card:expensive",
            "cost": 2,
            "block_gain": 6,
        },
        {
            "action_id": "cheap-a",
            "resource_key": "card:cheap-a",
            "cost": 0,
            "block_gain": 3,
        },
        {
            "action_id": "cheap-b",
            "resource_key": "card:cheap-b",
            "cost": 1,
            "block_gain": 3,
        },
        {
            "action_id": "potion",
            "resource_key": "potion:0",
            "cost": 0,
            "consumable": True,
            "block_gain": 20,
        },
    ]
    stats = {}

    plan = visible_survival_plan(state, rows, 10, search_stats=stats)

    assert plan == ["cheap-a", "cheap-b"]
    assert stats["optimal"] and not stats["truncated"]


def test_verified_lethal_is_forced_when_it_removes_the_only_attack(cases):
    base = cases["fatal_one"]
    initial = assess(base)
    row = next(r for r in initial["evaluated_actions"] if r.get("hp_damage", 0) > 0)
    attack = next(a for a in base.legal_actions if a.id == row["action_id"])
    end = next(a for a in base.legal_actions if a.kind == ActionKind.END_TURN)
    enemy = base.combat.enemies[0].model_copy(update={"hp": row["hp_damage"]})
    state = base.model_copy(
        update={
            "combat": base.combat.model_copy(update={"enemies": (enemy,)}),
            "legal_actions": (end, attack),
        }
    )
    facts = assess(state)
    action, rule = forced_survival_action(state, facts)
    assert action.id == attack.id
    assert rule == "take_verified_lethal"


async def test_emergency_rule_is_logged_without_requesting_model(cases):
    strategy = CombatStrategy(None, None, None)
    decision = await strategy.decide(cases["fatal_one"], None)
    assert decision.policy_rule == "avoid_visible_lethal_with_block"
    assert decision.action in cases["fatal_one"].legal_actions
    assert not decision.fallback and decision.model_name is None


async def test_only_lethal_end_turn_is_audited_as_forced_loss(cases):
    state = two_defend_state(cases["fatal_one"], hp=1, incoming=11)
    end = next(a for a in state.legal_actions if a.kind == ActionKind.END_TURN)
    state = state.model_copy(
        update={"legal_actions": (end,), "combat": state.combat.model_copy(update={"energy": 0})}
    )
    decision = await CombatStrategy(None, None, None).decide(state, None)
    assert decision.action == end
    assert decision.policy_rule == "forced_lethal_end_turn"


async def test_stable_nonplay_combat_waits_without_sending_any_action(raw_decision, tmp_path):
    not_ready = copy.deepcopy(raw_decision)
    not_ready["decision_id"] = "animation"
    not_ready["context"]["combat"]["player_turn_phase"] = "None"
    not_ready["context"]["combat"]["hand"] = []
    not_ready["context"]["combat"]["player"]["energy"] = 0
    requests = []

    def handler(req):
        requests.append(req.url.path)
        if req.url.path.endswith("current"):
            return httpx.Response(200, json={"available": True, "decision": not_ready})
        assert req.url.path.endswith("wait")
        assert json.loads(req.content)["after_decision_id"] == "animation"
        return httpx.Response(200, json={"available": True, "decision": raw_decision})

    env = MCPEnvironment(
        GameConfig(),
        tmp_path / "p.json",
        httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler)),
    )
    state = await env.observe()
    assert state.combat.turn_phase == "Play"
    assert requests == ["/v2/decision/current", "/v2/decision/wait"]
    await env.close()


async def test_plow_threshold_prevents_visible_boss_attack():
    """Floor 17 replay: 170 HP, 150 HP stun threshold, 23 damage, 28 incoming."""
    enemy = Enemy(
        id="ceremonial_beast",
        ref="enemy:boss",
        hp=170,
        max_hp=252,
        intents=(Intent(type="Attack", damage=28, hits=1),),
        powers=(
            Power(
                id="plow_power",
                amount=150,
                description="生命值第一次下降到150或更低时，将其击晕并使其失去所有力量。",
            ),
            Power(id="strength_power", amount=10),
        ),
    )
    attack = Card(
        id="perfected_strike",
        ref="card:perfected",
        type="attack",
        cost=2,
        values=PublicFacts.of({"CalculatedDamage": 23}),
    )
    block = Card(
        id="defend_ironclad", ref="card:defend", type="skill", cost=1, values=PublicFacts.of({"Block": 10})
    )
    state = GameState(
        scene=Scene.COMBAT,
        run=RunState(id="boss", character="ironclad", floor=17, hp=6, max_hp=80, boss="仪式兽"),
        combat=CombatState(energy=3, hand=(attack, block), enemies=(enemy,)),
        legal_actions=(
            Action(id="combat:end_turn", decision_id="d", kind=ActionKind.END_TURN),
            Action(
                id="combat:play:attack",
                decision_id="d",
                kind=ActionKind.PLAY_CARD,
                card_id=attack.ref,
                target_id=enemy.ref,
            ),
            Action(id="combat:play:block", decision_id="d", kind=ActionKind.PLAY_CARD, card_id=block.ref),
        ),
        revision=1,
        decision_id="d",
        game_version="v0.111.0",
    )

    facts = assess(state)
    control = next(r for r in facts["evaluated_actions"] if r["action_id"] == "combat:play:attack")
    assert control["triggers_visible_stun"]
    assert control["removed_incoming_damage"] == 28
    assert control["hp_after_intents_if_played"] == 6
    assert forced_survival_action(state, facts)[0].id == "combat:play:attack"
    assert (await CombatStrategy(None, None, None).decide(state, None)).action.id == "combat:play:attack"

    # A different power description must not be promoted to a verified stun.
    unknown = enemy.model_copy(update={"powers": (Power(id="plow_power", amount=150),)})
    uncertain = state.model_copy(update={"combat": state.combat.model_copy(update={"enemies": (unknown,)})})
    assert not any(r.get("triggers_visible_stun") for r in assess(uncertain)["evaluated_actions"])


def test_ringing_limits_both_attack_and_survival_search():
    """The visible one-card restriction cannot produce a three-card damage plan."""
    cards = tuple(
        Card(
            id="strike_ironclad",
            ref=f"card:{index}",
            type="attack",
            cost=1,
            values=PublicFacts.of({"Damage": damage}),
        )
        for index, damage in enumerate((12, 10, 7))
    )
    enemy = Enemy(id="boss", ref="enemy:boss", hp=132, intents=(Intent(type="Attack", damage=15),))
    actions = (
        Action(id="end", decision_id="d", kind=ActionKind.END_TURN),
        *(
            Action(
                id=f"play:{i}",
                decision_id="d",
                kind=ActionKind.PLAY_CARD,
                card_id=card.ref,
                target_id=enemy.ref,
            )
            for i, card in enumerate(cards)
        ),
    )
    state = GameState(
        scene=Scene.COMBAT,
        run=RunState(id="boss", hp=4, max_hp=80),
        combat=CombatState(
            energy=3, hand=cards, enemies=(enemy,), powers=(Power(id="ringing_power", amount=1),)
        ),
        legal_actions=actions,
        revision=1,
        decision_id="d",
        game_version="v0.111.0",
    )
    facts = assess(state)
    assert facts["remaining_card_plays"] == 1
    assert facts["visible_max_damage"] == 12
    assert len(facts["visible_max_damage_plan"]) == 1

    block_rows = [
        {"action_id": f"block:{i}", "resource_key": f"card:block:{i}", "cost": 1, "block_gain": 7}
        for i in range(2)
    ]
    assert visible_survival_plan(state, block_rows, 15) == []


async def test_persistent_boss_potions_are_used_while_they_can_pay_back():
    enemy = Enemy(
        id="ceremonial_beast",
        ref="enemy:boss",
        hp=220,
        max_hp=252,
        intents=(Intent(type="Attack", damage=18),),
    )
    block = Card(
        id="shrug_it_off",
        ref="card:block",
        cost=1,
        type="skill",
        values=PublicFacts.of({"Block": 8, "Cards": 1}),
    )
    clarity = Action(id="potion:clarity", decision_id="d", kind=ActionKind.USE_POTION, item_id="clarity")
    dexterity = Action(
        id="potion:dex", decision_id="d", kind=ActionKind.USE_POTION, item_id="dexterity_potion"
    )
    state = GameState(
        scene=Scene.COMBAT,
        run=RunState(id="boss", hp=53, max_hp=80, floor=17, boss="仪式兽"),
        combat=CombatState(turn=2, energy=3, draw=Pile(count=12), hand=(block,), enemies=(enemy,)),
        legal_actions=(
            Action(id="end", decision_id="d", kind=ActionKind.END_TURN),
            Action(id="play:block", decision_id="d", kind=ActionKind.PLAY_CARD, card_id=block.ref),
            clarity,
            dexterity,
        ),
        revision=1,
        decision_id="d",
        game_version="v0.111.0",
    )
    assert early_boss_potion_action(state, assess(state)) == (clarity, "use_early_boss_draw_potion")
    assert (await CombatStrategy(None, None, None).decide(state, None)).action == clarity
    no_clarity = state.model_copy(
        update={"legal_actions": tuple(a for a in state.legal_actions if a != clarity)}
    )
    assert early_boss_potion_action(no_clarity, assess(no_clarity)) == (
        dexterity,
        "use_early_boss_dexterity_potion",
    )
    no_block = no_clarity.model_copy(update={"legal_actions": (state.legal_actions[0], dexterity)})
    assert early_boss_potion_action(no_block, assess(no_block)) is None


def self_harm_setup_state(*, hp=4):
    enemy = Enemy(
        id="enemy",
        ref="enemy:0",
        hp=40,
        max_hp=40,
        intents=(Intent(type="Attack", damage=5, hits=1),),
    )
    bloodletting = Card(
        id="bloodletting",
        ref="card:bloodletting",
        name="Bloodletting",
        type="skill",
        cost=0,
        values=PublicFacts.of({"HpLoss": 3, "Energy": 2}),
    )
    heal = Card(
        id="not_yet",
        ref="card:heal",
        name="Not Yet",
        type="skill",
        cost=2,
        playable=False,
        unplayable_reason="not_enough_energy",
        values=PublicFacts.of({"Heal": 10}),
    )
    return GameState(
        scene=Scene.COMBAT,
        run=RunState(id="run", hp=hp, max_hp=80),
        combat=CombatState(energy=0, hand=(bloodletting, heal), enemies=(enemy,)),
        legal_actions=(
            Action(id="end", decision_id="d", kind=ActionKind.END_TURN),
            Action(
                id="play:bloodletting",
                decision_id="d",
                kind=ActionKind.PLAY_CARD,
                card_id=bloodletting.ref,
            ),
        ),
        revision=1,
        decision_id="d",
        game_version="v0.111.0",
    )


def test_bloodletting_can_enable_a_net_healing_survival_plan():
    state = self_harm_setup_state(hp=4)
    facts = assess(state)

    assert facts["visible_survival_plan"] == ["play:bloodletting", "future:card:heal"]
    option = facts["visible_self_harm_options"][0]
    assert option["action_id"] == "play:bloodletting"
    assert option["hp_loss"] == 3
    assert option["hp_after_cost"] == 1
    assert not option["self_lethal"]
    assert option["energy_gain"] == 2
    assert option["best_enabled_heal"] == 10
    assert option["net_hp_delta_vs_end_now_with_best_followup"] == 7
    assert forced_survival_action(state, facts)[0].id == "play:bloodletting"


def test_energy_gain_does_not_unlock_cards_unplayable_for_other_reasons():
    state = self_harm_setup_state(hp=4)
    blocked = state.combat.hand[1].model_copy(update={"unplayable_reason": "unplayable"})
    state = state.model_copy(
        update={"combat": state.combat.model_copy(update={"hand": (state.combat.hand[0], blocked)})}
    )
    facts = assess(state)
    assert facts["visible_survival_plan"] == []
    assert facts["visible_self_harm_options"][0]["best_enabled_heal"] == 0


def test_self_harm_followup_cannot_heal_after_its_own_lethal_hp_cost():
    state = self_harm_setup_state(hp=4)
    heal = state.combat.hand[1].model_copy(update={"values": PublicFacts.of({"HpLoss": 2, "Heal": 10})})
    state = state.model_copy(
        update={"combat": state.combat.model_copy(update={"hand": (state.combat.hand[0], heal)})}
    )
    option = assess(state)["visible_self_harm_options"][0]
    assert option["best_enabled_followup"] is None
    assert option["best_enabled_heal"] == 0
    assert option["hp_after_shown_intents_with_best_followup"] == -4


def test_self_lethal_energy_card_never_starts_a_survival_plan():
    state = self_harm_setup_state(hp=3)
    facts = assess(state)

    assert facts["visible_self_harm_options"][0]["self_lethal"]
    assert facts["visible_survival_plan"] == []
    assert not facts["verified_lethal_plan"]


def test_self_lethal_attack_is_not_a_verified_surviving_kill():
    enemy = Enemy(
        id="enemy",
        ref="enemy:0",
        hp=5,
        max_hp=5,
        intents=(Intent(type="Attack", damage=20, hits=1),),
    )
    attack = Card(
        id="breakthrough",
        ref="card:breakthrough",
        type="attack",
        cost=1,
        values=PublicFacts.of({"Damage": 10, "HpLoss": 1}),
    )
    state = GameState(
        scene=Scene.COMBAT,
        run=RunState(id="run", hp=1, max_hp=80),
        combat=CombatState(energy=1, hand=(attack,), enemies=(enemy,)),
        legal_actions=(
            Action(id="end", decision_id="d", kind=ActionKind.END_TURN),
            Action(
                id="play:attack",
                decision_id="d",
                kind=ActionKind.PLAY_CARD,
                card_id=attack.ref,
                target_id=enemy.ref,
            ),
        ),
        revision=1,
        decision_id="d",
        game_version="v0.111.0",
    )

    facts = assess(state)
    row = next(row for row in facts["evaluated_actions"] if row["action_id"] == "play:attack")
    assert row["self_lethal"]
    assert not row["verified_lethal"]
    assert row["hp_after_intents_if_played"] is None
    assert facts["verified_lethal_plan"] == []
    assert forced_survival_action(state, facts) is None


def test_self_lethal_card_cannot_claim_survival_from_later_healing():
    card = Card(
        id="breakthrough",
        ref="card:breakthrough",
        type="attack",
        cost=1,
        values=PublicFacts.of({"Damage": 10, "HpLoss": 1, "Heal": 10}),
    )
    state = status_state(card, hp=1, damage=10)
    enemy = state.combat.enemies[0].model_copy(update={"hp": 5})
    state = state.model_copy(update={"combat": state.combat.model_copy(update={"enemies": (enemy,)})})
    facts = assess(state)
    row = facts["evaluated_actions"][0]
    assert row["self_lethal"]
    assert row["verified_lethal"] is False
    assert row["hp_after_intents_if_played"] is None
    assert facts["visible_one_step_survival_actions"] == []
    assert facts["verified_lethal_plan"] == []
    assert forced_survival_action(state, facts) is None


def test_cruelty_setup_is_compared_inside_the_full_turn_damage_plan():
    enemy = Enemy(
        id="enemy",
        ref="enemy:0",
        hp=40,
        max_hp=40,
        powers=(Power(id="vulnerable_power", amount=2),),
    )
    cruelty = Card(
        id="cruelty",
        ref="card:cruelty",
        name="Cruelty+",
        type="power",
        cost=1,
        values=PublicFacts.of({"CrueltyPower": 50}),
    )
    strike = Card(
        id="strike_ironclad",
        ref="card:strike",
        name="Strike",
        type="attack",
        cost=1,
        values=PublicFacts.of({"Damage": 10}),
    )
    state = GameState(
        scene=Scene.COMBAT,
        run=RunState(id="run", hp=30, max_hp=80),
        combat=CombatState(energy=2, hand=(cruelty, strike), enemies=(enemy,)),
        legal_actions=(
            Action(id="end", decision_id="d", kind=ActionKind.END_TURN),
            Action(
                id="play:cruelty",
                decision_id="d",
                kind=ActionKind.PLAY_CARD,
                card_id=cruelty.ref,
            ),
            Action(
                id="play:strike",
                decision_id="d",
                kind=ActionKind.PLAY_CARD,
                card_id=strike.ref,
                target_id=enemy.ref,
            ),
        ),
        revision=1,
        decision_id="d",
        game_version="v0.111.0",
    )

    facts = assess(state)
    assert facts["visible_max_damage"] == 20
    assert facts["visible_max_damage_plan"] == ["play:cruelty", "play:strike"]
    assert facts["visible_setup_options"] == [
        {
            "action_id": "play:cruelty",
            "card_id": "cruelty",
            "card_type": "power",
            "cost": 1,
            "draw_per_vulnerable": 0,
            "draw_blocked_now": False,
            "vulnerable_sources_remaining": 0,
            "immediate_vulnerable_sources": 0,
            "vulnerable_enemies_now": 1,
            "playable_attacks_now": 1,
            "extra_vulnerable_damage_fraction": 0.5,
            "rage_block_per_attack": 0,
        }
    ]


def test_spite_repeat_uses_persisted_same_turn_hp_loss():
    enemy = Enemy(id="enemy", ref="enemy:0", hp=9, max_hp=9)
    spite = Card(
        id="spite",
        ref="card:spite",
        name="Spite",
        type="attack",
        cost=0,
        values=PublicFacts.of({"Damage": 5, "Repeat": 2}),
    )
    state = GameState(
        scene=Scene.COMBAT,
        run=RunState(id="run", hp=30, max_hp=80),
        combat=CombatState(energy=0, hand=(spite,), enemies=(enemy,)),
        legal_actions=(
            Action(id="end", decision_id="d", kind=ActionKind.END_TURN),
            Action(
                id="play:spite",
                decision_id="d",
                kind=ActionKind.PLAY_CARD,
                card_id=spite.ref,
                target_id=enemy.ref,
            ),
        ),
        revision=1,
        decision_id="d",
        game_version="v0.111.0",
    )

    before = assess(state)
    after = assess(state, lost_hp_this_turn=True)

    assert before["visible_max_damage"] == 5
    assert not before["verified_lethal_plan"]
    assert after["lost_hp_this_turn"]
    assert after["visible_max_damage"] == 10
    assert after["verified_lethal_plan"] == ["play:spite"]


def status_state(card, *, hp=11, damage=15, hits=1, powers=(), enemy_powers=()):
    enemy = Enemy(
        id="enemy",
        ref="enemy:0",
        hp=40,
        max_hp=40,
        intents=(Intent(type="Attack", damage=damage, hits=hits),),
        powers=enemy_powers,
    )
    return GameState(
        scene=Scene.COMBAT,
        run=RunState(id="run", hp=hp, max_hp=80),
        combat=CombatState(energy=1, hand=(card,), enemies=(enemy,), powers=powers),
        legal_actions=(
            Action(id="end", decision_id="d", kind=ActionKind.END_TURN),
            Action(id="play:card", decision_id="d", kind=ActionKind.PLAY_CARD, card_id=card.ref),
        ),
        revision=1,
        decision_id="d",
        game_version="v0.111.0",
    )


def test_tainted_block_recalculates_incoming_before_claiming_survival():
    card = Card(
        id="defend_ironclad",
        ref="card:defend",
        type="skill",
        cost=1,
        text="Gain 5 Block. Gain 2 Tainted.",
        values=PublicFacts.of({"Block": 5}),
        affliction_id="tainted",
        affliction_amount=2,
    )
    state = status_state(card, enemy_powers=(Power(id="vital_spark_power", amount=2),))
    facts = assess(state)
    row = facts["evaluated_actions"][0]

    assert facts["incoming_attack_damage"] == 15
    assert row["incoming_damage_after_status"] == 17
    assert row["tainted_gain"] == 2
    assert row["hp_after_intents"] == -1
    assert facts["visible_survival_plan"] == []
    assert facts["visible_one_step_survival_actions"] == []
    assert facts["survival_status"] == "dead"
    assert forced_survival_action(state, facts) is None


def test_tainted_gain_is_added_per_hit_and_not_double_counted():
    production = Card(
        id="production",
        ref="card:production",
        type="skill",
        cost=0,
        text="Gain 2 Energy. Gain 2 Tainted.",
        values=PublicFacts.of({"Energy": 2}),
        affliction_id="tainted",
        affliction_amount=2,
    )
    multi = assess(status_state(production, hp=25, damage=5, hits=3))
    assert multi["incoming_attack_damage"] == 15
    assert multi["evaluated_actions"][0]["incoming_damage_after_status"] == 21
    assert multi["evaluated_actions"][0]["hp_after_intents"] == 4

    already_tainted = assess(
        status_state(
            production,
            hp=25,
            damage=17,
            powers=(Power(id="tainted_power", amount=2),),
        )
    )
    assert already_tainted["incoming_attack_damage"] == 17
    assert already_tainted["evaluated_actions"][0]["incoming_damage_after_status"] == 19

    clean_production = production.model_copy(
        update={"text": "Gain 2 Energy. Exhaust.", "affliction_id": "", "affliction_amount": None}
    )
    clean_row = assess(status_state(clean_production, hp=25))["evaluated_actions"][0]
    assert clean_row["status_effect_known"]
    assert clean_row["tainted_gain"] == 0
    assert clean_row["incoming_damage_after_status"] == 15


def test_tainted_projection_abstains_when_attack_hit_count_is_missing():
    card = Card(
        id="defend_ironclad",
        ref="card:defend",
        type="skill",
        cost=1,
        text="Gain 5 Block. Gain 2 Tainted.",
        values=PublicFacts.of({"Block": 5}),
        affliction_id="tainted",
        affliction_amount=2,
    )
    facts = assess(status_state(card, hp=11, damage=15, hits=None))
    row = facts["evaluated_actions"][0]
    assert facts["intent_hits_incomplete"]
    assert facts["incoming_attack_hits"] is None
    assert not row["status_effect_known"]
    assert row["incoming_damage_after_status"] is None
    assert facts["survival_status"] == "unknown"


def test_tainted_projection_abstains_from_unverified_damage_multiplier_order():
    card = Card(
        id="defend_ironclad",
        ref="card:defend",
        type="skill",
        cost=1,
        text="Gain 5 Block. Gain 2 Tainted.",
        values=PublicFacts.of({"Block": 5}),
        affliction_id="tainted",
        affliction_amount=2,
    )
    vulnerable = assess(status_state(card, powers=(Power(id="vulnerable_power", amount=1),)))
    weak_enemy = assess(status_state(card, enemy_powers=(Power(id="weak_power", amount=1),)))
    for facts in (vulnerable, weak_enemy):
        assert facts["evaluated_actions"][0]["status_effect_known"] is False
        assert facts["evaluated_actions"][0]["incoming_damage_after_status"] is None


def test_frail_fractional_preview_uses_displayed_integer_block():
    card = Card(
        id="defend_ironclad",
        ref="card:defend",
        type="skill",
        cost=1,
        text="Gain 3 Block.",
        values=PublicFacts.of({"Block": 3.75}),
    )
    facts = assess(status_state(card, hp=10, damage=13, powers=(Power(id="frail_power", amount=1),)))
    assert facts["evaluated_actions"][0]["block_gain"] == 3
    assert facts["evaluated_actions"][0]["hp_after_intents"] == 0
    assert facts["visible_survival_plan"] == []


def test_target_specific_block_preview_is_used_for_the_bound_action():
    card = Card(
        id="iron_wave",
        ref="card:iron_wave",
        type="attack",
        cost=1,
        values=PublicFacts.of({"Damage": 6, "Block": 5}),
        target_values=PublicFacts.of({"0": {"Block": 8}}),
    )
    facts = assess(status_state(card, hp=5, damage=12))
    row = facts["evaluated_actions"][0]
    assert row["block_gain"] == 8
    assert row["hp_after_intents_if_played"] == 1
    assert facts["visible_survival_plan"] == ["play:card"]


def test_gigantification_only_boosts_the_next_attack_in_full_turn_search():
    cards = tuple(
        Card(
            id="strike_ironclad",
            ref=f"card:strike:{index}",
            type="attack",
            cost=1,
            text="Deal 18 damage.",
            values=PublicFacts.of({"Damage": 18}),
        )
        for index in range(2)
    )
    enemy = Enemy(id="enemy", ref="enemy:0", hp=30, max_hp=30)
    state = GameState(
        scene=Scene.COMBAT,
        run=RunState(id="run", hp=30, max_hp=80),
        combat=CombatState(
            energy=2,
            hand=cards,
            enemies=(enemy,),
            powers=(Power(id="gigantification_power", amount=1),),
        ),
        legal_actions=(
            Action(id="end", decision_id="d", kind=ActionKind.END_TURN),
            *(
                Action(
                    id=f"play:{index}",
                    decision_id="d",
                    kind=ActionKind.PLAY_CARD,
                    card_id=card.ref,
                    target_id=enemy.ref,
                )
                for index, card in enumerate(cards)
            ),
        ),
        revision=1,
        decision_id="d",
        game_version="v0.111.0",
    )
    facts = assess(state)
    assert facts["visible_max_damage"] == 24
    assert facts["verified_lethal_plan"] == []
    assert facts["evaluated_actions"][0]["hp_damage"] == 18


def test_unmodeled_affliction_and_target_preview_abstain_from_exact_claims():
    block = Card(
        id="defend_ironclad",
        ref="card:defend",
        type="skill",
        cost=1,
        values=PublicFacts.of({"Block": 5}),
        affliction_id="unknown_affliction",
        affliction_amount=2,
    )
    unknown = assess(status_state(block, hp=11))
    assert unknown["evaluated_actions"][0]["status_effect_known"] is False
    assert unknown["visible_survival_plan"] == []
    assert unknown["visible_one_step_survival_actions"] == []
    assert unknown["survival_status"] == "unknown"

    attack = Card(
        id="strike_ironclad",
        ref="card:strike",
        type="attack",
        cost=1,
        values=PublicFacts.of({"Damage": 6}),
        target_values=PublicFacts.of({"0": {"Damage": 12}}),
    )
    state = status_state(attack, hp=11, enemy_powers=(Power(id="vulnerable_power", amount=2),))
    state = state.model_copy(
        update={
            "combat": state.combat.model_copy(
                update={"enemies": (state.combat.enemies[0].model_copy(update={"hp": 10}),)}
            ),
            "legal_actions": (
                state.legal_actions[0],
                state.legal_actions[1].model_copy(update={"target_id": "enemy:0"}),
            ),
        }
    )
    uncertain = assess(state)
    assert "hp_damage" not in uncertain["evaluated_actions"][0]
    assert uncertain["visible_damage_plan_known"] is False
    assert uncertain["verified_lethal_plan"] == []


@pytest.mark.parametrize(
    ("card_id", "values"),
    [
        ("flame_barrier", {"Block": 5, "DamageBack": 4}),
        ("armaments", {"Block": 5}),
        ("true_grit", {"Block": 5}),
        ("one_two_punch", {"Attacks": 1}),
    ],
)
def test_unmodeled_hand_effects_do_not_claim_exact_survival(card_id, values):
    card = Card(
        id=card_id,
        ref=f"card:{card_id}",
        type="skill",
        cost=1,
        values=PublicFacts.of(values),
    )
    facts = assess(status_state(card))
    row = facts["evaluated_actions"][0]
    assert not row["status_effect_known"]
    assert row["incoming_damage_after_status"] is None
    assert "hp_after_intents" not in row
    assert facts["visible_survival_plan"] == []
    assert facts["survival_status"] == "unknown"
    assert not facts["visible_damage_plan_known"]


def test_missing_affliction_or_unknown_player_power_prevents_exact_block_claim():
    card = Card(
        id="defend_ironclad",
        ref="card:defend",
        type="skill",
        cost=1,
        values=PublicFacts.of({"Block": 5}),
    )
    vital_spark = assess(status_state(card, enemy_powers=(Power(id="vital_spark_power", amount=2),)))
    assert vital_spark["evaluated_actions"][0]["status_effect_known"] is False
    assert vital_spark["survival_status"] == "unknown"
    player_unknown = assess(status_state(card, powers=(Power(id="double_attack_power", amount=1),)))
    assert player_unknown["evaluated_actions"][0]["status_effect_known"] is False
    assert player_unknown["survival_status"] == "unknown"
    negative_unknown = assess(status_state(card, powers=(Power(id="unknown_debuff", amount=-1),)))
    assert negative_unknown["evaluated_actions"][0]["status_effect_known"] is False


def test_no_draw_state_and_triggered_power_draw_are_not_immediate_draws():
    shrug = Card(
        id="shrug_it_off",
        ref="card:shrug",
        type="skill",
        cost=1,
        values=PublicFacts.of({"Block": 5, "Cards": 1}),
    )
    facts = assess(status_state(shrug, powers=(Power(id="no_draw_power", amount=1),)))
    assert facts["draw_blocked_now"]
    assert facts["evaluated_actions"][0]["draw"] == 0
    assert facts["visible_survival_plan"] == ["play:card"]

    vicious = Card(
        id="vicious",
        ref="card:vicious",
        type="power",
        cost=1,
        values=PublicFacts.of({"Cards": 1}),
    )
    setup = assess(status_state(vicious))
    assert setup["evaluated_actions"][0]["draw"] == 0
    assert setup["visible_setup_options"][0]["draw_per_vulnerable"] == 1


def test_two_nonlethal_attacks_are_recognized_as_a_surviving_lethal_combo():
    cards = tuple(
        Card(
            id="strike_ironclad",
            ref=f"card:{index}",
            type="attack",
            cost=1,
            values=PublicFacts.of({"Damage": 6}),
        )
        for index in range(2)
    )
    enemy = Enemy(
        id="enemy",
        ref="enemy:0",
        hp=12,
        max_hp=12,
        intents=(Intent(type="Attack", damage=10),),
    )
    state = GameState(
        scene=Scene.COMBAT,
        run=RunState(id="run", hp=4, max_hp=80),
        combat=CombatState(energy=2, hand=cards, enemies=(enemy,)),
        legal_actions=(
            Action(id="end", decision_id="d", kind=ActionKind.END_TURN),
            *(
                Action(
                    id=f"play:{index}",
                    decision_id="d",
                    kind=ActionKind.PLAY_CARD,
                    card_id=card.ref,
                    target_id=enemy.ref,
                )
                for index, card in enumerate(cards)
            ),
        ),
        revision=1,
        decision_id="d",
        game_version="v0.111.0",
    )
    facts = assess(state)
    assert len(facts["verified_lethal_plan"]) == 2
    assert facts["survival_status"] == "survives"
    assert not facts["no_visible_survival"]
    assert forced_survival_action(state, facts)[0].id == facts["verified_lethal_plan"][0]


def test_survival_search_keeps_feasible_order_of_energy_generators():
    card = Card(id="defend_ironclad", ref="card:block", type="skill", cost=0)
    state = status_state(card, hp=4, damage=10).model_copy(
        update={"combat": status_state(card, hp=4, damage=10).combat.model_copy(update={"energy": 1})}
    )
    rows = [
        {"action_id": "a", "resource_key": "card:a", "cost": 2, "energy_gain": 2, "block_gain": 3},
        {"action_id": "b", "resource_key": "card:b", "cost": 0, "energy_gain": 1, "block_gain": 4},
    ]
    assert visible_survival_plan(state, rows, 10) == ["b", "a"]


def test_survival_search_applies_hp_loss_and_healing_in_play_order():
    card = Card(id="defend_ironclad", ref="card:block", type="skill", cost=0)
    state = status_state(card, hp=8, damage=10)
    state = state.model_copy(update={"run": state.run.model_copy(update={"max_hp": 10})})
    rows = [
        {"action_id": "a:heal", "resource_key": "card:heal", "cost": 0, "heal": 6},
        {"action_id": "b:cost", "resource_key": "card:cost", "cost": 0, "hp_loss": 5, "block_gain": 5},
    ]
    # Healing first wastes 4 HP at the cap, leaving exactly 0 HP after attack.
    # Spending HP first and then healing is a valid surviving sequence.
    assert visible_survival_plan(state, rows, 10) == ["b:cost", "a:heal"]


def test_survival_search_can_heal_before_a_later_hp_cost():
    card = Card(id="defend_ironclad", ref="card:block", type="skill", cost=0)
    state = status_state(card, hp=4, damage=12)
    state = state.model_copy(update={"run": state.run.model_copy(update={"max_hp": 10})})
    rows = [
        {"action_id": "heal", "resource_key": "card:heal", "cost": 0, "heal": 6},
        {"action_id": "cost", "resource_key": "card:cost", "cost": 0, "hp_loss": 5, "block_gain": 8},
    ]
    assert visible_survival_plan(state, rows, 12) == ["heal", "cost"]
