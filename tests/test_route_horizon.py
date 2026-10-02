from spiremind.context.route_horizon import last_known_shop_before_boss, route_options
from spiremind.core.actions import Action
from spiremind.core.enums import ActionKind, Scene
from spiremind.core.state import Choice, GameState, MapNode, MapState, RunState
from spiremind.memory.manager import MemoryContext, MemoryManager
from spiremind.memory.storage_sqlite import MemoryStore
from spiremind.strategies.fallback import conservative_choice
from spiremind.strategies.map import MapStrategy
from spiremind.strategies.run import RunStrategy


def _action(node_id: str, decision_id: str = "map-decision") -> Action:
    return Action(
        id=f"map:{node_id}",
        decision_id=decision_id,
        kind=ActionKind.CHOOSE_MAP_NODE,
        node_id=node_id,
    )


def _nodes() -> tuple[MapNode, ...]:
    return (
        MapNode(id="12,2", type="Unknown", children=("13,2", "13,3")),
        MapNode(id="13,2", type="Elite", children=("14,2",)),
        MapNode(id="13,3", type="Monster", children=("14,2", "14,3")),
        MapNode(id="14,2", type="Shop", children=("15,2",)),
        MapNode(id="14,3", type="Elite", children=("15,2",)),
        MapNode(id="15,2", type="RestSite", children=("16,3",)),
        MapNode(id="16,3", type="Boss"),
    )


def _map_state(*, hp: int = 37) -> GameState:
    return GameState(
        scene=Scene.MAP,
        run=RunState(id="route-run", act=1, floor=13, hp=hp, max_hp=80, gold=260),
        map=MapState(current_node="12,2", nodes=_nodes()),
        legal_actions=(_action("13,2"), _action("13,3")),
        revision=1,
        decision_id="map-decision",
        game_version="v0.111.0",
    )


def test_visible_route_summary_exposes_shared_future_access():
    horizon = route_options(_map_state())
    assert horizon["shared_reachable_shops"] == ["14,2"]
    assert horizon["shared_reachable_rests"] == ["15,2"]
    elite, monster = horizon["options"]
    assert elite["min_elites"] == 1
    assert monster["min_elites"] == 0
    assert elite["possible_shop_game_floors"] == [15]
    assert monster["boss_game_floors"] == [17]
    assert [x["node_id"] for x in elite["fewest_elites_path"]][1:] == [
        x["node_id"] for x in monster["fewest_elites_path"]
    ][1:]


async def test_low_hp_map_avoids_elite_when_downstream_route_is_identical():
    memory = MemoryContext("snapshot", {"elite_readiness": 0.306}, {}, ())
    decision = await MapStrategy(None, None, conservative_choice).decide(_map_state(), memory)
    assert decision.action.node_id == "13,3"
    assert decision.policy_rule == "low_hp_shared_route_avoid_elite"


async def test_last_shop_horizon_survives_scene_transition_and_opens_inventory(tmp_path):
    source = _map_state().model_copy(
        update={
            "run": RunState(id="route-run", act=1, floor=14, hp=9, max_hp=80, gold=304),
            "map": MapState(current_node="13,2", nodes=_nodes()),
            "legal_actions": (_action("14,2"),),
        }
    )
    shop = GameState(
        scene=Scene.SHOP,
        run=RunState(id="route-run", act=1, floor=15, hp=9, max_hp=80, gold=304),
        choices=(Choice(id="0", label="Attack Potion", price=50),),
        legal_actions=(
            Action(id="shop:open_inventory", decision_id="shop-decision", kind=ActionKind.OPEN_SHOP),
            Action(id="shop:proceed", decision_id="shop-decision", kind=ActionKind.PROCEED),
        ),
        revision=2,
        decision_id="shop-decision",
        game_version="v0.111.0",
    )
    store = MemoryStore(tmp_path / "route.sqlite")
    memory = MemoryManager(store)
    await memory.context_for(source, "map")
    await memory.update(source, source.legal_actions[0], shop, semantic_success=False)
    restored = MemoryManager(store)
    context = await restored.context_for(shop, "run")
    assert context.run["route_horizon"]["boss_game_floors"] == [17]
    assert last_known_shop_before_boss(shop, context.run["route_horizon"])
    assert "no later shop before the boss" in RunStrategy(None, None, conservative_choice).task_for(
        shop, context
    )
    decision = await RunStrategy(None, None, conservative_choice).decide(shop, context)
    assert decision.action.id == "shop:open_inventory"
    assert decision.policy_rule == "inspect_critical_last_shop"

    inventory = shop.model_copy(
        update={
            "legal_actions": (
                Action(id="shop:buy:0", decision_id="shop-decision", kind=ActionKind.BUY_ITEM),
                Action(id="shop:close_inventory", decision_id="shop-decision", kind=ActionKind.CLOSE_SHOP),
            )
        }
    )
    follow_up = await RunStrategy(None, None, conservative_choice).decide(inventory, context)
    assert follow_up.action.kind == ActionKind.CLOSE_SHOP
    assert follow_up.policy_rule is None

    next_act = shop.model_copy(update={"run": shop.run.model_copy(update={"act": 2, "floor": 1})})
    assert (await restored.context_for(next_act, "run")).run["route_horizon"] == {}
    store.close()
