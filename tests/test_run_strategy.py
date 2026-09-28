from spiremind.core.actions import Action
from spiremind.core.enums import ActionKind, Scene
from spiremind.core.state import GameState, RunState
from spiremind.memory.manager import MemoryContext
from spiremind.strategies.run import RunStrategy

MEMORY = MemoryContext(snapshot_id="test", run={}, working={}, skills=())


def test_shop_task_makes_no_purchase_a_first_class_option() -> None:
    current = GameState(
        scene=Scene.SHOP,
        run=RunState(id="run", hp=80, max_hp=80, gold=300),
        revision=1,
        decision_id="decision",
        game_version="test",
    )
    strategy = RunStrategy(None, None, None)

    task = strategy.task_for(current, MEMORY)

    assert "Shopping is optional" in task
    assert "leave with no purchase" in task
    assert "affordability or synergy alone does not justify spending" in task


async def test_unopened_card_reward_is_inspected_before_skip() -> None:
    current = GameState(
        scene=Scene.CARD_REWARD,
        run=RunState(id="run", hp=70, max_hp=80),
        legal_actions=(
            Action(
                id="reward:claim:0",
                decision_id="decision",
                kind=ActionKind.OPEN_CARD_REWARD,
                label="View card reward choices",
            ),
            Action(
                id="reward:proceed",
                decision_id="decision",
                kind=ActionKind.PROCEED,
                label="Skip remaining rewards and proceed",
            ),
        ),
        revision=1,
        decision_id="decision",
        game_version="test",
    )

    decision = await RunStrategy(None, None, None).decide(current, MEMORY)

    assert decision.action.id == "reward:claim:0"
    assert decision.policy_rule == "inspect_card_reward_before_skip"
    assert decision.confidence == 1


def test_card_reward_task_distinguishes_inspection_from_selection() -> None:
    current = GameState(
        scene=Scene.CARD_REWARD,
        run=RunState(id="run"),
        revision=1,
        decision_id="decision",
        game_version="test",
    )

    task = RunStrategy(None, None, None).task_for(current, MEMORY)

    assert "only reveals the offered cards" in task
    assert "compare every card with skipping" in task
