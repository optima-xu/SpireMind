"""Check only effects whose complete immediate mechanics are supported.

A receipt proves acceptance. A new observation proves a transition. Neither alone
proves that a forecast was correct, nor that the selected action was optimal.
"""

from dataclasses import dataclass, field
from typing import Literal

from spiremind.core.enums import ActionKind, Scene
from spiremind.decision.mechanics.effects import card_resources, simple_damage, target_for
from spiremind.decision.mechanics.resources import spend_and_gain
from spiremind.knowledge.library import version_matches


@dataclass(frozen=True)
class EffectVerification:
    status: Literal["unknown", "confirmed", "conflict"] = "unknown"
    expected: dict[str, int] = field(default_factory=dict)
    observed: dict[str, int] = field(default_factory=dict)
    reason: str = "unsupported_or_incomplete_effects"


def verify_effect(before, action, after):
    old, new = before.combat, after.combat
    if (
        action.kind != ActionKind.PLAY_CARD
        or not old
        or not new
        or before.scene != Scene.COMBAT
        or after.scene != Scene.COMBAT
        or before.run.id != after.run.id
        or before.run.floor != after.run.floor
        or old.turn != new.turn
        or before.run.relics
        or old.powers
        or any(enemy.powers for enemy in old.enemies if enemy.alive)
        or not version_matches("0.111.x", before.game_version)
    ):
        return EffectVerification()
    card = next((card for card in old.hand if card.ref == action.card_id), None)
    if not card or card.id not in {"strike", "defend", "bloodletting", "iron_wave", "hemokinesis"}:
        return EffectVerification()
    target = target_for(action, old.enemies)
    index = old.enemies.index(target) if target else None
    effects = card_resources(card, old, index)
    if not effects["status_effect_known"] or any(
        effects[name] for name in ("draw", "rage_per_attack", "tainted_gain", "cruelty_bonus")
    ):
        return EffectVerification()
    resources = spend_and_gain(before.run.hp, old.energy, before.run.max_hp, effects | {"cost": card.cost})
    if resources is None:
        return EffectVerification()
    expected = {"hp": resources[0], "energy": resources[1], "block": old.block + effects["block_gain"]}
    observed = {"hp": after.run.hp, "energy": new.energy, "block": new.block}
    if card.type.lower() == "attack":
        estimate = simple_damage(card, target, target_index=index) if target else None
        if not estimate:
            return EffectVerification()
        current = next((enemy for enemy in new.enemies if enemy.ref == target.ref), None)
        if current is None:
            return EffectVerification(reason="target_missing_after_transition")
        expected["target_hp"] = max(0, target.hp - estimate["hp_damage"])
        observed["target_hp"] = current.hp
    return EffectVerification(
        "confirmed" if expected == observed else "conflict",
        expected,
        observed,
        "supported_immediate_effects",
    )
