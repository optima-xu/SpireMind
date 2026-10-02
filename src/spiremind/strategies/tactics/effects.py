import math
import re
from contextlib import contextmanager
from contextvars import ContextVar

from spiremind.core.enums import ActionKind
from spiremind.knowledge.library import version_matches

_parsed = ContextVar("combat_public_facts", default=None)


@contextmanager
def parsed_scope():
    token = _parsed.set({})
    try:
        yield
    finally:
        _parsed.reset(token)


def facts_of(facts):
    cache = _parsed.get()
    if cache is None:
        return facts.unpack()
    if facts.encoded not in cache:
        cache[facts.encoded] = facts.unpack()
    return cache[facts.encoded]


MAX_SURVIVAL_SEARCH_TRANSITIONS = 4096

SIMPLE_ATTACKS = {
    "strike",
    "strike_ironclad",
    "bash",
    "pommel_strike",
    "iron_wave",
    "twin_strike",
    "sword_boomerang",
    "thunderclap",
    "perfected_strike",
    "headbutt",
    "breakthrough",
    "molten_fist",
    "spite",
}

KNOWN_TARGET_POWERS = {
    "minion_power",  # v0.111.x: follower flees when the leader dies; no damage modifier.
    "personal_hive_power",
    "slippery_power",
    "slow_power",
    "strength_power",
    "vulnerable_power",
    "vital_spark_power",  # Adds a visible Tainted affliction to Skills, not an attack modifier.
    "weak_power",
    "plow_power",
}

KNOWN_PLAYER_POWERS = {
    "aggression_power",  # Start-of-turn effect is already reflected in the hand.
    "cruelty_power",
    "dexterity_power",  # The live card preview already includes this Block modifier.
    "frail_power",  # The live card preview already includes this Block modifier.
    "gigantification_power",
    "no_draw_power",
    "rage_power",
    "ringing_power",
    "shrink_power",
    "strength_power",
    "tainted_power",  # Current stacks are already reflected in enemy intents.
    "vicious_power",  # Draw is outside the visible-hand search.
    "vulnerable_power",  # The live enemy intent already includes this modifier.
    "weak_power",
}

MODELED_CARD_VALUE_KEYS = {
    "Block",
    "CalculatedBlock",
    "Damage",
    "CalculatedDamage",
    "CalculationBase",
    "ExtraDamage",
    "Repeat",
    "HpLoss",
    "Energy",
    "Heal",
    "Cards",
    "VulnerablePower",
    "CrueltyPower",
}

UNMODELED_CARD_EFFECTS = {
    "armaments",  # Upgrades another card in the current hand.
    "battle_trance",  # Also prevents further draws this turn.
    "burning_pact",  # Exhausts a selected card before drawing.
    "true_grit",  # Exhausts another card, possibly one in the proposed plan.
}


def numeric(value):
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


def power(enemy, identity):
    return next((p for p in enemy.powers if p.id == identity and (p.amount or 0) > 0), None)


def plow_stun_threshold(enemy):
    """The v0.111.x Plow threshold is public, and its trigger cancels this attack."""
    effect = power(enemy, "plow_power")
    if not effect:
        return None
    threshold = numeric(effect.amount)
    description = effect.description.lower()
    if (
        threshold is None
        or not 0 < threshold < enemy.hp
        or not (
            ("击晕" in description and "力量" in description)
            or ("stun" in description and "strength" in description)
        )
    ):
        return None
    return threshold


def known_target_effects(enemy):
    return all(
        p.id in KNOWN_TARGET_POWERS and (p.id != "plow_power" or plow_stun_threshold(enemy) is not None)
        for p in enemy.powers
    )


def remaining_card_plays(state):
    """Only the exact v0.111.x Ringing restriction is interpreted here."""
    if not state.combat or not version_matches("0.111.x", state.game_version):
        return None
    if not any(p.id == "ringing_power" and p.amount == 1 for p in state.combat.powers):
        return None
    return int(any(a.kind == ActionKind.PLAY_CARD for a in state.legal_actions))


def target_for(action, enemies):
    if action.target_id:
        direct = next((e for e in enemies if e.ref == action.target_id), None)
        if direct:
            return direct
        if action.target_id.isdigit() and int(action.target_id) < len(enemies):
            return enemies[int(action.target_id)]
    alive = [e for e in enemies if e.alive]
    return alive[0] if len(alive) == 1 else None


