import math

from spiremind.core.enums import ActionKind, Scene
from spiremind.knowledge.library import version_matches

from .effects import (
    KNOWN_PLAYER_POWERS,
    MAX_SURVIVAL_SEARCH_TRANSITIONS,
    action_resource_key,
    attack_hit_count_known,
    attack_hits_from,
    card_resources,
    facts_of,
    incoming_after_tainted,
    incoming_from,
    known_target_effects,
    numeric,
    parsed_scope,
    player_power_amount,
    power,
    remaining_card_plays,
    simple_damage,
    target_for,
)
from .search import visible_offense_plan, visible_survival_plan


def _assess(state, *, lost_hp_this_turn=False):
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
        card.count for card in visible_cards if numeric(facts_of(card.values).get("VulnerablePower"))
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


def forced_combat_selection_action(state):
    """Handle an unambiguous in-combat exhaust picker without asking the LLM.

    Selecting a card here applies the picker operation; it does not play the card.
    Prefer a visible unplayable Status/Curse so useful hand actions stay available.
    """
    if state.scene != Scene.CARD_SELECTION:
        return None
    facts = facts_of(state.scene_facts)
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
            and (
                numeric(facts_of(card.values).get("CalculatedBlock", facts_of(card.values).get("Block"))) or 0
            )
            > 0
            for action in state.legal_actions
        )
        if has_block_action:
            potion = next((a for a in potions if (a.item_id or "").lower() == "dexterity_potion"), None)
            if potion:
                return potion, "use_early_boss_dexterity_potion"
    return None


def assess(state, *, lost_hp_this_turn=False):
    """Parse each immutable public fact once per complete decision assessment."""
    with parsed_scope():
        return _assess(state, lost_hp_this_turn=lost_hp_this_turn)
