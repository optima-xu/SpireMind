from pydantic import BaseModel, Field

from spiremind.core.actions import Action


class WorkingMemory(BaseModel):
    current_goal: str = ""
    current_plan: list[Action] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    rejected_options: list[str] = Field(default_factory=list)
    decision_context: str = ""
    revision: int = -1

    def invalidate_plan(self):
        self.current_plan.clear()
        self.assumptions.clear()
        self.rejected_options.clear()
        self.decision_context = ""
