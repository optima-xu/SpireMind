"""Bounded combat checks from normalized public facts, without bridge previews."""

import heapq
import math
import re

from spiremind.core.enums import ActionKind, Scene
from spiremind.knowledge.library import version_matches

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
    progress = slow.trigger_progress.unpack()
    parameters = progress.get("parameters", {}) if isinstance(progress, dict) else {}
    displayed = numeric(parameters.get("DisplayAmount"))
    if displayed is not None:
        return int(displayed)
    cards_played = numeric(parameters.get("SlowAmount"))
    return int(cards_played * 10) if cards_played is not None else None


def attack_profile(card, target_index=None):
    if card.id not in SIMPLE_ATTACKS:
        return None
    values = card.values.unpack()
    if target_index is not None:
        target_values = card.target_values.unpack().get(str(target_index), {})
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
    values = card.values.unpack()
    target_values = card.target_values.unpack()
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
        target_values = card.target_values.unpack().get(str(target_index), {})
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


def visible_offense_plan(state, *, lost_hp_this_turn=False, transition_limit=MAX_SURVIVAL_SEARCH_TRANSITIONS):
    """Find a bounded full-turn plan for supported visible cards and one target.

    Draw remains unknown because pile order is hidden. Explicit HP loss, healing,
    energy gain, Tainted, Rage, Cruelty, Block, Vulnerable, and attack damage are modeled.
    This lets the search compare setup and self-damage against the same no-setup
    baseline instead of valuing each card in isolation.
    """
    result = {
        "complete": False,
        "truncated": False,
        "transitions": 0,
        "transition_limit": transition_limit,
        "max_damage": None,
        "max_damage_plan": [],
        "max_damage_hp_after_intents": None,
        "lethal_plan": [],
        "control_plan": [],
    }
    combat = state.combat
    if not combat or not version_matches("0.111.x", state.game_version):
        return result
    enemies = [enemy for enemy in combat.enemies if enemy.alive]
    if len(enemies) != 1:
        return result
    enemy = enemies[0]
    if not known_target_effects(enemy) or power(enemy, "slippery_power"):
        return result
    if any(effect.id not in KNOWN_PLAYER_POWERS for effect in combat.powers):
        # Reactive and conditional powers can change the number or result of
        # attacks; a live preview for the first card does not prove a sequence.
        return result
    initial_slow = slow_percent(enemy)
    if initial_slow is None:
        return result
    initial_giant_charges = max(0, int(player_power_amount(combat, "gigantification_power")))
    initial_cruelty = player_power_amount(combat, "cruelty_power") / 100
    target_index = combat.enemies.index(enemy)

    def matches_live_target_preview(card, profile):
        target_values = card.target_values.unpack().get(str(target_index), {})
        preview = numeric(target_values.get("CalculatedDamage", target_values.get("Damage")))
        if preview is None:
            return True
        multiplier = 1 + (0.5 + initial_cruelty if power(enemy, "vulnerable_power") else 0)
        calculated = math.floor(profile["damage"] * multiplier * (1 + initial_slow / 100))
        return math.floor(preview) == calculated

    cards = {card.ref: card for card in combat.hand}
    candidates = []
    unsupported_effect = False
    legal_card_refs = {
        action.card_id for action in state.legal_actions if action.kind == ActionKind.PLAY_CARD
    }
    for action in state.legal_actions:
        if action.kind != ActionKind.PLAY_CARD:
            continue
        card = cards.get(action.card_id)
        if not card:
            continue
        profile = attack_profile(card, target_index)
        is_attack = card.type.lower() == "attack" or profile is not None
        target = target_for(action, combat.enemies)
        cost = card.cost
        if not isinstance(cost, int) or cost < 0:
            if is_attack:
                unsupported_effect = True
            continue
        if is_attack and (target != enemy or profile is None):
            unsupported_effect = True
            continue
        resources = card_resources(card, combat, target_index)
        if not resources["status_effect_known"] or (
            is_attack and not matches_live_target_preview(card, profile)
        ):
            unsupported_effect = True
            continue
        target_values = card.target_values.unpack().get(str(target_index), {})
        applies_vulnerable = bool(numeric((card.values.unpack() | target_values).get("VulnerablePower")) or 0)
        supported_setup = (
            any(
                resources[key] > 0
                for key in (
                    "hp_loss",
                    "energy_gain",
                    "heal",
                    "block_gain",
                    "rage_per_attack",
                    "cruelty_bonus",
                )
            )
            or applies_vulnerable
        )
        if not is_attack and not supported_setup:
            continue
        candidates.append(
            {
                "action_id": action.id,
                "resource_key": action_resource_key(action, card),
                "cost": cost,
                "is_attack": is_attack,
                "applies_vulnerable": applies_vulnerable,
                **resources,
                **(profile or {"damage": 0, "hits": 0, "hits_require_hp_loss": False}),
            }
        )
    extra_energy = sum(
        card_resources(card, combat, target_index)["energy_gain"]
        for ref, card in cards.items()
        if ref in legal_card_refs
    )
    for card in combat.hand:
        if (
            card.ref in legal_card_refs
            or card.unplayable_reason != "not_enough_energy"
            or not isinstance(card.cost, int)
            or card.cost <= combat.energy
            or card.cost > combat.energy + extra_energy
        ):
            continue
        profile = attack_profile(card, target_index)
        is_attack = card.type.lower() == "attack" or profile is not None
        resources = card_resources(card, combat, target_index)
        if not resources["status_effect_known"] or (
            is_attack and profile is not None and not matches_live_target_preview(card, profile)
        ):
            unsupported_effect = True
            continue
        target_values = card.target_values.unpack().get(str(target_index), {})
        applies_vulnerable = bool(numeric((card.values.unpack() | target_values).get("VulnerablePower")) or 0)
        supported_setup = (
            any(
                resources[key] > 0
                for key in (
                    "hp_loss",
                    "energy_gain",
                    "heal",
                    "block_gain",
                    "rage_per_attack",
                    "cruelty_bonus",
                )
            )
            or applies_vulnerable
        )
        if is_attack and profile is None:
            unsupported_effect = True
            continue
        if not is_attack and not supported_setup:
            continue
        candidates.append(
            {
                "action_id": f"future:{card.ref}",
                "resource_key": f"card:{card.ref}",
                "cost": card.cost,
                "is_attack": is_attack,
                "applies_vulnerable": applies_vulnerable,
                **resources,
                **(profile or {"damage": 0, "hits": 0, "hits_require_hp_loss": False}),
            }
        )
    if unsupported_effect:
        return result
    if initial_giant_charges and any(row["is_attack"] and row["damage"] % 3 for row in candidates):
        # The current preview includes the next-attack tripling. If another
        # modifier rounded it, dividing by three cannot recover base damage.
        return result

    # A physical card can have several target-bound action variants. There is
    # only one live enemy here, but grouping keeps the resource contract exact.
    by_resource = {}
    for row in candidates:
        current = by_resource.get(row["resource_key"])
        if current is None or row["action_id"] < current["action_id"]:
            by_resource[row["resource_key"]] = row
    candidates = sorted(by_resource.values(), key=lambda row: row["action_id"])

    root = {
        "used": frozenset(),
        "cost": 0,
        "energy": combat.energy,
        "block": enemy.block,
        "damage": 0,
        "self_block": 0,
        "hp": state.run.hp,
        "lost_hp": lost_hp_this_turn,
        "rage": player_power_amount(combat, "rage_power"),
        "cruelty": initial_cruelty,
        "giant_charges": initial_giant_charges,
        "tainted_gain": 0,
        "vulnerable": bool(power(enemy, "vulnerable_power")),
        "slow": initial_slow,
        "plan": (),
    }
    stack = [root]
    seen = {}
    best = root
    best_lethal = None
    best_control = None
    card_limit = remaining_card_plays(state)
    stun_threshold = plow_stun_threshold(enemy)
    transitions = 0
    truncated = False

    def hp_after_intents(node):
        neutralized = node["damage"] >= enemy.hp or (
            stun_threshold is not None and enemy.hp - node["damage"] <= stun_threshold
        )
        shown_incoming = (
            0 if neutralized else incoming_from(enemy) + node["tainted_gain"] * attack_hits_from(enemy)
        )
        return node["hp"] - max(0, shown_incoming - combat.block - node["self_block"])

    def better_damage(candidate, incumbent):
        left = (
            candidate["damage"],
            hp_after_intents(candidate),
            candidate["energy"],
            -len(candidate["plan"]),
        )
        right = (
            incumbent["damage"],
            hp_after_intents(incumbent),
            incumbent["energy"],
            -len(incumbent["plan"]),
        )
        return left > right or (left == right and candidate["plan"] < incumbent["plan"])

    def lethal_key(node):
        return (
            len(node["plan"]),
            -hp_after_intents(node),
            node["cost"],
            -node["damage"],
            node["plan"],
        )

    while stack:
        node = stack.pop()
        if better_damage(node, best):
            best = node
        if (
            node["damage"] >= enemy.hp
            and hp_after_intents(node) > 0
            and (best_lethal is None or lethal_key(node) < lethal_key(best_lethal))
        ):
            best_lethal = node
        if (
            stun_threshold is not None
            and enemy.hp - node["damage"] <= stun_threshold
            and hp_after_intents(node) > 0
            and (best_control is None or lethal_key(node) < lethal_key(best_control))
        ):
            best_control = node
        for row in candidates:
            if row["resource_key"] in node["used"]:
                continue
            if card_limit is not None and len(node["plan"]) >= card_limit:
                continue
            if transitions >= transition_limit:
                truncated = True
                break
            transitions += 1
            if row["cost"] > node["energy"]:
                continue
            hp = node["hp"] - row["hp_loss"]
            if hp <= 0:
                continue
            hp = min(state.run.max_hp or hp + row["heal"], hp + row["heal"])
            energy = node["energy"] - row["cost"] + row["energy_gain"]
            cost = node["cost"] + row["cost"]
            block = node["block"]
            hp_damage = 0
            self_block = node["self_block"] + row["block_gain"]
            if row["is_attack"]:
                vulnerable_multiplier = 1 + (0.5 + node["cruelty"] if node["vulnerable"] else 0)
                card_damage = (
                    row["damage"] / 3
                    if initial_giant_charges and node["giant_charges"] == 0
                    else row["damage"]
                )
                per_hit = math.floor(card_damage * vulnerable_multiplier * (1 + node["slow"] / 100))
                hits = (2 if node["lost_hp"] else 1) if row["hits_require_hp_loss"] else row["hits"]
                for _ in range(hits):
                    absorbed = min(block, per_hit)
                    block -= absorbed
                    hp_damage += per_hit - absorbed
                self_block += node["rage"]
            child = {
                "used": node["used"] | {row["resource_key"]},
                "cost": cost,
                "energy": energy,
                "block": block,
                "damage": node["damage"] + hp_damage,
                "self_block": self_block,
                "hp": hp,
                "lost_hp": node["lost_hp"] or row["hp_loss"] > 0,
                "rage": node["rage"] + row["rage_per_attack"],
                "cruelty": node["cruelty"] + row["cruelty_bonus"],
                "giant_charges": max(0, node["giant_charges"] - int(row["is_attack"])),
                "tainted_gain": node["tainted_gain"] + row["tainted_gain"],
                "vulnerable": node["vulnerable"] or row["applies_vulnerable"],
                "slow": node["slow"] + (10 if power(enemy, "slow_power") else 0),
                "plan": node["plan"] + (row["action_id"],),
            }
            key = (
                child["used"],
                child["energy"],
                child["block"],
                child["self_block"],
                child["hp"],
                child["lost_hp"],
                child["rage"],
                child["cruelty"],
                child["giant_charges"],
                child["tainted_gain"],
                child["vulnerable"],
                child["slow"],
            )
            previous = seen.get(key)
            if previous is not None and previous >= child["damage"]:
                continue
            seen[key] = child["damage"]
            stack.append(child)
        if truncated:
            break

    result.update(
        complete=not truncated,
        truncated=truncated,
        transitions=transitions,
        max_damage=best["damage"] if not truncated else None,
        max_damage_plan=list(best["plan"]) if not truncated else [],
        max_damage_hp_after_intents=hp_after_intents(best) if not truncated else None,
        lethal_plan=list(best_lethal["plan"]) if best_lethal and not truncated else [],
        control_plan=list(best_control["plan"]) if best_control and not truncated else [],
    )
    return result


