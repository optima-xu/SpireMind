from .base import LLMStrategy


class MapStrategy(LLMStrategy):
    name = "map"
    task = (
        "Choose a reachable map node using future paths, HP risk, elite readiness, gold policy, "
        "deck needs and boss preparation. Seek sustainable rewards and useful rest/shop access."
    )