def incoming_from(enemy):
    return sum(
        i.total_damage if i.total_damage is not None else (i.damage or 0) * (i.hits or 1)
        for i in enemy.intents
        if enemy.alive
    )


def attack_hits_from(enemy):
    return sum(
        max(1, i.hits or 1)
        for i in enemy.intents
        if enemy.alive and "attack" in i.type.lower() and (i.damage is not None or i.total_damage is not None)
    )


def attack_hit_count_known(combat):
    return all(
        isinstance(intent.hits, int) and intent.hits > 0
        for enemy in combat.enemies
        if enemy.alive
        for intent in enemy.intents
        if "attack" in intent.type.lower()
    )


def incoming_after_tainted(combat, tainted_gain=0, removed_targets=frozenset()):
    """Intent damage already includes current Tainted; add only newly gained stacks."""
    return sum(
        incoming_from(enemy) + tainted_gain * attack_hits_from(enemy)
        for enemy in combat.enemies
        if enemy.alive and enemy.ref not in removed_targets
    )


def action_resource_key(action, card=None):
    """Identify the physical card or potion consumed by a bound action.

    A targetable card or potion is exposed as one legal action per target. Those
    actions are alternatives, not separate resources that can all be used in a
    single plan.
    """
    if card:
        return f"card:{card.ref or action.card_id or action.id}"
    if action.kind == ActionKind.USE_POTION:
        slot = action.option_id
        if slot is None:
            parts = action.id.split(":")
            try:
                slot = parts[parts.index("use_potion") + 1]
            except (ValueError, IndexError):
                # Treat indistinguishable copies conservatively as one resource.
                slot = action.item_id or action.id
        return f"potion:{slot}"
    return action.id


def slow_percent(enemy):
    slow = power(enemy, "slow_power")
    if not slow:
        return 0
    progress = facts_of(slow.trigger_progress)
    parameters = progress.get("parameters", {}) if isinstance(progress, dict) else {}
    displayed = numeric(parameters.get("DisplayAmount"))
    if displayed is not None:
        return int(displayed)
    cards_played = numeric(parameters.get("SlowAmount"))
    return int(cards_played * 10) if cards_played is not None else None


def attack_profile(card, target_index=None):
    if card.id not in SIMPLE_ATTACKS:
        return None
    values = facts_of(card.values)
    if target_index is not None:
        target_values = facts_of(card.target_values).get(str(target_index), {})
        values |= {key: target_values[key] for key in ("Repeat", "VulnerablePower") if key in target_values}
    damage = numeric(values.get("CalculatedDamage", values.get("Damage")))
    if damage is None:
        return None
    return {
        "damage": damage,
        "hits": int(values.get("Repeat", 2 if card.id == "twin_strike" else 1)),
        "hits_require_hp_loss": card.id == "spite",
        "applies_vulnerable": bool(numeric(values.get("VulnerablePower")) or 0),
    }


def tainted_gain(card):
    """Read a visible, unconditional Tainted gain; unknown afflictions are not estimated."""
    text = re.sub(r"\[[^\]]*\]", "", card.text)
    gains = [
        int(value) for value in re.findall(r"(?:获得|gain)\s*(\d+)\s*(?:层)?\s*(?:污染|tainted)", text, re.I)
    ]
    if card.affliction_id == "tainted":
        amount = card.affliction_amount
        if not isinstance(amount, int) or amount < 0:
            return None
        # A second Tainted clause may have a separate trigger. Do not merge it
        # into an unconditional affliction without knowing that trigger.
        return amount if len(gains) <= 1 and (not gains or gains[0] == amount) else None
    if card.affliction_id:
        return None
    if "污染" in text or "tainted" in text.lower():
        return None
    return 0


