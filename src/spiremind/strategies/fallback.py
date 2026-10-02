import re

from spiremind.core.decision import Decision
from spiremind.core.enums import ActionKind, Scene
from spiremind.core.state import GameState
from spiremind.memory.manager import MemoryContext
from spiremind.strategies.combat_tactics import assess, forced_survival_action


def conservative_choice(state: GameState, memory: MemoryContext) -> Decision:
    """A deterministic outage policy, explicitly labelled, not a claimed expert policy."""

    if state.scene == Scene.COMBAT:
        facts = memory.assessment if memory and memory.assessment is not None else assess(state)
        forced = forced_survival_action(state, facts)
        if forced:
            action, rule = forced
            return Decision(
                action=action,
                reason=f"Deterministic outage safety rule: {rule}",
                confidence=0,
                fallback=True,
                policy_rule=f"fallback_{rule}",
            )

    def score(action):
        risk_cost = {
            "lethal": 1000,
            "incoming_damage": 80,
            "hp_loss": 50,
            "curse": 40,
            "automatic_consumable": 25,
            "deck_thickening": 15,
            "irreversible": 8,
        }
        value = -sum(risk_cost.get(tag, 0) for tag in action.risk_tags)
        text = f"{action.label} {action.description}".lower()
        if "discard_potion" in action.id or "close_main_menu" in action.id or "cancel" in action.id:
            value -= 50
        if state.scene == Scene.SHOP:
            if action.kind in {ActionKind.BUY_ITEM, ActionKind.REMOVE_CARD}:
                value -= 10
            if action.id in {"shop:close_inventory", "shop:proceed"}:
                value += 20
        if action.kind == ActionKind.PLAY_CARD:
            value += 15
            if state.combat:
                card = next((c for c in state.combat.hand if action.card_id in {c.id, c.ref}), None)
                incoming = sum(
                    (i.damage or 0) * (i.hits or 1) for e in state.combat.enemies for i in e.intents
                )
                if card and ("block" in card.text.lower() or "格挡" in card.text):
                    value += 15 if incoming > state.combat.block else -10
                if card:
                    values = card.values.unpack()
                    block = values.get("CalculatedBlock", values.get("Block", 0))
                    damage = values.get("CalculatedDamage", values.get("Damage", 0))
                    if isinstance(block, (int, float)):
                        value += min(max(block, 0), max(incoming - state.combat.block, 0)) * 2
                    if isinstance(damage, (int, float)):
                        value += min(max(damage, 0), 30) / 3
        if action.kind == ActionKind.END_TURN:
            value -= 10
            if state.combat:
                incoming = sum(
                    (i.damage or 0) * (i.hits or 1) for e in state.combat.enemies for i in e.intents
                )
                value -= max(0, incoming - state.combat.block) * 3
        if action.kind == ActionKind.USE_POTION:
            value += 20 if state.run.hp < state.run.max_hp * 0.35 else -15
        if action.kind == ActionKind.CHOOSE_MAP_NODE and state.map:
            node = next((n for n in state.map.nodes if n.id == action.node_id), None)
            if node and "elite" in node.type.lower():
                value -= 25 * (1 - memory.run.get("elite_readiness", 0))
        if state.scene == Scene.CARD_REWARD and action.kind == ActionKind.SKIP:
            value += 5  # don't bloat a deck during an outage without card valuation
        if state.scene == Scene.CARD_REWARD:
            if action.id.startswith("reward:claim:"):
                # The reward overview contains gold, potion, relic and card-reward
                # entry actions. Claim these before considering the destructive
                # "leave remaining rewards" action.
                value += 100
                if "gold" in text or "金币" in text:
                    value += 20
            if action.id == "reward:proceed":
                value -= 100
        if action.kind == ActionKind.CHOOSE_EVENT_OPTION:
            numbers = [int(item) for item in re.findall(r"\d+", text)]
            amount = max(numbers, default=0)
            if any(marker in text for marker in ("最大生命", "max hp", "maximum hp")) and any(
                marker in text for marker in ("失去", "lose", "loss")
            ):
                value -= 100 + amount
            elif any(marker in text for marker in ("失去", "lose", "take")) and any(
                marker in text for marker in ("生命", " hp", "damage", "伤害")
            ):
                value -= 30 + amount
            if any(marker in text for marker in ("离开", "停止", "leave", "stop", "decline")):
                value += 40
        if action.kind == ActionKind.PROCEED:
            value += 2
        return value

    action = max(state.legal_actions, key=score)
    return Decision(action=action, reason="Deterministic conservative fallback", confidence=0, fallback=True)