def assess(state, *, lost_hp_this_turn=False):
    combat = state.combat
    if not combat:
        return {}
    unmodeled_player_powers = sorted(
        effect.id for effect in combat.powers if effect.id not in KNOWN_PLAYER_POWERS
    )
    incoming = sum(incoming_from(e) for e in combat.enemies)
    attack_hits = sum(attack_hits_from(e) for e in combat.enemies)
    loss = max(0, incoming - combat.block)
    unknown = any(
        "attack" in i.type.lower() and i.damage is None and i.total_damage is None
        for e in combat.enemies
        if e.alive
        for i in e.intents
    )
    versioned = version_matches("0.111.x", state.game_version)
    cards = {c.ref: c for c in combat.hand}
    alive_indices = [index for index, enemy in enumerate(combat.enemies) if enemy.alive]
    sole_enemy_index = alive_indices[0] if len(alive_indices) == 1 else None
    choices = []
    for action in state.legal_actions:
        c = cards.get(action.card_id)
        enemy = target_for(action, combat.enemies)
        if action.kind == ActionKind.PLAY_CARD and c:
            target_index = combat.enemies.index(enemy) if enemy else None
            resources = card_resources(c, combat, target_index)
            status_known = resources["status_effect_known"]
            projected_incoming = (
                incoming_after_tainted(combat, resources["tainted_gain"]) if status_known else None
            )
            row = {
                "action_id": action.id,
                "card_ref": c.ref,
                "card_id": c.id,
                "card_type": c.type,
                "resource_key": action_resource_key(action, c),
                "cost": c.cost,
                **resources,
                "incoming_damage_after_status": projected_incoming,
                "tainted_incoming_increase": projected_incoming - incoming if status_known else None,
            }
            row["hp_after_cost"] = state.run.hp - resources["hp_loss"]
            row["self_lethal"] = row["hp_after_cost"] <= 0
            block = resources["block_gain"]
            if status_known and not row["self_lethal"] and block is not None and block > 0:
                row |= {
                    "block_gain": block,
                    "hp_after_intents": min(
                        state.run.max_hp or state.run.hp + resources["heal"],
                        state.run.hp - resources["hp_loss"] + resources["heal"],
                    )
                    - max(0, projected_incoming - combat.block - block),
                }
            elif status_known and not row["self_lethal"] and resources["heal"] > 0:
                row["hp_after_intents"] = min(
                    state.run.max_hp or state.run.hp + resources["heal"],
                    state.run.hp - resources["hp_loss"] + resources["heal"],
                ) - max(0, projected_incoming - combat.block)
            elif status_known and not row["self_lethal"] and resources["tainted_gain"] > 0:
                row["hp_after_intents"] = row["hp_after_cost"] - max(0, projected_incoming - combat.block)
            if versioned and enemy and status_known:
                estimate = simple_damage(
                    c,
                    enemy,
                    lost_hp_this_turn=lost_hp_this_turn,
                    target_index=combat.enemies.index(enemy),
                    cruelty_bonus=player_power_amount(combat, "cruelty_power") / 100,
                )
                if estimate:
                    verified_lethal = (
                        status_known and not row["self_lethal"] and estimate["hp_damage"] >= enemy.hp
                    )
                    neutralized = not row["self_lethal"] and (
                        verified_lethal or estimate["triggers_visible_stun"]
                    )
                    projected_incoming = (
                        incoming_after_tainted(
                            combat,
                            resources["tainted_gain"],
                            {enemy.ref} if neutralized else frozenset(),
                        )
                        if status_known
                        else None
                    )
                    row |= estimate | {
                        "target_ref": enemy.ref,
                        "target_hp": enemy.hp,
                        "target_hp_after": max(0, enemy.hp - estimate["hp_damage"]),
                        "verified_lethal": verified_lethal,
                        "removed_incoming_damage": incoming_from(enemy) if neutralized else 0,
                        "incoming_damage_after_status": projected_incoming,
                        "tainted_incoming_increase": (
                            projected_incoming - incoming + (incoming_from(enemy) if neutralized else 0)
                            if status_known and not row["self_lethal"]
                            else None
                        ),
                        "hp_after_intents_if_played": (
                            min(
                                state.run.max_hp or state.run.hp + resources["heal"],
                                state.run.hp - resources["hp_loss"] + resources["heal"],
                            )
                            - max(0, projected_incoming - combat.block - row.get("block_gain", 0))
                            if status_known and not row["self_lethal"]
                            else None
                        ),
                    }
            if len(row) > 2:
                row["survival_effect_complete"] = (
                    resources["status_effect_known"]
                    and bool(
                        row.get("hp_damage", 0)
                        or row.get("block_gain", 0)
                        or row.get("heal", 0)
                        or row.get("energy_gain", 0)
                        or row.get("tainted_gain", 0)
                    )
                    and not bool(
                        row.get("draw", 0) or row.get("rage_per_attack", 0) or row.get("cruelty_bonus", 0)
                    )
                    and (row["card_type"].lower() != "attack" or "hp_damage" in row)
                )
                choices.append(row)
        if action.kind == ActionKind.USE_POTION:
            row = {
                "action_id": action.id,
                "cost": 0,
                "consumable": True,
                "potion": action.item_id,
                "resource_key": action_resource_key(action),
                "target_ref": enemy.ref if enemy else None,
            }
            if versioned and (action.item_id or "").lower() == "weak_potion" and enemy:
                # Reapplying Weak while already active adds duration, not extra reduction.
                # Current Tainted is already included in the intent. Applying Weak
                # to that combined number would also reduce the Tainted damage.
                blocked = not known_target_effects(enemy) or player_power_amount(combat, "tainted_power") > 0
                reduction = (
                    sum(
                        ((i.damage or 0) - math.floor((i.damage or 0) * 0.75)) * (i.hits or 1)
                        for i in enemy.intents
                    )
                    if not power(enemy, "weak_power") and not blocked
                    else 0
                )
                row |= {
                    "intent_reduction_estimate": reduction,
                    "nonstacking_effect_key": f"weak:{enemy.ref}",
                    "hp_after_intents": state.run.hp - max(0, incoming - reduction - combat.block),
                }
            choices.append(row)
    # An unknown attack cannot be treated as zero damage. The narrow visible
    # planner deliberately abstains rather than presenting a false proof.
    planning_rows = list(choices)
    legal_card_refs = {
        action.card_id for action in state.legal_actions if action.kind == ActionKind.PLAY_CARD
    }
    extra_energy = sum(row.get("energy_gain", 0) for row in choices if row.get("card_ref") in legal_card_refs)
    if extra_energy > 0:
        for card in combat.hand:
            if (
                card.ref in legal_card_refs
                or card.unplayable_reason != "not_enough_energy"
                or not isinstance(card.cost, int)
                or card.cost <= combat.energy
                or card.cost > combat.energy + extra_energy
            ):
                continue
            resources = card_resources(card, combat, sole_enemy_index)
            if resources["block_gain"] <= 0 and resources["heal"] <= 0:
                continue
            planning_rows.append(
                {
                    "action_id": f"future:{card.ref}",
                    "card_ref": card.ref,
                    "card_id": card.id,
                    "card_type": card.type,
                    "resource_key": f"card:{card.ref}",
                    "cost": card.cost,
                    **resources,
                }
            )
    search_stats = {}
    if unknown or unmodeled_player_powers:
        survival_plan = []
        search_stats.update(
            candidate_actions=0,
            resource_groups=0,
            expanded_nodes=0,
            transitions=0,
            transition_limit=MAX_SURVIVAL_SEARCH_TRANSITIONS,
            truncated=False,
            optimal=False,
            skipped="unknown_intent_damage" if unknown else "unmodeled_player_power",
        )
    else:
        survival_plan = visible_survival_plan(state, planning_rows, incoming, search_stats=search_stats)
    one_step_survival = (
        []
        if unknown or unmodeled_player_powers
        else [
            r["action_id"]
            for r in choices
            if r.get("status_effect_known", True)
            and not r.get("self_lethal", False)
            and (
                r.get("hp_after_intents", 0) > 0
                or (r.get("removed_incoming_damage", 0) > 0 and r.get("hp_after_intents_if_played", 0) > 0)
            )
        ]
    )
    rows_by_id = {r["action_id"]: r for r in choices}
    effect_actions = [
        action
        for action in state.legal_actions
        if action.kind in {ActionKind.PLAY_CARD, ActionKind.USE_POTION}
    ]
    offense = visible_offense_plan(state, lost_hp_this_turn=lost_hp_this_turn)
    unresolved_attack_combo = any(
        row.get("card_type", "").lower() == "attack"
        and "hp_damage" in row
        and not row.get("verified_lethal")
        and not row.get("triggers_visible_stun")
        for row in choices
    )
    effects_complete = (
        not unmodeled_player_powers
        and all(
            rows_by_id.get(action.id, {}).get("survival_effect_complete", False)
            or rows_by_id.get(action.id, {}).get("intent_reduction_estimate", 0) > 0
            for action in effect_actions
        )
        and (not unresolved_attack_combo or offense["complete"])
        and not search_stats.get("truncated", False)
    )
    survival_known = not unknown and effects_complete
    if unknown:
        survival_status = "unknown"
    elif (
        loss < state.run.hp
        or survival_plan
        or one_step_survival
        or offense["lethal_plan"]
        or offense["control_plan"]
    ):
        survival_status = "survives"
    elif survival_known:
        survival_status = "dead"
    else:
        survival_status = "unknown"
    boss_name_matches = bool(
        state.run.boss and any(e.name == state.run.boss for e in combat.enemies if e.alive)
    )
    boss_floor = state.run.floor > 0 and state.run.floor % 17 == 0
    visible_cards = (*combat.hand, *combat.draw.cards, *combat.discard.cards)
    vulnerable_sources_remaining = sum(
        card.count for card in visible_cards if numeric(card.values.unpack().get("VulnerablePower"))
    )
    immediate_vulnerable_sources = sum(
        1
        for row in choices
        if row.get("card_ref") and numeric(cards[row["card_ref"]].values.unpack().get("VulnerablePower"))
    )
    vulnerable_enemies_now = sum(
        bool(power(enemy, "vulnerable_power")) for enemy in combat.enemies if enemy.alive
    )
    playable_attacks_now = sum(row.get("card_type", "").lower() == "attack" for row in choices)
    setup_options = [
        {
            "action_id": row["action_id"],
            "card_id": row["card_id"],
            "card_type": row["card_type"],
            "cost": row["cost"],
            "draw_per_vulnerable": (
                max(0, numeric(cards[row["card_ref"]].values.unpack().get("Cards")) or 0)
                if row["card_id"] == "vicious"
                else 0
            ),
            "draw_blocked_now": player_power_amount(combat, "no_draw_power") > 0,
            "vulnerable_sources_remaining": vulnerable_sources_remaining,
            "immediate_vulnerable_sources": immediate_vulnerable_sources,
            "vulnerable_enemies_now": vulnerable_enemies_now,
            "playable_attacks_now": playable_attacks_now,
            "extra_vulnerable_damage_fraction": row["cruelty_bonus"],
            "rage_block_per_attack": row["rage_per_attack"],
        }
        for row in choices
        if row.get("card_type", "").lower() == "power"
        or row.get("cruelty_bonus", 0) > 0
        or row.get("rage_per_attack", 0) > 0
    ]
    self_harm_options = []
    for row in choices:
        if row.get("hp_loss", 0) <= 0:
            continue
        if unknown or not row.get("status_effect_known", True):
            self_harm_options.append(
                {
                    "action_id": row["action_id"],
                    "card_id": row["card_id"],
                    "hp_loss": row["hp_loss"],
                    "status_effect_known": False,
                    "reason": "unknown_intent_damage" if unknown else "unmodeled_card_or_power_effect",
                }
            )
            continue
        row_cost = row.get("cost")
        energy_after = (
            combat.energy - row_cost + row["energy_gain"]
            if isinstance(row_cost, int) and row_cost >= 0
            else -1
        )
        enabled_followups = []
        for card in combat.hand:
            if (
                card.ref == row.get("card_ref")
                or card.unplayable_reason != "not_enough_energy"
                or not isinstance(card.cost, int)
                or card.cost <= combat.energy
                or card.cost > energy_after
            ):
                continue
            followup = card_resources(card, combat, sole_enemy_index)
            if not followup["status_effect_known"] or (followup["heal"] <= 0 and followup["block_gain"] <= 0):
                continue
            enabled_followups.append(
                {
                    "card_ref": card.ref,
                    "card_id": card.id,
                    "cost": card.cost,
                    "heal": followup["heal"],
                    "hp_loss": followup["hp_loss"],
                    "block_gain": followup["block_gain"],
                    "tainted_gain": followup["tainted_gain"],
                }
            )

        def projected_hp(followup=None, action_row=row):
            hp = state.run.hp - action_row["hp_loss"]
            if hp <= 0:
                return None
            hp = min(state.run.max_hp or hp + action_row["heal"], hp + action_row["heal"])
            block = action_row.get("block_gain", 0)
            tainted = action_row["tainted_gain"]
            if followup:
                hp -= followup["hp_loss"]
                if hp <= 0:
                    return None
                hp = min(state.run.max_hp or hp + followup["heal"], hp + followup["heal"])
                block += followup["block_gain"]
                tainted += followup["tainted_gain"]
            return hp - max(0, incoming + tainted * attack_hits - combat.block - block)

        base_hp = projected_hp()
        feasible_followups = [item for item in enabled_followups if projected_hp(item) is not None]
        best_followup = max(
            feasible_followups,
            key=lambda item: (projected_hp(item), item["heal"], item["card_ref"]),
            default=None,
        )
        if best_followup and base_hp is not None and projected_hp(best_followup) <= base_hp:
            best_followup = None
        best_enabled_heal = best_followup["heal"] if best_followup else 0
        hp_after_enabled_heal = projected_hp(best_followup)
        self_harm_options.append(
            {
                "action_id": row["action_id"],
                "card_id": row["card_id"],
                "hp_loss": row["hp_loss"],
                "hp_after_cost": row["hp_after_cost"],
                "self_lethal": row["self_lethal"],
                "energy_gain": row["energy_gain"],
                "heal": row["heal"],
                "tainted_gain": row["tainted_gain"],
                "hp_after_shown_intents_if_only_cost": state.run.hp
                - row["hp_loss"]
                - max(0, incoming + row["tainted_gain"] * attack_hits - combat.block),
                "enabled_followups": enabled_followups,
                "best_enabled_followup": best_followup["card_ref"] if best_followup else None,
                "best_enabled_heal": best_enabled_heal,
                "hp_after_shown_intents_with_best_followup": hp_after_enabled_heal,
                "net_hp_delta_vs_end_now_with_best_followup": (
                    hp_after_enabled_heal - (state.run.hp - loss)
                    if hp_after_enabled_heal is not None
                    else None
                ),
            }
        )
    return {
        "scope": "visible attack intents only; excludes end-turn triggers and hidden effects",
        "in_boss_fight": bool(state.run.boss and (boss_name_matches or boss_floor)),
        "incoming_attack_damage": incoming,
        "incoming_attack_hits": attack_hits if attack_hit_count_known(combat) else None,
        "intent_hits_incomplete": not attack_hit_count_known(combat),
        "unblocked_attack_damage": loss,
        "hp_after_intents_if_end_now": state.run.hp - loss,
        "minimum_additional_block_to_survive": (None if unknown else max(0, loss - state.run.hp + 1)),
        "visible_survival_margin_if_end_now": None if unknown else state.run.hp - loss,
        "same_attack_twice_hp_scenario": None if unknown else state.run.hp - 2 * loss,
        "intent_damage_incomplete": unknown,
        "visible_survival_plan": survival_plan,
        "survival_search": search_stats,
        "visible_survival_known": survival_known,
        "survival_status": survival_status,
        "action_effects_complete": effects_complete,
        "visible_one_step_survival_actions": one_step_survival,
        "no_visible_survival": survival_status == "dead",
        "verified_lethal_actions": [
            r["action_id"]
            for r in choices
            if r.get("verified_lethal") and r.get("hp_after_intents_if_played", 0) > 0
        ],
        "visible_max_damage": offense["max_damage"],
        "visible_max_damage_plan": offense["max_damage_plan"],
        "visible_max_damage_hp_after_intents": offense["max_damage_hp_after_intents"],
        "verified_lethal_plan": offense["lethal_plan"],
        "visible_control_plan": offense["control_plan"],
        "lost_hp_this_turn": lost_hp_this_turn,
        "visible_setup_options": setup_options,
        "visible_self_harm_options": self_harm_options,
        "remaining_card_plays": remaining_card_plays(state),
        "visible_damage_plan_known": offense["complete"],
        "damage_search": {key: offense[key] for key in ("transitions", "transition_limit", "truncated")},
        "player_strength": sum(p.amount or 0 for p in combat.powers if p.id == "strength_power"),
        "player_tainted": player_power_amount(combat, "tainted_power"),
        "draw_blocked_now": player_power_amount(combat, "no_draw_power") > 0,
        "unmodeled_player_powers": unmodeled_player_powers,
        "damage_caps": [
            {"enemy": e.ref, "remaining_hits": p.amount, "text": p.description}
            for e in combat.enemies
            for p in e.powers
            if p.id == "slippery_power"
        ],
        "evaluated_actions": choices,
    }


