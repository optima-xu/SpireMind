from .base import LLMStrategy


class EventStrategy(LLMStrategy):
    name = "event"
    task = (
        "Choose an event, treasure or modal option using its visible costs and outcomes, deck needs, "
        "HP/gold policy and relic interactions. Do not assume undisclosed outcomes."
    )
