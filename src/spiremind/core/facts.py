from pydantic import BaseModel, ConfigDict, Field

from spiremind.core.state import PublicFacts


class CardFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    card_id: str
    game_version: str
    source_version: str
    text: str
    upgraded: bool = False
    cost: int | None = None
    star_cost: int | None = None
    type: str = ""
    values: PublicFacts = Field(default_factory=PublicFacts)

    def context_view(self):
        return self.model_dump(exclude={"values"}) | {"values": self.values.unpack()}
