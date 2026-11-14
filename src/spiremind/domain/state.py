"""Immutable game state, action schemas, scene routing, and transition verification."""

from __future__ import annotations

import inspect
import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# --- from core/enums.py ---


class Scene(StrEnum):
    COMBAT = "combat"
    CARD_SELECTION = "card_selection"
    CARD_REWARD = "card_reward"
    SHOP = "shop"
    REST = "rest"
    MAP = "map"
    EVENT = "event"
    TREASURE = "treasure"
    MAIN_MENU = "main_menu"
    CHARACTER_SELECT = "character_select"
    MODAL = "modal"
    GAME_OVER = "game_over"
    UNKNOWN = "unknown"


class ActionKind(StrEnum):
    PLAY_CARD = "play_card"
    END_TURN = "end_turn"
    CHOOSE_CARD = "choose_card"
    OPEN_CARD_REWARD = "open_card_reward"
    CLAIM_REWARD = "claim_reward"
    DISCARD_POTION = "discard_potion"
    CHOOSE_MAP_NODE = "choose_map_node"
    BUY_ITEM = "buy_item"
    REMOVE_CARD = "remove_card"
    UPGRADE_CARD = "upgrade_card"
    CHOOSE_EVENT_OPTION = "choose_event_option"
    USE_POTION = "use_potion"
    SELECT_CARD = "select_card"
    CONFIRM_SELECTION = "confirm_selection"
    SELECT_CARD_BUNDLE = "select_card_bundle"
    SKIP = "skip"
    PROCEED = "proceed"
    REST = "rest"
    SELECT_CHARACTER = "select_character"
    EMBARK = "embark"
    OPEN_RUN = "open_run"
    CONTINUE_RUN = "continue_run"
    CHOOSE_TREASURE_RELIC = "choose_treasure_relic"
    OPEN_CHEST = "open_chest"
    OPEN_SHOP = "open_shop"
    CLOSE_SHOP = "close_shop"
    OPEN_TIMELINE = "open_timeline"
    CLOSE_MENU = "close_menu"
    RETURN_TO_MAIN_MENU = "return_to_main_menu"
    OTHER = "other"


# --- from core/actions.py ---


class Action(BaseModel):
    """A command bound to a single observed decision, never free-form model params."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    decision_id: str
    kind: ActionKind
    label: str = ""
    description: str = ""
    card_id: str | None = None
    target_id: str | None = None
    node_id: str | None = None
    item_id: str | None = None
    option_id: str | None = None
    character: str | None = None
    ascension: int | None = None
    risk_tags: tuple[str, ...] = ()


class ActionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: str
    action_id: str
    previous_decision_id: str
    next_decision_id: str | None = None
    error: str | None = None


# --- from core/state.py ---


class Snapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PublicFacts(Snapshot):
    """Immutable normalized public facts; decoding always produces a fresh copy."""

    encoded: str = "{}"

    @classmethod
    def of(cls, value: Any) -> PublicFacts:
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
    legal_actions: tuple[Action, ...] = ()
    revision: int
    decision_id: str
    game_version: str
    scene_facts: PublicFacts = Field(default_factory=PublicFacts)
    victory: bool | None = None

    @property
    def terminal(self) -> bool:
        return self.scene == Scene.GAME_OVER


GameState.model_rebuild()


# --- from core/facts.py ---


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


# --- from core/transitions.py ---


def verify_transition(before: GameState, action: Action, after: GameState) -> bool:
    run_boundary = action.kind in {
        ActionKind.EMBARK,
        ActionKind.CONTINUE_RUN,
        ActionKind.RETURN_TO_MAIN_MENU,
        ActionKind.OPEN_RUN,
        ActionKind.SELECT_CHARACTER,
    }
    return (
        action in before.legal_actions
        and action.decision_id == before.decision_id
        and after.decision_id != before.decision_id
        and after.game_version == before.game_version
        and (run_boundary or after.run.id == before.run.id)
        and (run_boundary or after.run.character == before.run.character)
        and (after.revision > before.revision or (run_boundary and after.run.id != before.run.id))
    )


# --- from core/routing.py ---


def owner_for(state: GameState) -> str:
    if state.scene == Scene.UNKNOWN:
        raise ValueError("Unsupported scene: unknown")
    if state.scene == Scene.COMBAT or (
        state.scene == Scene.CARD_SELECTION and (state.combat or state.scene_facts.unpack().get("in_combat"))
    ):
        return "combat"
    if state.scene == Scene.MAP:
        return "map"
    if state.scene in {Scene.CARD_REWARD, Scene.SHOP, Scene.REST, Scene.CARD_SELECTION}:
        return "run"
    return "event"


# --- from core/async_utils.py ---


async def resolve(value):
    """Allow synchronous offline adapters alongside asynchronous production ports."""
    return await value if inspect.isawaitable(value) else value
