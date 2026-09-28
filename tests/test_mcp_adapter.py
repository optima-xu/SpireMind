import asyncio
import copy
import json
import time

import httpx
import pytest

from spiremind.config import GameConfig
from spiremind.environment.base import EnvironmentError, StaleDecision, TransitionPending
from spiremind.environment.mcp import PROTOCOL, MCPEnvironment
from spiremind.environment.normalize import normalize
from spiremind.strategies.combat import CombatStrategy


def test_public_normalization(raw_decision):
    raw_decision["context"]["run"].update(
        max_energy=4,
        second_boss_encounter={"name": "Second Guardian"},
        relics=[
            {
                "relic_id": "INK_BOTTLE",
                "name": "Ink Bottle",
                "stack": 1,
                "trigger_progress": {"progress_known": True, "primary": 7},
            }
        ],
    )
    s = normalize(raw_decision, 1, "v0.111.0")
    assert s.combat.enemies[0].intents[0].hits == 2
    assert s.legal_actions[0].card_id == "c0"
    assert s.combat.hand[0].values.unpack() == {"Damage": 6}
    assert "EXCLUDED" not in s.model_dump_json()
    assert "secret_card" not in s.model_dump_json()
    assert s.run.boss == "Guardian"
    assert s.run.second_boss == "Second Guardian"
    assert s.run.max_energy == 4
    assert s.run.act == 1
    assert s.run.relics[0].trigger_progress.unpack()["primary"] == 7
    with pytest.raises(ValueError):
        s.run.hp = 2


def test_card_reward_claim_is_normalized_as_inspection(raw_decision):
    decision = copy.deepcopy(raw_decision)
    decision["phase"] = "reward"
    decision["context"].pop("combat")
    decision["context"]["reward"] = {
        "pending_card_choice": False,
        "can_proceed": True,
        "rewards": [
            {
                "index": 0,
                "reward_type": "Card",
                "description": "将一张牌添加到你的牌组。",
                "claimable": True,
            }
        ],
        "card_options": [],
    }
    decision["choices"] = [
        {
            "action_id": "reward:claim:0",
            "kind": "claim_reward",
            "label": "Claim Card: 将一张牌添加到你的牌组。",
            "summary": "将一张牌添加到你的牌组。",
            "source": {"option_index": 0, "reward_type": "Card"},
            "risk_tags": [],
            "params_schema": {},
        },
        {
            "action_id": "reward:proceed",
            "kind": "proceed",
            "label": "Skip remaining rewards and proceed",
            "source": {"skips_remaining_rewards": True},
            "risk_tags": ["irreversible"],
            "params_schema": {},
        },
    ]

    state = normalize(decision, 2, "v0.111.0")

    assert [action.id for action in state.legal_actions] == ["reward:claim:0"]
    inspect = state.legal_actions[0]
    assert inspect.kind.value == "open_card_reward"
    assert inspect.label == "View card reward choices"
    assert "does not add a card" in inspect.description


def test_reward_filters_passive_potion_discard_but_keeps_required_slot_choice(raw_decision):
    decision = copy.deepcopy(raw_decision)
    decision["phase"] = "reward"
    decision["context"].pop("combat")
    decision["context"]["reward"] = {"rewards": []}
    decision["choices"] = [
        {
            "action_id": "reward:discard_potion:0",
            "kind": "discard_potion",
            "label": "Discard potion",
            "source": {"potion_id": "WEAK_POTION", "opens_reward_potion_slot": False},
            "risk_tags": ["irreversible"],
            "params_schema": {},
        },
        {
            "action_id": "reward:discard_potion:1",
            "kind": "discard_potion",
            "label": "Discard potion to make room",
            "source": {"potion_id": "FIRE_POTION", "opens_reward_potion_slot": True},
            "risk_tags": ["irreversible"],
            "params_schema": {},
        },
    ]

    state = normalize(decision, 2, "v0.111.0")

    assert [action.id for action in state.legal_actions] == ["reward:discard_potion:1"]
    assert state.legal_actions[0].kind.value == "discard_potion"


def test_reward_hides_optional_discard_when_potion_has_an_open_slot(raw_decision):
    decision = copy.deepcopy(raw_decision)
    decision["phase"] = "reward"
    decision["context"].pop("combat")
    decision["context"]["reward"] = {"rewards": []}
    decision["choices"] = [
        {
            "action_id": "reward:claim:0",
            "kind": "claim_reward",
            "label": "Claim Potion",
            "source": {
                "reward_type": "Potion",
                "potion_id": "FIRE_POTION",
                "potion_slot_available": True,
            },
            "risk_tags": [],
            "params_schema": {},
        },
        {
            "action_id": "reward:discard_potion:0",
            "kind": "discard_potion",
            "label": "Discard potion to make room",
            "source": {"potion_id": "WEAK_POTION", "opens_reward_potion_slot": True},
            "risk_tags": ["irreversible"],
            "params_schema": {},
        },
    ]

    state = normalize(decision, 2, "v0.111.0")

    assert [action.id for action in state.legal_actions] == ["reward:claim:0"]


