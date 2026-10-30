"""Summaries of visible map paths, without estimating hidden encounters or outcomes."""

from dataclasses import dataclass

from spiremind.core.actions import Action
from spiremind.core.state import GameState, MapNode

NODE_TYPES = ("Elite", "Monster", "Shop", "RestSite", "Boss")


def _index(node_id: str) -> int | None:
    try:
        return int(node_id.split(",", 1)[0])
    except ValueError:
        return None


@dataclass(frozen=True)
class _PathFacts:
    path_count: int
    all_paths_to_boss: bool
    min_counts: dict[str, int]
    max_counts: dict[str, int]
    possible_floors: dict[str, frozenset[int]]
    reachable_ids: frozenset[str]
    fewest_elites_path: tuple[str, ...]


def _summaries(state: GameState) -> tuple[dict[str, MapNode], dict[str, _PathFacts], int]:
    if state.map is None:
        return {}, {}, 1
    nodes = {node.id: node for node in state.map.nodes}
    current_index = _index(state.map.current_node)
    floor_offset = state.run.floor - current_index if current_index is not None else 1
    cache: dict[str, _PathFacts] = {}
    visiting: set[str] = set()

    def path_score(path: tuple[str, ...]) -> tuple[int, int, int, int]:
        types = [nodes[node_id].type for node_id in path]
        return (
            types.count("Elite"),
            types.count("Monster") + types.count("Unknown"),
            -types.count("RestSite"),
            -types.count("Shop"),
        )

    def walk(node_id: str) -> _PathFacts | None:
        if node_id in cache:
            return cache[node_id]
        node = nodes.get(node_id)
        if node is None or node_id in visiting:
            return None
        visiting.add(node_id)
        children = [walk(child_id) for child_id in node.children]
        visiting.remove(node_id)
        valid_children = [child for child in children if child is not None]
        own_floor = _index(node_id)
        own_counts = {kind: int(node.type == kind) for kind in NODE_TYPES}
        possible = {
            kind: frozenset({own_floor + floor_offset})
            if kind == node.type and own_floor is not None
            else frozenset()
            for kind in NODE_TYPES
        }
        if valid_children:
            minimum = {
                kind: own_counts[kind] + min(child.min_counts[kind] for child in valid_children)
                for kind in NODE_TYPES
            }
            maximum = {
                kind: own_counts[kind] + max(child.max_counts[kind] for child in valid_children)
                for kind in NODE_TYPES
            }
            possible = {
                kind: possible[kind].union(*(child.possible_floors[kind] for child in valid_children))
                for kind in NODE_TYPES
            }
            reachable = frozenset({node_id}).union(*(child.reachable_ids for child in valid_children))
            complete = len(valid_children) == len(node.children) and all(
                child.all_paths_to_boss for child in valid_children
            )
            count = min(100_000, sum(child.path_count for child in valid_children))
            best_child = min(valid_children, key=lambda child: path_score(child.fewest_elites_path))
            fewest_elites_path = (node_id, *best_child.fewest_elites_path)
        else:
            minimum = maximum = own_counts
            reachable = frozenset({node_id})
            complete = node.type == "Boss" and not node.children
            count = 1
            fewest_elites_path = (node_id,)
        result = _PathFacts(count, complete, minimum, maximum, possible, reachable, fewest_elites_path)
        cache[node_id] = result
        return result

    for action in state.legal_actions:
        if action.node_id:
            walk(action.node_id)
    return nodes, cache, floor_offset


def _option(action: Action, nodes: dict[str, MapNode], facts: _PathFacts, floor_offset: int) -> dict:
    return {
        "action_id": action.id,
        "node_id": action.node_id,
        "node_type": nodes[action.node_id].type,
        "visible_path_count": facts.path_count,
        "all_paths_to_boss": facts.all_paths_to_boss,
        "min_elites": facts.min_counts["Elite"],
        "max_elites": facts.max_counts["Elite"],
        "min_monsters": facts.min_counts["Monster"],
        "max_monsters": facts.max_counts["Monster"],
        "min_shops": facts.min_counts["Shop"],
        "max_shops": facts.max_counts["Shop"],
        "min_rests": facts.min_counts["RestSite"],
        "max_rests": facts.max_counts["RestSite"],
        "possible_shop_game_floors": sorted(facts.possible_floors["Shop"]),
        "possible_rest_game_floors": sorted(facts.possible_floors["RestSite"]),
        "boss_game_floors": sorted(facts.possible_floors["Boss"]),
        "fewest_elites_path": [
            {"node_id": node_id, "type": nodes[node_id].type, "game_floor": _index(node_id) + floor_offset}
            for node_id in facts.fewest_elites_path
            if _index(node_id) is not None
        ],
    }


def route_options(state: GameState) -> dict | None:
    nodes, summaries, floor_offset = _summaries(state)
    options = [
        (action, summaries[action.node_id])
        for action in state.legal_actions
        if action.node_id in nodes and action.node_id in summaries
    ]
    if not options:
        return None
    shared = set.intersection(*(set(facts.reachable_ids) for _, facts in options))
    return {
        "options": [_option(action, nodes, facts, floor_offset) for action, facts in options],
        "shared_reachable_shops": sorted(node_id for node_id in shared if nodes[node_id].type == "Shop"),
        "shared_reachable_rests": sorted(node_id for node_id in shared if nodes[node_id].type == "RestSite"),
    }


def chosen_route_horizon(state: GameState, action: Action) -> dict | None:
    nodes, summaries, _ = _summaries(state)
    if action.node_id not in nodes or action.node_id not in summaries:
        return None
    facts = summaries[action.node_id]
    return {
        "act": state.run.act,
        "source_floor": state.run.floor,
        "chosen_node_id": action.node_id,
        "all_paths_to_boss": facts.all_paths_to_boss,
        "possible_shop_game_floors": sorted(facts.possible_floors["Shop"]),
        "possible_rest_game_floors": sorted(facts.possible_floors["RestSite"]),
        "boss_game_floors": sorted(facts.possible_floors["Boss"]),
    }


def last_known_shop_before_boss(state: GameState, horizon: dict) -> bool:
    if state.run.act != horizon.get("act") or not horizon.get("all_paths_to_boss"):
        return False
    bosses = horizon.get("boss_game_floors", [])
    shops = horizon.get("possible_shop_game_floors", [])
    return (
        bool(bosses) and min(bosses) > state.run.floor and not any(floor > state.run.floor for floor in shops)
    )
