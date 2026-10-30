from spiremind.core.decision import Decision
from spiremind.core.enums import ActionKind, Scene
from spiremind.core.state import GameState
from spiremind.decision.planning.route import last_known_shop_before_boss
from spiremind.decision.policies.base import LLMStrategy


class RunStrategy(LLMStrategy):
    name = "run"
    task = (
        "Choose a reward, purchase, removal, upgrade, rest or deck selection. Improve current deck "
        "needs and prepare for the known boss; skip weak additions. Evaluate price and survival. "
        "Use strategy_update to maintain a short boss plan and resource/route policy across scenes."
    )

    def task_for(self, state: GameState, memory) -> str:
        if state.scene == Scene.CARD_REWARD:
            return (
                "Resolve combat rewards deliberately. An open_card_reward action only reveals the offered "
                "cards and never adds one to the deck. Inspect those candidates first. Once concrete card "
                "choices are visible, compare every card with skipping and choose skip_reward_cards when "
                "none improves the deck. Check L4_deck_facts for the actual effects of cards already owned; "
                "do not infer effects from names or claim that a card grants Strength without evidence. "
                "For a Power card, estimate how many remaining turns and concrete deck triggers can repay "
                "its setup energy; do not reject Powers as a class, and do not take one merely because it "
                "is persistent. Treat explicit HpLoss as a resource cost and explicit Energy as its return. "
                "Never use reward:proceed to avoid inspecting an unopened card "
                "reward. Claim free material rewards before leaving."
            )
        if state.scene == Scene.SHOP:
            guidance = (
                "Shopping is optional. Compare every purchase and removal against saving all gold for a "
                "later shop only when a later shop is visible or plausible; affordability or synergy "
                "alone does not justify spending. Never open the "
                "inventory or buy something merely because it is available. Buy only when the option's "
                "marginal value clearly exceeds keeping the gold, and reassess after every purchase rather "
                "than chaining purchases by default. If nothing clears that threshold, leave with no "
                "purchase. Use shop:close_inventory to return to the shop overview, then shop:proceed to "
                "leave. A prior plan to buy one named item is complete once that item is owned; then prefer "
                "leaving unless a separate exceptional purchase is independently justified."
            )
            horizon = memory.run.get("route_horizon", {})
            if last_known_shop_before_boss(state, horizon):
                guidance += (
                    " The visible route has no later shop before the boss. Do not reserve gold for a "
                    "nonexistent later shop: evaluate immediate boss value of potions, cards, relics and "
                    "removal, especially at low HP. Opening inventory only reveals legal purchases; it "
                    "does not commit gold. Leaving is still correct if every offer is weak."
                )
            return guidance
        return self.task

    async def decide(self, state: GameState, memory) -> Decision:
        self.last_context = None
        unopened = next(
            (action for action in state.legal_actions if action.kind == ActionKind.OPEN_CARD_REWARD),
            None,
        )
        if unopened is not None:
            return Decision(
                action=unopened,
                reason=(
                    "Card candidates are still hidden; this action only reveals them and does not add a card"
                ),
                confidence=1,
                policy_rule="inspect_card_reward_before_skip",
            )
        if state.scene == Scene.SHOP and state.run.max_hp:
            horizon = memory.run.get("route_horizon", {})
            boss_floors = horizon.get("boss_game_floors", [])
            affordable = any(
                choice.price is not None and choice.price <= state.run.gold for choice in state.choices
            )
            open_shop = next(
                (action for action in state.legal_actions if action.kind == ActionKind.OPEN_SHOP), None
            )
            if (
                open_shop is not None
                and state.run.hp / state.run.max_hp <= 0.35
                and last_known_shop_before_boss(state, horizon)
                and min(boss_floors) - state.run.floor <= 3
                and (affordable or not state.choices)
            ):
                return Decision(
                    action=open_shop,
                    reason="Critical HP at the last visible shop before the boss; inspect affordable options",
                    confidence=1,
                    policy_rule="inspect_critical_last_shop",
                )
        return await super().decide(state, memory)
