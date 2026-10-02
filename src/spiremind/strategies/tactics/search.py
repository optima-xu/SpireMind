import heapq
import math

from spiremind.core.enums import ActionKind
from spiremind.knowledge.library import version_matches

from .effects import (
    KNOWN_PLAYER_POWERS,
    MAX_SURVIVAL_SEARCH_TRANSITIONS,
    action_resource_key,
    attack_hits_from,
    attack_profile,
    card_resources,
    facts_of,
    incoming_from,
    known_target_effects,
    numeric,
    player_power_amount,
    plow_stun_threshold,
    power,
    remaining_card_plays,
    slow_percent,
    target_for,
)


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
        target_values = facts_of(card.target_values).get(str(target_index), {})
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
        target_values = facts_of(card.target_values).get(str(target_index), {})
        applies_vulnerable = bool(
            numeric((facts_of(card.values) | target_values).get("VulnerablePower")) or 0
        )
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
        target_values = facts_of(card.target_values).get(str(target_index), {})
        applies_vulnerable = bool(
            numeric((facts_of(card.values) | target_values).get("VulnerablePower")) or 0
        )
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
