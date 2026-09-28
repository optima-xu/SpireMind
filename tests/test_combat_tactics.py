import copy
import json
from pathlib import Path

import httpx
import pytest

from spiremind.config import GameConfig
from spiremind.core.actions import Action
from spiremind.core.enums import ActionKind
from spiremind.core.state import Card, Enemy, GameState, Intent, Power, PublicFacts
from spiremind.environment.mcp import MCPEnvironment
from spiremind.strategies.combat import CombatStrategy
from spiremind.strategies.combat_tactics import (
    MAX_SURVIVAL_SEARCH_TRANSITIONS,
    assess,
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
