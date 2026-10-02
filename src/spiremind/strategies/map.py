from spiremind.context.route_horizon import route_options
from spiremind.core.decision import Decision

from .base import LLMStrategy


class MapStrategy(LLMStrategy):
    name = "map"
    task = (
        "Compare L1_current_state.route_options before choosing a reachable map node. Treat shared "
        "reachable shops/rests as available after multiple choices, not a unique benefit of one route. "
        "Compare unavoidable elites, HP risk, potion supply and boss distance before valuing rewards. "
        "The fewest_elites_path is a visible map path, not a combat outcome prediction."
    )

    async def decide(self, state, memory) -> Decision:
        self.last_context = None
        if state.run.max_hp and state.run.hp / state.run.max_hp <= 0.5:
            horizon = route_options(state)
            options = horizon["options"] if horizon else []
            readiness = memory.run.get("elite_readiness", 1)
            if readiness < 0.5:
                for safer in options:
                    if safer["node_type"] == "Elite" or not safer["all_paths_to_boss"]:
                        continue
                    safe_path = [node["node_id"] for node in safer["fewest_elites_path"]]
                    bosses = safer["boss_game_floors"]
                    if not bosses or min(bosses) - state.run.floor > 4:
                        continue
                    for elite in options:
                        elite_path = [node["node_id"] for node in elite["fewest_elites_path"]]
                        if (
                            elite["node_type"] == "Elite"
                            and elite["all_paths_to_boss"]
                            and safer["min_elites"] < elite["min_elites"]
                            and safe_path[1:] == elite_path[1:]
                        ):
                            action = next(a for a in state.legal_actions if a.id == safer["action_id"])
                            return Decision(
                                action=action,
                                reason="Lower-risk route reaches the same downstream nodes before the boss",
                                confidence=1,
                                policy_rule="low_hp_shared_route_avoid_elite",
                            )
        return await super().decide(state, memory)
