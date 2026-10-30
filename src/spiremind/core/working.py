from pydantic import BaseModel


class WorkingMemory(BaseModel):
    current_goal: str = ""
    combat_floor: int | None = None
    combat_turn: int | None = None
    lost_hp_this_turn: bool = False
