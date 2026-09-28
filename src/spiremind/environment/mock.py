"""Scripted contract walkthrough, deliberately not a game simulator or win benchmark."""

from spiremind.core.actions import Action, ActionResult
from spiremind.core.enums import ActionKind, Scene
from spiremind.core.state import (
    Card,
    Choice,
    CombatState,
    Enemy,
    GameState,
    Intent,
    MapNode,
    MapState,
    PublicFacts,
    RunState,
)
from spiremind.runtime.validator import ActionValidator
from spiremind.runtime.verifier import verify_transition


class MockEnvironment:
    def __init__(self, states: list[GameState] | None = None):
        self.states = states or demo_states()
        self.index = 0
        self.executed: list[Action] = []

    async def observe(self):
        return self.states[self.index]

    async def legal_actions(self):
        return list((await self.observe()).legal_actions)

    async def execute(self, action: Action):
        state = await self.observe()
        ActionValidator().validate(state, action)
        self.executed.append(action)
        self.index += 1
        return ActionResult(
            status="completed",
            action_id=action.id,
            previous_decision_id=state.decision_id,
            next_decision_id=self.states[self.index].decision_id,
        )

    async def verify(self, before, action, after):
        return verify_transition(before, action, after)


def demo_states() -> list[GameState]:
    strike = Card(id="strike", ref="c0", name="Strike", cost=1, type="attack", text="Deal 6 damage.")
    defend = Card(id="defend", ref="c1", name="Defend", cost=1, type="skill", text="Gain 5 Block.")
    enemy = Enemy(
        id="demo_enemy", ref="e0", hp=12, max_hp=12, intents=(Intent(type="attack", damage=6, hits=1),)
    )
    scenes = [
        Scene.MAIN_MENU,
        Scene.CHARACTER_SELECT,
        Scene.EVENT,
        Scene.MAP,
        Scene.COMBAT,
        Scene.CARD_REWARD,
        Scene.SHOP,
        Scene.REST,
        Scene.CARD_SELECTION,
        Scene.TREASURE,
        Scene.GAME_OVER,
    ]
    specifications = [
        [("open", ActionKind.OPEN_RUN, "Open standard run")],
        [("start", ActionKind.EMBARK, "Embark")],
        [
            ("gold", ActionKind.CHOOSE_EVENT_OPTION, "Gain 20 gold"),
            ("leave", ActionKind.CHOOSE_EVENT_OPTION, "Leave"),
        ],
        [
            ("normal", ActionKind.CHOOSE_MAP_NODE, "Normal combat"),
            ("elite", ActionKind.CHOOSE_MAP_NODE, "Elite combat"),
        ],
        [
            ("strike", ActionKind.PLAY_CARD, "Play Strike on enemy e0"),
            ("defend", ActionKind.PLAY_CARD, "Play Defend"),
            ("end", ActionKind.END_TURN, "End turn"),
        ],
        [("card", ActionKind.CHOOSE_CARD, "Take Defend"), ("skip", ActionKind.SKIP, "Skip card")],
        [("buy", ActionKind.BUY_ITEM, "Buy Defend for 50 gold"), ("leave", ActionKind.PROCEED, "Leave shop")],
        [
            ("rest", ActionKind.REST, "Rest: heal"),
            ("smith", ActionKind.UPGRADE_CARD, "Smith: upgrade a card"),
        ],
        [
            ("c0", ActionKind.UPGRADE_CARD, "Upgrade Strike"),
            ("c1", ActionKind.UPGRADE_CARD, "Upgrade Defend"),
        ],
        [("relic", ActionKind.OTHER, "Take relic"), ("leave", ActionKind.PROCEED, "Leave treasure")],
        [],
    ]
    states = []
    for i, (scene, specs) in enumerate(zip(scenes, specifications, strict=True)):
        did = f"mock-{i}"
        actions = tuple(
            Action(
                id=f"{did}:{a}",
                decision_id=did,
                kind=k,
                label=label,
                card_id={"strike": "c0", "defend": "c1"}.get(a),
                node_id={"normal": "1,0", "elite": "1,1"}.get(a),
            )
            for a, k, label in specs
        )
        states.append(
            GameState(
                scene=scene,
                decision_id=did,
                revision=i + 1,
                game_version="v0.111.0",
                run=RunState(
                    id="scripted-demo",
                    character="ironclad",
                    hp=40,
                    max_hp=80,
                    gold=100,
                    floor=max(0, i - 2),
                    deck=(strike, defend),
                    boss="Demo boss",
                ),
                legal_actions=actions,
                combat=CombatState(energy=2, turn=1, hand=(strike, defend), enemies=(enemy,))
                if scene == Scene.COMBAT
                else None,
                choices=(Choice(id="defend", label="Defend", card=defend),)
                if scene == Scene.CARD_REWARD
                else (),
                map=MapState(
                    nodes=(
                        MapNode(id="1,0", type="combat", reachable=True),
                        MapNode(id="1,1", type="elite", reachable=True),
                    )
                )
                if scene == Scene.MAP
                else None,
                scene_facts=PublicFacts.of({"selected_character_id": "IRONCLAD", "ascension": 0})
                if scene == Scene.CHARACTER_SELECT
                else PublicFacts(),
                victory=False if scene == Scene.GAME_OVER else None,
            )
        )
    return states
