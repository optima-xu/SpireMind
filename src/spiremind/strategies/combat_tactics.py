"""Small, auditable combat checks from visible facts; no bridge previews or search."""

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
}
KNOWN_TARGET_POWERS = {
    "personal_hive_power",
    "slippery_power",
    "slow_power",
    "strength_power",
    "vulnerable_power",
    "weak_power",
}


def numeric(value):
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


def power(enemy, identity):
    return next((p for p in enemy.powers if p.id == identity and (p.amount or 0) > 0), None)


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
    return sum((i.damage or 0) * (i.hits or 1) for i in enemy.intents if enemy.alive)


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


def attack_profile(card):
    if card.id not in SIMPLE_ATTACKS:
        return None
    values = card.values.unpack()
    damage = numeric(values.get("CalculatedDamage", values.get("Damage")))
    if damage is None:
        return None
    return {
        "damage": damage,
        "hits": int(values.get("Repeat", 2 if card.id == "twin_strike" else 1)),
        "applies_vulnerable": bool(numeric(values.get("VulnerablePower")) or 0),
    }


def simple_damage(card, enemy):
    """Narrow estimate; live card values already contain owner bonuses.

    Do not add the target's Strength to the card, or re-add owner Strength.
    Unknown target powers intentionally disable this estimate.
    """
    if any(p.id not in KNOWN_TARGET_POWERS for p in enemy.powers):
        return None
    profile = attack_profile(card)
    slow = slow_percent(enemy)
    if not profile or slow is None:
        return None
    hits = profile["hits"]
    damage = math.floor(
        profile["damage"] * (1.5 if power(enemy, "vulnerable_power") else 1) * (1 + slow / 100)
    )
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
    return {"hp_damage": loss, "hits": hits, "cap_layers_consumed": (int(cap.amount) if cap else 0) - layers}


def visible_offense_plan(state, *, transition_limit=MAX_SURVIVAL_SEARCH_TRANSITIONS):
    """Find the exact best remaining-hand attack order for a supported single target.

    This deliberately ignores draw and unsupported card effects. It models target
    Block, Vulnerable, and the current per-turn Slow counter. Any unsupported
    attack or target power makes the result unknown rather than optimistic.
    """
    result = {
        "complete": False,
        "truncated": False,
        "transitions": 0,
        "transition_limit": transition_limit,
        "max_damage": None,
        "max_damage_plan": [],
        "lethal_plan": [],
    }
    combat = state.combat
    if not combat or not version_matches("0.111.x", state.game_version):
        return result
    enemies = [enemy for enemy in combat.enemies if enemy.alive]
    if len(enemies) != 1:
        return result
    enemy = enemies[0]
    if any(p.id not in KNOWN_TARGET_POWERS or p.id == "slippery_power" for p in enemy.powers):
        return result
    initial_slow = slow_percent(enemy)
    if initial_slow is None:
        return result

    cards = {card.ref: card for card in combat.hand}
    candidates = []
    unsupported_attack = False
    for action in state.legal_actions:
        if action.kind != ActionKind.PLAY_CARD:
            continue
        card = cards.get(action.card_id)
        if not card:
            continue
        profile = attack_profile(card)
        is_attack = card.type.lower() == "attack" or profile is not None
        if not is_attack:
            continue
        target = target_for(action, combat.enemies)
        cost = card.cost
        if target != enemy or profile is None or not isinstance(cost, int) or cost < 0:
            unsupported_attack = True
            continue
        candidates.append(
            {
                "action_id": action.id,
                "resource_key": action_resource_key(action, card),
                "cost": cost,
                **profile,
            }
        )
    if unsupported_attack:
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
        "block": enemy.block,
        "damage": 0,
        "vulnerable": bool(power(enemy, "vulnerable_power")),
        "slow": initial_slow,
        "plan": (),
    }
    stack = [root]
    seen = {}
    best = root
    best_lethal = None
    transitions = 0
    truncated = False

    def better_damage(candidate, incumbent):
        left = (candidate["damage"], -candidate["cost"], -len(candidate["plan"]))
        right = (incumbent["damage"], -incumbent["cost"], -len(incumbent["plan"]))
        return left > right or (left == right and candidate["plan"] < incumbent["plan"])

    def lethal_key(node):
        return len(node["plan"]), node["cost"], -node["damage"], node["plan"]

    while stack:
        node = stack.pop()
        if better_damage(node, best):
            best = node
        if node["damage"] >= enemy.hp and (best_lethal is None or lethal_key(node) < lethal_key(best_lethal)):
            best_lethal = node
        for row in candidates:
            if row["resource_key"] in node["used"]:
                continue
            if transitions >= transition_limit:
                truncated = True
                break
            transitions += 1
            cost = node["cost"] + row["cost"]
            if cost > combat.energy:
                continue
            per_hit = math.floor(
                row["damage"] * (1.5 if node["vulnerable"] else 1) * (1 + node["slow"] / 100)
            )
            block = node["block"]
            hp_damage = 0
            for _ in range(row["hits"]):
                absorbed = min(block, per_hit)
                block -= absorbed
                hp_damage += per_hit - absorbed
            child = {
                "used": node["used"] | {row["resource_key"]},
                "cost": cost,
                "block": block,
                "damage": node["damage"] + hp_damage,
                "vulnerable": node["vulnerable"] or row["applies_vulnerable"],
                "slow": node["slow"] + (10 if power(enemy, "slow_power") else 0),
                "plan": node["plan"] + (row["action_id"],),
            }
            key = (child["used"], child["cost"], child["block"], child["vulnerable"], child["slow"])
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
        lethal_plan=list(best_lethal["plan"]) if best_lethal and not truncated else [],
    )
    return result


