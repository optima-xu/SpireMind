from spiremind.core.actions import Action
from spiremind.core.enums import ActionKind, Scene
from spiremind.core.state import Card, CombatState, Enemy, GameState, Intent, PublicFacts, RunState
from spiremind.memory.manager import MemoryContext
from spiremind.strategies.fallback import conservative_choice

MEMORY = MemoryContext(snapshot_id="test", run={}, working={}, skills=())


def state(scene: Scene, actions: list[Action]) -> GameState:
    return GameState(
        scene=scene,
        run=RunState(id="run", hp=80, max_hp=80),
        legal_actions=tuple(actions),
        revision=1,
        decision_id="decision",
        game_version="test",
    )


def action(action_id: str, kind: ActionKind, label: str = "", description: str = "") -> Action:
    return Action(
        id=action_id,
        decision_id="decision",
        kind=kind,
        label=label,
        description=description,
    )


def test_outage_claims_reward_before_proceeding() -> None:
    current = state(
        Scene.CARD_REWARD,
        [
            action("reward:claim:0", ActionKind.OTHER, "Claim Gold"),
            action("reward:claim:1", ActionKind.OTHER, "Claim Card"),
            action("reward:proceed", ActionKind.PROCEED, "Skip remaining rewards"),
        ],
    )

    assert conservative_choice(current, MEMORY).action.id == "reward:claim:0"


def test_outage_stops_escalating_max_hp_event_cost() -> None:
    current = state(
        Scene.EVENT,
        [
            action(
                "event:option:0",
                ActionKind.CHOOSE_EVENT_OPTION,
                "继续解读",
                "失去12点最大生命。随机升级一张牌。",
            ),
            action(
                "event:option:1",
                ActionKind.CHOOSE_EVENT_OPTION,
                "离开",
                "停止阅读并离开。",
            ),
        ],
    )

    assert conservative_choice(current, MEMORY).action.id == "event:option:1"


def test_outage_leaves_shop_instead_of_forcing_a_purchase() -> None:
    current = state(
        Scene.SHOP,
        [
            action("shop:buy_card:0", ActionKind.BUY_ITEM, "Buy card"),
            action("shop:remove_card", ActionKind.REMOVE_CARD, "Remove a card"),
            action("shop:close_inventory", ActionKind.OTHER, "Close shop inventory"),
        ],
    )

    assert conservative_choice(current, MEMORY).action.id == "shop:close_inventory"


def test_outage_combat_uses_visible_survival_action_before_generic_scoring() -> None:
    block = Card(
        id="defend",
        ref="card:defend:0",
        cost=1,
        text="Gain 8 Block.",
        values=PublicFacts.of({"Block": 8}),
    )
    current = GameState(
        scene=Scene.COMBAT,
        run=RunState(id="run", hp=5, max_hp=80),
        combat=CombatState(
            energy=1,
            hand=(block,),
            enemies=(
                Enemy(
                    id="enemy",
                    ref="enemy:0",
                    hp=20,
                    intents=(Intent(type="Attack", damage=7, hits=1),),
                ),
            ),
        ),
        legal_actions=(
            Action(
                id="combat:play:defend",
                decision_id="decision",
                kind=ActionKind.PLAY_CARD,
                card_id=block.ref,
            ),
            Action(
                id="combat:end_turn",
                decision_id="decision",
                kind=ActionKind.END_TURN,
                risk_tags=("incoming_damage", "lethal"),
            ),
        ),
        revision=1,
        decision_id="decision",
        game_version="v0.111.0",
    )

    decision = conservative_choice(current, MEMORY)

    assert decision.action.id == "combat:play:defend"
    assert decision.policy_rule == "fallback_avoid_visible_lethal_with_block"