def card_resources(card, combat=None, target_index=None):
    """Return only explicit, public resource changes from a live card."""
    values = facts_of(card.values)
    target_values = facts_of(card.target_values)
    if target_index is not None:
        values = values | target_values.get(str(target_index), {})
    unknown_target_resources = bool(
        target_index is None
        and any(
            key not in {"Damage", "CalculatedDamage"} for preview in target_values.values() for key in preview
        )
    )
    tainted = tainted_gain(card)
    unmodeled_values = set(values) - MODELED_CARD_VALUE_KEYS
    if card.id == "rage":
        unmodeled_values.discard("Power")
    if ("CalculationBase" in values or "ExtraDamage" in values) and "CalculatedDamage" not in values:
        unmodeled_values.add("CalculatedDamage")
    missing_affliction = bool(
        combat
        and card.type.lower() == "skill"
        and not card.affliction_id
        and any(power(enemy, "vital_spark_power") for enemy in combat.enemies if enemy.alive)
    )
    unknown_player_power = bool(
        combat and any(effect.id not in KNOWN_PLAYER_POWERS for effect in combat.powers)
    )
    unknown_attack_hits = bool(combat and tainted and not attack_hit_count_known(combat))
    unknown_tainted_multiplier = bool(
        combat
        and tainted
        and (
            any(effect.id == "vulnerable_power" for effect in combat.powers)
            or any(power(enemy, "weak_power") for enemy in combat.enemies if enemy.alive)
        )
    )
    draw_blocked = bool(combat and player_power_amount(combat, "no_draw_power") > 0)
    immediate_draw = (
        0 if draw_blocked or card.type.lower() == "power" else max(0, numeric(values.get("Cards")) or 0)
    )
    cruelty = max(0, numeric(values.get("CrueltyPower")) or 0) / 100
    return {
        "hp_loss": max(0, numeric(values.get("HpLoss")) or 0),
        "energy_gain": max(0, numeric(values.get("Energy")) or 0),
        "heal": max(0, numeric(values.get("Heal")) or 0),
        "draw": immediate_draw,
        "block_gain": math.floor(max(0, numeric(values.get("CalculatedBlock", values.get("Block"))) or 0)),
        "rage_per_attack": (max(0, numeric(values.get("Power")) or 0) if card.id == "rage" else 0),
        "cruelty_bonus": cruelty,
        "tainted_gain": tainted or 0,
        "status_effect_known": (
            tainted is not None
            and not unmodeled_values
            and not unknown_target_resources
            and card.id not in UNMODELED_CARD_EFFECTS
            and not missing_affliction
            and not unknown_player_power
            and not unknown_attack_hits
            and not unknown_tainted_multiplier
            and (card.type.lower() != "power" or cruelty > 0)
        ),
    }


def player_power_amount(combat, identity):
    return sum(numeric(effect.amount) or 0 for effect in combat.powers if effect.id == identity)


def simple_damage(card, enemy, *, lost_hp_this_turn=False, target_index=None, cruelty_bonus=0):
    """Narrow estimate; live card values already contain owner bonuses.

    Do not add the target's Strength to the card, or re-add owner Strength.
    Unknown target powers intentionally disable this estimate.
    """
    if not known_target_effects(enemy):
        return None
    profile = attack_profile(card, target_index)
    slow = slow_percent(enemy)
    if not profile or (profile["hits_require_hp_loss"] and not lost_hp_this_turn) or slow is None:
        return None
    hits = 2 if profile["hits_require_hp_loss"] else profile["hits"]
    multiplier = 1 + (0.5 + cruelty_bonus if power(enemy, "vulnerable_power") else 0)
    damage = math.floor(profile["damage"] * multiplier * (1 + slow / 100))
    if target_index is not None:
        target_values = facts_of(card.target_values).get(str(target_index), {})
        preview = numeric(target_values.get("CalculatedDamage", target_values.get("Damage")))
        if preview is not None and math.floor(preview) != damage:
            return None
    cap = power(enemy, "slippery_power")
    layers = int(cap.amount) if cap else 0
    if cap and not re.search(r"(?:只会失去|only lose)\s*1", re.sub(r"\[[^\]]*\]", "", cap.description)):
        return None
    # Slippery limits HP loss, not damage absorbed by block.
    block, loss = enemy.block, 0
    for _ in range(hits):
        remaining = max(0, damage - block)
        block = max(0, block - damage)
        if remaining and layers:
            remaining = min(1, remaining)
            layers -= 1
        loss += remaining
    threshold = plow_stun_threshold(enemy)
    return {
        "hp_damage": loss,
        "hits": hits,
        "cap_layers_consumed": (int(cap.amount) if cap else 0) - layers,
        "triggers_visible_stun": bool(threshold is not None and enemy.hp - loss <= threshold),
    }
