import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .enums import Scene


class Snapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PublicFacts(Snapshot):
    """Immutable normalized public facts; decoding always produces a fresh copy."""

    encoded: str = "{}"

    @classmethod
    def of(cls, value: Any) -> "PublicFacts":
        return cls(encoded=json.dumps(value, ensure_ascii=False, separators=(",", ":")))

    def unpack(self) -> Any:
        return json.loads(self.encoded)


class Power(Snapshot):
    id: str
    amount: float | None = None
    description: str = ""
    trigger_progress: PublicFacts = Field(default_factory=PublicFacts)


class Card(Snapshot):
    id: str
    ref: str = ""
    name: str = ""
    type: str = ""
    cost: int | None = None
    star_cost: int | None = None
    upgraded: bool = False
    text: str = ""
    keywords: tuple[str, ...] = ()
    values: PublicFacts = Field(default_factory=PublicFacts)
    target_values: PublicFacts = Field(default_factory=PublicFacts)
    affliction_id: str = ""
    affliction_amount: int | None = None
    affliction_description: str = ""
    playable: bool | None = None
    unplayable_reason: str = ""
    count: int = Field(default=1, ge=1)


class Intent(Snapshot):
    type: str
    damage: int | None = None
    hits: int | None = None
    total_damage: int | None = None
    text: str = ""


class Enemy(Snapshot):
    id: str
    ref: str
    name: str = ""
    hp: int
    max_hp: int = 0
    block: int = 0
    powers: tuple[Power, ...] = ()
    intents: tuple[Intent, ...] = ()
    alive: bool = True


class Item(Snapshot):
    id: str
    name: str = ""
    text: str = ""
    slot: int | None = None
    amount: int | None = None
    trigger_progress: PublicFacts = Field(default_factory=PublicFacts)


class RunState(Snapshot):
    id: str = "menu"
    character: str = "unknown"
    ascension: int = 0
    act: int | None = None
    floor: int = 0
    max_energy: int = 0
    hp: int = 0
    max_hp: int = 0
    gold: int = 0
    deck: tuple[Card, ...] = ()
    relics: tuple[Item, ...] = ()
    potions: tuple[Item, ...] = ()
    boss: str = ""
    second_boss: str = ""


class Pile(Snapshot):
    count: int = 0
    # Counts and unordered identities only; never future draw order.
    cards: tuple[Card, ...] = ()


class CombatState(Snapshot):
    turn_phase: str = "unknown"
    energy: int = 0
    stars: int = 0
    focus: int = 0
    block: int = 0
    turn: int = 0
    attacks_played: int = 0
    hand: tuple[Card, ...] = ()
    draw: Pile = Field(default_factory=Pile)
    discard: Pile = Field(default_factory=Pile)
    exhaust: Pile = Field(default_factory=Pile)
    powers: tuple[Power, ...] = ()
    enemies: tuple[Enemy, ...] = ()
    orbs: PublicFacts = Field(default_factory=PublicFacts)


class MapNode(Snapshot):
    id: str
    type: str
    children: tuple[str, ...] = ()
    reachable: bool = False


class MapState(Snapshot):
    current_node: str = ""
    nodes: tuple[MapNode, ...] = ()


class Choice(Snapshot):
    id: str
    label: str
    description: str = ""
    card: Card | None = None
    price: int | None = None


class GameState(Snapshot):
    scene: Scene
    run: RunState = Field(default_factory=RunState)
    combat: CombatState | None = None
    map: MapState | None = None
    choices: tuple[Choice, ...] = ()
    legal_actions: tuple["Action", ...] = ()
    revision: int
    decision_id: str
    game_version: str
    scene_facts: PublicFacts = Field(default_factory=PublicFacts)
    victory: bool | None = None

    @property
    def terminal(self) -> bool:
        return self.scene == Scene.GAME_OVER


from .actions import Action  # noqa: E402

GameState.model_rebuild()