def visible_survival_plan(state, rows, incoming, *, search_stats=None):
    """Find a bounded, provably best visible-action sequence for this attack.

    The queue is ordered by consumables, energy, action count, then remaining HP.
    Physical resources form mutually exclusive groups, so target variants never
    multiply a card or potion. If the transition bound prevents proving optimality,
    the planner abstains instead of forcing a partially searched plan.
    """
    combat = state.combat
    if not combat:
        if search_stats is not None:
            search_stats.update(
                candidate_actions=0,
                resource_groups=0,
                expanded_nodes=0,
                transitions=0,
                transition_limit=MAX_SURVIVAL_SEARCH_TRANSITIONS,
                truncated=False,
                optimal=True,
            )
        return []

    groups = {}
    for row in rows:
        if not row.get("status_effect_known", True):
            continue
        cost = row.get("cost")
        visible_effect = (
            row.get("block_gain", 0)
            + row.get("intent_reduction_estimate", 0)
            + row.get("removed_incoming_damage", 0)
            + row.get("heal", 0)
            + row.get("energy_gain", 0)
        )
        if visible_effect <= 0 or not isinstance(cost, int) or cost < 0:
            continue
        resource = row.get("resource_key", row["action_id"])
        groups.setdefault(resource, []).append(row)

    resource_groups = [
        (resource, tuple(sorted(options, key=lambda row: row["action_id"])))
        for resource, options in sorted(groups.items())
    ]
    resource_groups.sort(
        key=lambda group: (
            -max(row.get("energy_gain", 0) for row in group[1]),
            group[0],
        )
    )
    candidate_count = sum(len(options) for _, options in resource_groups)
    card_limit = remaining_card_plays(state)

    def hp_after(node):
        reduction = sum(amount for _, _, amount in node["reductions"])
        remaining_hits = sum(
            attack_hits_from(enemy)
            for enemy in combat.enemies
            if enemy.alive and enemy.ref not in node["killed"]
        )
        loss = max(
            0,
            incoming
            - node["removed"]
            - reduction
            + node["tainted_gain"] * remaining_hits
            - combat.block
            - node["block"],
        )
        return node["hp"] - loss

    def action_ids(node):
        return tuple(row["action_id"] for row in node["selected"])

    def primary(node):
        return node["consumables"], node["cost"], len(node["selected"])

    def priority(node):
        return primary(node) + (-hp_after(node), action_ids(node))

    def state_key(node):
        return (
            node["cost"],
            node["consumables"],
            node["card_plays"],
            node["energy_gain"],
            node["hp"],
            node["tainted_gain"],
            node["used"],
            node["killed"],
            node["effects"],
            node["block"],
            node["removed"],
            node["reductions"],
        )

    root = {
        "cost": 0,
        "consumables": 0,
        "card_plays": 0,
        "energy_gain": 0,
        "hp": state.run.hp,
        "tainted_gain": 0,
        "used": frozenset(),
        "killed": frozenset(),
        "effects": frozenset(),
        "block": 0,
        "removed": 0,
        "reductions": (),
        "selected": (),
    }
    if hp_after(root) > 0:
        if search_stats is not None:
            search_stats.update(
                candidate_actions=candidate_count,
                resource_groups=len(resource_groups),
                expanded_nodes=0,
                transitions=0,
                transition_limit=MAX_SURVIVAL_SEARCH_TRANSITIONS,
                truncated=False,
                optimal=True,
            )
        return []

    heap = [(priority(root), 0, root)]
    seen = {state_key(root): action_ids(root)}
    serial = 0
    expanded = 0
    transitions = 0
    truncated = False
    best = None

    while heap:
        _, _, node = heapq.heappop(heap)
        if seen.get(state_key(node)) != action_ids(node):
            continue
        if best is not None and primary(node) > best[0][:3]:
            break
        expanded += 1
        current_hp = hp_after(node)
        if node["selected"] and current_hp > 0:
            objective = primary(node) + (-current_hp, action_ids(node))
            if best is None or objective < best[0]:
                best = objective, node
            continue
        if best is not None and primary(node) == best[0][:3]:
            # Every successor spends another action and therefore cannot match
            # the already proven primary objective.
            continue

        hit_limit = False
        for resource, options in resource_groups:
            if resource in node["used"]:
                continue
            for row in options:
                if transitions >= MAX_SURVIVAL_SEARCH_TRANSITIONS:
                    truncated = hit_limit = True
                    break
                transitions += 1
                available_energy = combat.energy + node["energy_gain"] - node["cost"]
                if row["cost"] > available_energy:
                    continue
                cost = node["cost"] + row["cost"]
                energy_gain = node["energy_gain"] + row.get("energy_gain", 0)
                hp_before_heal = node["hp"] - row.get("hp_loss", 0)
                if hp_before_heal <= 0:
                    continue
                hp = min(
                    state.run.max_hp or hp_before_heal + row.get("heal", 0),
                    hp_before_heal + row.get("heal", 0),
                )
                card_plays = node["card_plays"] + int(not row.get("consumable"))
                if card_limit is not None and card_plays > card_limit:
                    continue
                effect = row.get("nonstacking_effect_key")
                if effect and effect in node["effects"]:
                    continue
                target = row.get("target_ref")
                lethal = bool(row.get("removed_incoming_damage", 0) > 0 and target)
                if lethal and target in node["killed"]:
                    continue

                killed = node["killed"] | ({target} if lethal else set())
                effects = node["effects"] | ({effect} if effect else set())
                reductions = list(node["reductions"])
                if lethal:
                    reductions = [entry for entry in reductions if entry[1] != target]
                elif effect and target not in killed:
                    reductions.append((effect, target, row.get("intent_reduction_estimate", 0)))
                child = {
                    "cost": cost,
                    "consumables": node["consumables"] + int(bool(row.get("consumable"))),
                    "card_plays": card_plays,
                    "energy_gain": energy_gain,
                    "hp": hp,
                    "tainted_gain": node["tainted_gain"] + row.get("tainted_gain", 0),
                    "used": node["used"] | {resource},
                    "killed": frozenset(killed),
                    "effects": frozenset(effects),
                    "block": node["block"] + row.get("block_gain", 0),
                    "removed": node["removed"] + (row.get("removed_incoming_damage", 0) if lethal else 0),
                    "reductions": tuple(sorted(reductions)),
                    "selected": node["selected"] + (row,),
                }
                key = state_key(child)
                ids = action_ids(child)
                if key in seen and seen[key] <= ids:
                    continue
                seen[key] = ids
                serial += 1
                heapq.heappush(heap, (priority(child), serial, child))
            if hit_limit:
                break
        if hit_limit:
            break

    optimal = not truncated
    if search_stats is not None:
        search_stats.update(
            candidate_actions=candidate_count,
            resource_groups=len(resource_groups),
            expanded_nodes=expanded,
            transitions=transitions,
            transition_limit=MAX_SURVIVAL_SEARCH_TRANSITIONS,
            truncated=truncated,
            optimal=optimal,
        )
    if best is None or not optimal:
        return []

    # Preserve the simulated order: moving an energy card earlier can make the
    # returned sequence unplayable when that card itself has an energy cost.
    selected = best[1]["selected"]
    dead = set()
    for row in selected:
        target = row.get("target_ref")
        if target in dead:
            return []
        if row.get("removed_incoming_damage", 0) and target:
            dead.add(target)
    return [row["action_id"] for row in selected]