def assess(state):
    combat = state.combat
    if not combat:
        return {}
    incoming = sum(incoming_from(e) for e in combat.enemies)
    loss = max(0, incoming - combat.block)
    unknown = any(
        "attack" in i.type.lower() and i.damage is None for e in combat.enemies if e.alive for i in e.intents
    )
    versioned = version_matches("0.111.x", state.game_version)
    cards = {c.ref: c for c in combat.hand}
    choices = []
    for action in state.legal_actions:
        c = cards.get(action.card_id)
        enemy = target_for(action, combat.enemies)
        if action.kind == ActionKind.PLAY_CARD and c:
            values = c.values.unpack()
            row = {
                "action_id": action.id,
                "card_ref": c.ref,
                "resource_key": action_resource_key(action, c),
                "cost": c.cost,
            }
            block = numeric(values.get("CalculatedBlock", values.get("Block")))
            if block is not None and block > 0:
                row |= {
                    "block_gain": block,
                    "hp_after_intents": state.run.hp - max(0, incoming - combat.block - block),
                }
            if versioned and enemy:
                estimate = simple_damage(c, enemy)
                if estimate:
                    verified_lethal = estimate["hp_damage"] >= enemy.hp
                    projected_incoming = incoming - (incoming_from(enemy) if verified_lethal else 0)
                    row |= estimate | {
                        "target_ref": enemy.ref,
                        "target_hp": enemy.hp,
                        "verified_lethal": verified_lethal,
                        "removed_incoming_damage": incoming_from(enemy) if verified_lethal else 0,
                        "hp_after_intents_if_played": state.run.hp
                        - max(0, projected_incoming - combat.block),
                    }
            if len(row) > 2:
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
                blocked = any(p.id not in KNOWN_TARGET_POWERS for p in enemy.powers)
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
    search_stats = {}
    if unknown:
        survival_plan = []
        search_stats.update(
            candidate_actions=0,
            resource_groups=0,
            expanded_nodes=0,
            transitions=0,
            transition_limit=MAX_SURVIVAL_SEARCH_TRANSITIONS,
            truncated=False,
            optimal=False,
            skipped="unknown_intent_damage",
        )
    else:
        survival_plan = visible_survival_plan(state, choices, incoming, search_stats=search_stats)
    one_step_survival = (
        []
        if unknown
        else [
            r["action_id"]
            for r in choices
            if r.get("hp_after_intents", 0) > 0
            or (r.get("verified_lethal") and r.get("hp_after_intents_if_played", 0) > 0)
        ]
    )
    rows_by_id = {r["action_id"]: r for r in choices}
    effect_actions = [
        action
        for action in state.legal_actions
        if action.kind in {ActionKind.PLAY_CARD, ActionKind.USE_POTION}
    ]
    effects_complete = all(
        any(
            key in rows_by_id.get(action.id, {})
            for key in ("block_gain", "hp_damage", "intent_reduction_estimate")
        )
        for action in effect_actions
    )
    survival_known = not unknown and effects_complete
    if unknown:
        survival_status = "unknown"
    elif loss < state.run.hp or survival_plan or one_step_survival:
        survival_status = "survives"
    elif survival_known:
        survival_status = "dead"
    else:
        survival_status = "unknown"
    boss_name_matches = bool(
        state.run.boss and any(e.name == state.run.boss for e in combat.enemies if e.alive)
    )
    boss_floor = state.run.floor > 0 and state.run.floor % 17 == 0
    offense = visible_offense_plan(state)
    return {
        "scope": "visible attack intents only; excludes end-turn triggers and hidden effects",
        "in_boss_fight": bool(state.run.boss and (boss_name_matches or boss_floor)),
        "incoming_attack_damage": incoming,
        "unblocked_attack_damage": loss,
        "hp_after_intents_if_end_now": state.run.hp - loss,
        "minimum_additional_block_to_survive": (None if unknown else max(0, loss - state.run.hp + 1)),
        "visible_survival_margin_if_end_now": None if unknown else state.run.hp - loss,
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
        "verified_lethal_plan": offense["lethal_plan"],
        "visible_damage_plan_known": offense["complete"],
        "damage_search": {key: offense[key] for key in ("transitions", "transition_limit", "truncated")},
        "player_strength": sum(p.amount or 0 for p in combat.powers if p.id == "strength_power"),
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
        cost = row.get("cost")
        visible_effect = (
            row.get("block_gain", 0)
            + row.get("intent_reduction_estimate", 0)
            + row.get("removed_incoming_damage", 0)
        )
        if visible_effect <= 0 or not isinstance(cost, int) or cost < 0:
            continue
        resource = row.get("resource_key", row["action_id"])
        groups.setdefault(resource, []).append(row)

    resource_groups = [
        (resource, tuple(sorted(options, key=lambda row: row["action_id"])))
        for resource, options in sorted(groups.items())
    ]
    candidate_count = sum(len(options) for _, options in resource_groups)

    def hp_after(node):
        reduction = sum(amount for _, _, amount in node["reductions"])
        loss = max(
            0,
            incoming - node["removed"] - reduction - combat.block - node["block"],
        )
        return state.run.hp - loss

    def action_ids(node):
        return tuple(row["action_id"] for row in node["selected"])

    def primary(node):
        return node["consumables"], node["cost"], len(node["selected"])

    def priority(node):
        return primary(node) + (-hp_after(node), action_ids(node))

    def state_key(node):
        return (
            node["next_group"],
            node["cost"],
            node["consumables"],
            node["used"],
            node["killed"],
            node["effects"],
            node["block"],
            node["removed"],
            node["reductions"],
        )

    root = {
        "next_group": 0,
        "cost": 0,
        "consumables": 0,
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
        for group_index in range(node["next_group"], len(resource_groups)):
            resource, options = resource_groups[group_index]
            for row in options:
                if transitions >= MAX_SURVIVAL_SEARCH_TRANSITIONS:
                    truncated = hit_limit = True
                    break
                transitions += 1
                cost = node["cost"] + row["cost"]
                if cost > combat.energy:
                    continue
                effect = row.get("nonstacking_effect_key")
                if effect and effect in node["effects"]:
                    continue
                target = row.get("target_ref")
                lethal = bool(row.get("verified_lethal") and target)
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
                    "next_group": group_index + 1,
                    "cost": cost,
                    "consumables": node["consumables"] + int(bool(row.get("consumable"))),
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

    # Apply target effects before the action that kills that target. The stable
    # action-id tie break keeps equivalent plans reproducible across input order.
    selected = sorted(
        best[1]["selected"],
        key=lambda row: (bool(row.get("verified_lethal")), row["action_id"]),
    )
    dead = set()
    for row in selected:
        target = row.get("target_ref")
        if target in dead:
            return []
        if row.get("verified_lethal") and target:
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
        lethal = [r for r in rows if r.get("verified_lethal") and r.get("hp_after_intents_if_played", 0) > 0]
        if lethal:
            best = max(lethal, key=lambda r: (r["hp_after_intents_if_played"], r["hp_damage"]))
            return by_id[best["action_id"]], "take_verified_lethal"
        plan = facts.get("visible_survival_plan") or []
        if plan:
            planned = next(r for r in rows if r["action_id"] == plan[0])
            if len(plan) > 1:
                rule = "follow_visible_survival_plan"
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
