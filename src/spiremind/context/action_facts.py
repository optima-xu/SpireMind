"""Revision-bound numeric facts for calculator calls and model forecast validation."""

import math


def action_evaluations(state, assessment=None, *, facts_loader=None):
    if not state.combat:
        return ()
    unpack = facts_loader or (lambda facts: facts.unpack())
    cards = {card.ref: card for card in state.combat.hand}
    rows = {row["action_id"]: row for row in (assessment or {}).get("evaluated_actions", [])}
    result = []
    for action in state.legal_actions:
        forecast = {}
        card = cards.get(action.card_id)
        if card is not None:
            values = unpack(card.values)
            for field, keys in {
                "live_block": ("CalculatedBlock", "Block"),
                "live_damage_per_hit": ("CalculatedDamage", "Damage"),
                "self_hp_loss": ("HpLoss",),
            }.items():
                value = next((values[key] for key in keys if key in values), None)
                if type(value) in {int, float} and math.isfinite(value) and value >= 0:
                    forecast[field] = math.floor(value)
            target = next((enemy for enemy in state.combat.enemies if enemy.ref == action.target_id), None)
            if target is None and action.target_id and action.target_id.isdigit():
                index = int(action.target_id)
                target = state.combat.enemies[index] if index < len(state.combat.enemies) else None
            if target is not None:
                preview = unpack(card.target_values).get(str(state.combat.enemies.index(target)), {})
                damage = preview.get("CalculatedDamage", preview.get("Damage"))
                if type(damage) in {int, float} and math.isfinite(damage) and damage >= 0:
                    forecast["target_damage_per_hit"] = math.floor(damage)
        row = rows.get(action.id, {})
        if row.get("status_effect_known"):
            for field in ("hp_damage", "target_hp_after"):
                if type(row.get(field)) in {int, float} and math.isfinite(row[field]):
                    forecast[field] = math.floor(row[field])
        if forecast:
            result.append(
                {
                    "action_id": action.id,
                    "decision_id": state.decision_id,
                    "revision": state.revision,
                    "forecast": forecast,
                    "effects_complete": bool(row.get("status_effect_known")),
                }
            )
    return tuple(result)