def forced_combat_selection_action(state):
    """Handle an unambiguous in-combat exhaust picker without asking the LLM.

    Selecting a card here applies the picker operation; it does not play the card.
    Prefer a visible unplayable Status/Curse so useful hand actions stay available.
    """
    if state.scene != Scene.CARD_SELECTION:
        return None
    facts = state.scene_facts.unpack()
    if not facts.get("in_combat") or facts.get("operation") != "exhaust":
        return None
    cards = {choice.card.ref: choice.card for choice in state.choices if choice.card}
    ranked = []
    for action in state.legal_actions:
        card = cards.get(action.card_id)
        if not card:
            continue
        keywords = {x.lower() for x in card.keywords}
        disposable = card.type in {"status", "curse"} or "unplayable" in keywords
        if disposable:
            ranked.append(("unplayable" in keywords, card.type == "status", action))
    if not ranked:
        return None
    return max(ranked, key=lambda row: row[:2])[2], "exhaust_unplayable_card"


def forced_survival_action(state, facts, potion_fraction=0.20):
    """Return a legal action and named rule, or let the model decide.

    The guard is conservative and does not claim to solve the combat. A verified
    visible lethal sequence takes priority; estimates are limited to v0.111.x mechanics.
    """
    if not state.combat or not facts:
        return None
    rows = facts["evaluated_actions"]
    by_id = {a.id: a for a in state.legal_actions}
    lethal_plan = facts.get("verified_lethal_plan") or []
    if lethal_plan and lethal_plan[0] in by_id:
        rule = "take_verified_lethal" if len(lethal_plan) == 1 else "follow_verified_lethal_plan"
        return by_id[lethal_plan[0]], rule
    if facts["intent_damage_incomplete"]:
        return None
    danger = facts["hp_after_intents_if_end_now"] <= 0
    if danger:
        lethal = [
            r for r in rows if r.get("verified_lethal") and (r.get("hp_after_intents_if_played") or 0) > 0
        ]
        if lethal:
            best = max(lethal, key=lambda r: (r["hp_after_intents_if_played"], r["hp_damage"]))
            return by_id[best["action_id"]], "take_verified_lethal"
        control = [
            r
            for r in rows
            if r.get("triggers_visible_stun") and (r.get("hp_after_intents_if_played") or 0) > 0
        ]
        if control:
            best = max(control, key=lambda r: (r["hp_after_intents_if_played"], r["hp_damage"]))
            return by_id[best["action_id"]], "trigger_visible_stun"
        control_plan = facts.get("visible_control_plan") or []
        if control_plan and control_plan[0] in by_id:
            return by_id[control_plan[0]], "follow_visible_stun_plan"
        plan = facts.get("visible_survival_plan") or []
        if plan:
            planned = next(r for r in rows if r["action_id"] == plan[0])
            if len(plan) > 1:
                rule = "follow_visible_survival_plan"
            elif planned.get("triggers_visible_stun"):
                rule = "trigger_visible_stun"
            elif planned.get("intent_reduction_estimate", 0) > 0:
                rule = "use_defensive_potion_for_current_threat"
            else:
                rule = "avoid_visible_lethal_with_block"
            return by_id[plan[0]], rule
    heavy_boss_hit = (
        facts["in_boss_fight"] and facts["unblocked_attack_damage"] >= state.run.max_hp * potion_fraction
    )
    if danger or heavy_boss_hit:
        potions = [
            r
            for r in rows
            if r.get("intent_reduction_estimate", 0) > 0 and (not danger or r.get("hp_after_intents", 0) > 0)
        ]
        if potions:
            best = max(potions, key=lambda r: r["intent_reduction_estimate"])
            return by_id[best["action_id"]], "use_defensive_potion_for_current_threat"
    return None