def test_supported_protocol_actions_do_not_collapse_to_other(raw_decision):
    decision = copy.deepcopy(raw_decision)
    kinds = {
        "claim_reward",
        "confirm_selection",
        "select_card_bundle",
        "choose_treasure_relic",
        "open_chest",
        "open_shop_inventory",
        "close_shop_inventory",
        "open_timeline",
        "close_main_menu_submenu",
        "return_to_main_menu",
    }
    decision["choices"] = [
        {
            "action_id": f"test:{kind}",
            "kind": kind,
            "label": kind,
            "source": {},
            "risk_tags": [],
            "params_schema": {},
        }
        for kind in kinds
    ]

    state = normalize(decision, 2, "v0.111.0")

    assert len(state.legal_actions) == len(kinds)
    assert all(action.kind.value != "other" for action in state.legal_actions)


async def test_combat_exhaust_picker_has_explicit_semantics_and_safe_rule(raw_decision):
    decision = copy.deepcopy(raw_decision)
    decision["decision_id"] = "run:f31:combat_selection:t5"
    decision["phase"] = "combat_selection"
    decision["summary"].update(
        current_hp=2,
        max_hp=80,
        block=0,
        energy=3,
        incoming_damage=19,
        player_powers=[],
        enemy_powers=[],
    )
    decision["context"].pop("combat")
    decision["context"]["selection"] = {
        "kind": "combat_hand_select",
        "prompt": "选择1张牌来消耗。",
        "min_select": 1,
        "max_select": 1,
        "selected_count": 0,
        "requires_confirmation": False,
        "cards": [
            {
                "index": 0,
                "card_ref": "card:DAZED:1",
                "card_id": "DAZED",
                "name": "晕眩",
                "card_type": "Status",
                "energy_cost": -1,
                "resolved_rules_text": "不能被打出。 虚无。",
                "keywords": ["Ethereal", "Unplayable"],
            },
            {
                "index": 1,
                "card_ref": "card:SHRUG_IT_OFF:1",
                "card_id": "SHRUG_IT_OFF",
                "name": "耸肩无视",
                "card_type": "Skill",
                "energy_cost": 1,
                "resolved_rules_text": "获得10点格挡。 抽1张牌。",
                "keywords": ["格挡"],
                "dynamic_vars": {"Block": {"preview_value": 10}},
            },
        ],
    }
    decision["choices"] = [
        {
            "action_id": "combat_selection:select_deck_card:0",
            "kind": "select_deck_card",
            "label": "Select 晕眩",
            "summary": "不能被打出。 虚无。",
            "source": {"card_ref": "card:DAZED:1", "option_index": 0},
            "risk_tags": [],
            "params_schema": {},
        },
        {
            "action_id": "combat_selection:select_deck_card:1",
            "kind": "select_deck_card",
            "label": "Select 耸肩无视",
            "summary": "获得10点格挡。 抽1张牌。",
            "source": {"card_ref": "card:SHRUG_IT_OFF:1", "option_index": 1},
            "risk_tags": [],
            "params_schema": {},
        },
    ]

    state = normalize(decision, 63, "v0.111.0")
    facts = state.scene_facts.unpack()
    assert facts["operation"] == "exhaust"
    assert facts["combat_summary"]["incoming_damage"] == 19
    assert state.legal_actions[0].label == "Exhaust 晕眩"
    assert "without playing" in state.legal_actions[0].description

    choice = await CombatStrategy(None, None, None).decide(state, None)
    assert choice.action.id == "combat_selection:select_deck_card:0"
    assert choice.policy_rule == "exhaust_unplayable_card"


async def test_timeout_reconciles_without_resend(raw_decision, tmp_path):
    calls = []
    later = copy.deepcopy(raw_decision)
    later["decision_id"] = "run:f1:t1:2"

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/act"):
            raise httpx.ReadTimeout("timeout", request=request)
        if request.url.path.endswith("/wait"):
            return httpx.Response(200, json={"ok": True, "data": {"available": True, "decision": later}})
        if calls.count("/v2/decision/act"):
            return httpx.Response(200, json={"ok": True, "data": {"available": False}})
        return httpx.Response(200, json={"ok": True, "data": {"available": True, "decision": raw_decision}})

    env = MCPEnvironment(
        GameConfig(),
        tmp_path / "pending.json",
        httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler)),
    )
    state = await env.observe()
    receipt = await env.execute(state.legal_actions[0])
    assert receipt.status == "uncertain"
    assert env.journal.exists()
    with pytest.raises(TransitionPending):
        await env.execute(state.legal_actions[0])
    after = await env.observe()
    assert after.decision_id == later["decision_id"]
    assert not env.journal.exists()
    assert calls.count("/v2/decision/act") == 1
    assert await env.verify(state, state.legal_actions[0], after)
    await env.close()


