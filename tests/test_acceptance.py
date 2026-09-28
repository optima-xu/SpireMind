import copy
import json
from argparse import Namespace

import httpx
import pytest
from pydantic import ValidationError

from spiremind.cli import bridge_key, bridge_lock_path, canonical_bridge_url, execute, safe_extra_body
from spiremind.config import Config, GameConfig
from spiremind.core.enums import Scene
from spiremind.environment.base import EnvironmentError
from spiremind.environment.mcp import MCPEnvironment
from spiremind.environment.normalize import normalize
from spiremind.runtime.locking import SingleWriter
from spiremind.runtime.router import SceneRouter


async def test_card_export_exact_version_and_provenance(tmp_path):
    payload = {
        "metadata": {"game_version": "v0.111.0", "mod_version": "0.1.12"},
        "collections": {
            "cards": {
                "CARD.STRIKE": {
                    "description": "Deal {Damage:diff()} damage.",
                    "cost": 1,
                    "type": "Attack",
                    "vars": {"Damage": 6},
                }
            }
        },
    }

    def handler(req):
        assert req.url.path == "/v2/data/export"
        return httpx.Response(200, json={"ok": True, "data": payload})

    env = MCPEnvironment(
        GameConfig(),
        tmp_path / "pending.json",
        httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler)),
    )
    env.game_version = "v0.111.0"
    (fact,) = await env.card_facts()
    assert fact.card_id == "strike" and "loaded_game_model" in fact.source_version
    assert fact.cost == 1 and fact.type == "attack"
    assert fact.context_view()["values"] == {"Damage": 6}
    env.game_version = "v0.112.0"
    with pytest.raises(EnvironmentError, match="version"):
        await env.card_facts()
    await env.close()


def test_selection_routing_and_shop_cost(raw_decision):
    raw = copy.deepcopy(raw_decision)
    raw["phase"] = "combat_selection"
    raw["summary"]["energy"] = 1
    raw["context"].pop("combat")
    raw["context"]["selection"] = {
        "kind": "combat_pile_card_select",
        "prompt": "Discard one",
        "min_select": 1,
        "max_select": 1,
        "requires_confirmation": True,
    }
    state = normalize(raw, 1, "v0.111.0")
    assert state.scene == Scene.CARD_SELECTION
    assert SceneRouter("combat", "run", "map", "event").route(state) == "combat"
    raw["summary"]["energy"] = None
    raw["context"]["selection"]["kind"] = "deck_upgrade_select"
    assert SceneRouter("combat", "run", "map", "event").route(normalize(raw, 2, "v0.111.0")) == "run"
    raw["phase"] = "shop"
    raw["context"]["shop"] = {"card_removal": {"price": 75, "available": True, "used": False}}
    assert normalize(raw, 3, "v0.111.0").scene_facts.unpack()["card_removal"]["price"] == 75


async def test_pending_receipt_waits_for_fresh_snapshot(raw_decision, tmp_path):
    next_state = copy.deepcopy(raw_decision)
    next_state["decision_id"] = "next"
    requests = []

    def handler(req):
        requests.append(req.url.path)
        if req.url.path.endswith("/act"):
            return httpx.Response(200, json={"data": {"status": "pending"}})
        if req.url.path.endswith("/wait"):
            assert json.loads(req.content)["after_decision_id"] == raw_decision["decision_id"]
            return httpx.Response(200, json={"available": True, "decision": next_state})
        if requests.count("/v2/decision/act"):
            return httpx.Response(200, json={"available": False})
        return httpx.Response(200, json={"available": True, "decision": raw_decision})

    env = MCPEnvironment(
        GameConfig(),
        tmp_path / "pending.json",
        httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler)),
    )
    before = await env.observe()
    assert (await env.execute(before.legal_actions[0])).status == "pending"
    assert (await env.observe()).decision_id == "next"
    assert requests.count("/v2/decision/act") == 1
    await env.close()


@pytest.mark.parametrize("command", ["sync-card-db", "import-card-db"])
async def test_knowledge_updates_cannot_change_a_running_agents_database(command, tmp_path, monkeypatch):
    config = Config()
    config.runtime.runs_dir = tmp_path
    monkeypatch.setattr(Config, "load", lambda _: config)

    class Bridge:
        def __init__(self, *args):
            pass

        async def health(self):
            return {}

        async def close(self):
            pass

        async def card_facts(self):
            pytest.fail("CardDB must not change during an active run")

    monkeypatch.setattr("spiremind.cli.MCPEnvironment", Bridge)
    with SingleWriter(bridge_lock_path(config.game.base_url)):
        with pytest.raises(RuntimeError, match="Another SpireMind"):
            await execute(Namespace(config=None, command=command, path=tmp_path / "unused.json"))


def test_equivalent_bridge_urls_share_one_lock_identity():
    assert canonical_bridge_url("HTTP://LOCALHOST:80/") == "http://localhost"
    assert bridge_key("http://127.0.0.1:8080") == bridge_key("http://127.0.0.1:8080/")


def test_manifest_extra_body_redaction_is_recursive():
    assert safe_extra_body({"enable_thinking": False, "nested": {"api_key": "secret", "mode": "safe"}}) == {
        "enable_thinking": False,
        "nested": {"mode": "safe"},
    }


@pytest.mark.parametrize("field,value", [("max_steps", -1), ("max_steps", 0), ("ascension", 999)])
async def test_cli_overrides_are_revalidated(field, value, tmp_path, monkeypatch):
    config = Config()
    config.runtime.runs_dir = tmp_path
    monkeypatch.setattr(Config, "load", lambda _: config)
    args = Namespace(
        config=None,
        command="run",
        environment="mock",
        policy="rules",
        max_steps=1,
        character=None,
        ascension=0,
    )
    setattr(args, field, value)

    with pytest.raises(ValidationError):
        await execute(args)