def early_boss_potion_action(state, facts):
    """Spend persistent buff/draw potions while a long, wounded boss fight can use them."""
    if (
        not state.combat
        or not facts.get("in_boss_fight")
        or not version_matches("0.111.x", state.game_version)
        or state.combat.turn > 3
        or state.run.hp > state.run.max_hp * 0.75
        or facts.get("verified_lethal_plan")
        or facts.get("visible_control_plan")
    ):
        return None
    enemies = [enemy for enemy in state.combat.enemies if enemy.alive]
    if len(enemies) != 1 or enemies[0].hp <= enemies[0].max_hp * 0.5:
        return None
    potions = [action for action in state.legal_actions if action.kind == ActionKind.USE_POTION]
    has_clarity = any(p.id == "clarity_power" for p in state.combat.powers)
    if (
        not has_clarity
        and state.combat.energy > 0
        and state.combat.draw.count > 0
        and len(state.combat.hand) <= 7
    ):
        clarity = next((a for a in potions if (a.item_id or "").lower() == "clarity"), None)
        if clarity:
            return clarity, "use_early_boss_draw_potion"
    dexterity = sum((p.amount or 0) for p in state.combat.powers if p.id == "dexterity_power")
    if dexterity == 0 and facts.get("unblocked_attack_damage", 0) >= state.run.max_hp * 0.15:
        cards = {card.ref: card for card in state.combat.hand}
        has_block_action = any(
            action.kind == ActionKind.PLAY_CARD
            and (card := cards.get(action.card_id)) is not None
            and (numeric(card.values.unpack().get("CalculatedBlock", card.values.unpack().get("Block"))) or 0)
            > 0
            for action in state.legal_actions
        )
        if has_block_action:
            potion = next((a for a in potions if (a.item_id or "").lower() == "dexterity_potion"), None)
            if potion:
                return potion, "use_early_boss_dexterity_potion"
    return None