async def test_rejection_is_not_retried(raw_decision, tmp_path):
    def handler(req):
        if req.url.path.endswith("act"):
            return httpx.Response(409, json={"ok": False, "error": {"code": "stale_decision"}})
        return httpx.Response(200, json={"available": True, "decision": raw_decision})

    env = MCPEnvironment(
        GameConfig(),
        tmp_path / "pending.json",
        httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler)),
    )
    state = await env.observe()
    with pytest.raises(StaleDecision):
        await env.execute(state.legal_actions[0])
    assert not env.journal.exists()
    await env.close()


async def test_restart_honors_pending_journal(raw_decision, tmp_path):
    path = tmp_path / "pending.json"
    path.write_text(json.dumps({"decision_id": "old", "action_id": "a0"}))

    def handler(req):
        if req.url.path == "/v2/decision/current":
            return httpx.Response(200, json={"available": False})
        assert req.url.path == "/v2/decision/wait"
        assert json.loads(req.content)["after_decision_id"] == "old"
        return httpx.Response(200, json={"available": True, "decision": raw_decision})

    env = MCPEnvironment(
        GameConfig(), path, httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler))
    )
    await env.observe()
    assert not path.exists()
    await env.close()


async def test_prepared_journal_recovers_when_old_decision_is_still_current(raw_decision, tmp_path):
    path = tmp_path / "pending.json"
    path.write_text(
        json.dumps(
            {
                "decision_id": raw_decision["decision_id"],
                "action_id": raw_decision["choices"][0]["action_id"],
                "phase": "prepared",
            }
        )
    )
    calls = []

    def handler(req):
        calls.append(req.url.path)
        return httpx.Response(200, json={"available": True, "decision": raw_decision})

    env = MCPEnvironment(
        GameConfig(),
        path,
        httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler)),
    )
    assert (await env.observe()).decision_id == raw_decision["decision_id"]
    assert calls == ["/v2/decision/current"]
    assert not path.exists()
    await env.close()


async def test_corrupt_pending_journal_is_quarantined(raw_decision, tmp_path):
    path = tmp_path / "pending.json"
    path.write_text("{not-json", encoding="utf-8")
    env = MCPEnvironment(
        GameConfig(),
        path,
        httpx.AsyncClient(
            base_url="http://test",
            transport=httpx.MockTransport(
                lambda req: httpx.Response(200, json={"available": True, "decision": raw_decision})
            ),
        ),
    )
    assert (await env.observe()).decision_id == raw_decision["decision_id"]
    assert not path.exists()
    assert path.with_name(path.name + ".corrupt").exists()
    await env.close()


async def test_act_next_decision_is_reused_without_observe_round_trip(raw_decision, tmp_path):
    next_state = copy.deepcopy(raw_decision)
    next_state["decision_id"] = "run:f1:t1:next"
    calls = []

    def handler(req):
        calls.append(req.url.path)
        if req.url.path.endswith("/act"):
            return httpx.Response(
                200,
                json={"data": {"status": "completed", "next_decision": next_state}},
            )
        return httpx.Response(200, json={"available": True, "decision": raw_decision})

    env = MCPEnvironment(
        GameConfig(),
        tmp_path / "pending.json",
        httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler)),
    )
    before = await env.observe()
    receipt = await env.execute(before.legal_actions[0])
    after = await env.observe()
    assert receipt.next_decision_id == after.decision_id == next_state["decision_id"]
    assert calls == ["/v2/decision/current", "/v2/decision/act"]
    assert not env.journal.exists()
    await env.close()


async def test_wait_respects_transition_timeout(raw_decision, tmp_path):
    async def handler(req):
        if req.url.path.endswith("/current"):
            return httpx.Response(200, json={"available": False})
        await asyncio.sleep(1)
        return httpx.Response(200, json={"available": False})

    env = MCPEnvironment(
        GameConfig(transition_timeout=0.05),
        tmp_path / "pending.json",
        httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler)),
    )
    started = time.monotonic()
    with pytest.raises(TransitionPending):
        await env.observe()
    assert time.monotonic() - started < 0.25
    await env.close()


@pytest.mark.parametrize(
    "changes",
    [
        {"protocol_version": "old"},
        {"state_version": 15},
        {"decision_version": 6},
        {"capabilities": {}},
        {"compatibility": {"status": "incompatible"}},
    ],
)
async def test_health_contract(changes, tmp_path):
    health = (
        dict(
            protocol_version=PROTOCOL,
            state_version=16,
            decision_version=7,
            capabilities={"decision_v2": True},
        )
        | changes
    )
    env = MCPEnvironment(
        GameConfig(),
        tmp_path / "pending.json",
        httpx.AsyncClient(
            base_url="http://test",
            transport=httpx.MockTransport(lambda req: httpx.Response(200, json=health)),
        ),
    )
    with pytest.raises(EnvironmentError):
        await env.health()
    await env.close()
