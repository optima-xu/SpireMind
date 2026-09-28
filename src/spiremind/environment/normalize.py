"""The only module that translates bridge payloads into domain snapshots.

No preview, evaluator, hidden draw order, diagnostics, or raw state is admitted.
"""

from spiremind.core.actions import Action
from spiremind.core.enums import ActionKind, Scene
from spiremind.core.state import (
    Card,
    Choice,
    CombatState,
    Enemy,
    GameState,
    Intent,
    Item,
    MapNode,
    MapState,
    Pile,
    Power,
    PublicFacts,
    RunState,
)

PHASES = {
    "combat": Scene.COMBAT,
    "combat_selection": Scene.CARD_SELECTION,
    "selection": Scene.CARD_SELECTION,
    "reward": Scene.CARD_REWARD,
    "map": Scene.MAP,
    "shop": Scene.SHOP,
    "rest": Scene.REST,
    "event": Scene.EVENT,
    "chest": Scene.TREASURE,
    "modal": Scene.MODAL,
    "main_menu": Scene.MAIN_MENU,
    "character_select": Scene.CHARACTER_SELECT,
    "custom_run": Scene.CHARACTER_SELECT,
    "game_over": Scene.GAME_OVER,
}
KINDS = {
    "choose_reward_card": ActionKind.CHOOSE_CARD,
    "skip_reward_cards": ActionKind.SKIP,
    "buy_card": ActionKind.BUY_ITEM,
    "buy_relic": ActionKind.BUY_ITEM,
    "buy_potion": ActionKind.BUY_ITEM,
    "remove_card_at_shop": ActionKind.REMOVE_CARD,
    "select_deck_card": ActionKind.SELECT_CARD,
    "toggle_card": ActionKind.SELECT_CARD,
    "choose_rest_option": ActionKind.REST,
    "open_character_select": ActionKind.OPEN_RUN,
    "discard_potion": ActionKind.DISCARD_POTION,
    "confirm_selection": ActionKind.CONFIRM_SELECTION,
    "select_card_bundle": ActionKind.SELECT_CARD_BUNDLE,
    "choose_treasure_relic": ActionKind.CHOOSE_TREASURE_RELIC,
    "open_chest": ActionKind.OPEN_CHEST,
    "open_shop_inventory": ActionKind.OPEN_SHOP,
    "close_shop_inventory": ActionKind.CLOSE_SHOP,
    "open_timeline": ActionKind.OPEN_TIMELINE,
    "close_main_menu_submenu": ActionKind.CLOSE_MENU,
    "return_to_main_menu": ActionKind.RETURN_TO_MAIN_MENU,
}


def norm_id(value: str) -> str:
    return value.lower().replace(" ", "_").removeprefix("card.").removeprefix("card:")


def card(value: dict) -> Card:
    values = {
        name: v.get("preview_value", v.get("base_value"))
        for name, v in (value.get("dynamic_vars") or {}).items()
        if isinstance(v, dict)
    }
    return Card(
        id=norm_id(value.get("card_id", "unknown")),
        ref=value.get("card_ref", ""),
        name=value.get("name", ""),
        type=value.get("card_type", "").lower(),
        cost=value.get("energy_cost"),
        star_cost=value.get("star_cost"),
        upgraded=value.get("upgraded", False),
        text=value.get("resolved_rules_text") or value.get("rules_text") or value.get("description") or "",
        keywords=tuple(value.get("keywords") or ()),
        values=PublicFacts.of(values),
        playable=value.get("playable"),
        count=value.get("count", 1),
    )


def powers(items: list) -> tuple[Power, ...]:
    return tuple(
        Power(
            id=norm_id(p.get("power_id", "unknown")),
            amount=p.get("amount"),
            description=p.get("description") or "",
            trigger_progress=PublicFacts.of(p.get("trigger_progress") or {}),
        )
        for p in items
    )


def coord(value: dict | None) -> str:
    return f"{value['row']},{value['col']}" if value and "row" in value else ""


def selection_operation(value: dict) -> str | None:
    """Turn localized selection prose into a narrow action semantic.

    Only operations whose wording is unambiguous are classified. Unknown prompts
    remain model-visible data instead of being guessed here.
    """
    prompt = str(value.get("prompt") or "").lower()
    if "消耗" in prompt or "exhaust" in prompt:
        return "exhaust"
    return None


def public_options(context: dict, scene: Scene) -> tuple[tuple[Choice, ...], PublicFacts]:
    # Explicit field selection keeps the external schema out of strategies.
    name = {
        Scene.CARD_REWARD: "reward",
        Scene.CARD_SELECTION: "selection",
        Scene.EVENT: "event",
        Scene.SHOP: "shop",
        Scene.REST: "rest",
        Scene.TREASURE: "chest",
        Scene.CHARACTER_SELECT: "character_select",
        Scene.MODAL: "modal",
    }.get(scene, "")
    value = context.get(name) or {}
    fields = (
        "title",
        "name",
        "description",
        "body",
        "prompt",
        "min_select",
        "max_select",
        "selected_count",
        "selection_type",
        "kind",
        "requires_confirmation",
        "can_confirm",
        "can_skip",
        "can_cancel",
        "selected_character_id",
        "ascension",
        "can_embark",
        "is_custom",
        "is_multiplayer",
    )
    facts = {k: value[k] for k in fields if value.get(k) is not None}
    if scene == Scene.CARD_SELECTION:
        facts["in_combat"] = bool((context.get("combat") or {}).get("player"))
        operation = selection_operation(value)
        if operation:
            facts["operation"] = operation
            facts["operation_effect"] = (
                "The chosen card is exhausted from hand; its card text is not played or triggered."
            )
    removal = value.get("card_removal")
    if isinstance(removal, dict):
        facts["card_removal"] = {
            k: removal[k] for k in ("price", "available", "used", "enough_gold") if k in removal
        }
    choices = []
    for key in ("card_options", "cards", "options", "rewards", "relics", "potions", "items"):
        for index, option in enumerate(value.get(key) or []):
            if not isinstance(option, dict):
                continue
            nested_card = option.get("card") if isinstance(option.get("card"), dict) else option
            choices.append(
                Choice(
                    id=str(option.get("card_ref") or option.get("index", f"{key}-{index}")),
                    label=str(option.get("name") or option.get("label") or option.get("title") or ""),
                    description=option.get("description")
                    or option.get("text")
                    or option.get("rules_text")
                    or "",
                    card=card(nested_card) if nested_card.get("card_id") else None,
                    price=option.get("price"),
                )
            )
    return tuple(choices), PublicFacts.of(facts)


def normalize(payload: dict, revision: int, game_version: str) -> GameState:
    decision_id = payload["decision_id"]
    if not payload.get("stable"):
        raise ValueError("Refusing unstable decision")
    scene = PHASES.get(payload.get("phase"), Scene.UNKNOWN)
    ctx, summary = payload.get("context") or {}, payload.get("summary") or {}
    selection_op = selection_operation(ctx.get("selection") or {})
    r, c = ctx.get("run") or {}, ctx.get("combat") or {}
    player = c.get("player") or {}
    over = ctx.get("game_over") or {}
    boss = r.get("boss_encounter") or {}
    second_boss = r.get("second_boss_encounter") or {}
    floor = r.get("floor") or summary.get("floor") or over.get("floor") or 0
    act = summary.get("act") if summary.get("act") is not None else r.get("act")
    if act is None and floor > 0:
        # The bridge currently exposes a global floor but no act. Standard runs
        # advance acts after each 17-floor segment.
        act = ((floor - 1) // 17) + 1
    run = RunState(
        id=str(payload.get("run_id") or "menu"),
        character=norm_id(
            r.get("character_id") or summary.get("character_id") or over.get("character_id") or "unknown"
        ),
        ascension=summary.get("ascension") or r.get("ascension") or 0,
        act=act,
        floor=floor,
        max_energy=r.get("max_energy") or 0,
        hp=player.get("current_hp", r.get("current_hp", summary.get("current_hp") or 0)),
        max_hp=player.get("max_hp", r.get("max_hp", summary.get("max_hp") or 0)),
        gold=r.get("gold") or 0,
        deck=tuple(card(x) for x in r.get("deck", [])),
        relics=tuple(
            Item(
                id=norm_id(x.get("relic_id", "unknown")),
                name=x.get("name", ""),
                text=x.get("description") or "",
                amount=x.get("stack"),
                trigger_progress=PublicFacts.of(x.get("trigger_progress") or {}),
            )
            for x in r.get("relics", [])
        ),
        potions=tuple(
            Item(
                id=norm_id(x.get("potion_id") or "empty"),
                name=x.get("name") or "",
                text=x.get("description") or "",
                slot=x.get("slot_index", i),
                trigger_progress=PublicFacts.of(x.get("trigger_progress") or {}),
            )
            for i, x in enumerate(r.get("potions", []))
            if x.get("potion_id")
        ),
        boss=boss.get("name") or boss.get("encounter_id") or "",
        second_boss=second_boss.get("name") or second_boss.get("encounter_id") or "",
    )
    combat = None
    if c:
        piles = c.get("piles") or {}
        pile_values = {}
        for key in ("draw", "discard", "exhaust"):
            p = piles.get(key) or {}
            pile_values[key] = Pile(
                count=p.get("count", 0),
                cards=tuple(sorted((card(x) for x in p.get("stacks", [])), key=lambda x: (x.id, x.upgraded))),
            )
        combat = CombatState(
            turn_phase=c.get("player_turn_phase") or "unknown",
            energy=player.get("energy", 0),
            stars=player.get("stars", 0),
            focus=player.get("focus", 0),
            block=player.get("block", 0),
            turn=c.get("player_turn_number") or summary.get("turn") or 0,
            attacks_played=c.get("attacks_played_this_turn", 0),
            hand=tuple(card(x) for x in c.get("hand", [])),
            powers=powers(player.get("powers", [])),
            orbs=PublicFacts.of(
                [
                    {k: x[k] for k in ("orb_id", "passive_value", "evoke_value", "slot_index") if k in x}
                    for x in player.get("orbs", [])
                ]
            ),
            enemies=tuple(
                Enemy(
                    id=norm_id(x.get("enemy_id", "unknown")),
                    ref=x.get("enemy_ref") or str(x.get("index", i)),
                    name=x.get("name", ""),
                    hp=x.get("current_hp", 0),
                    max_hp=x.get("max_hp", 0),
                    block=x.get("block", 0),
                    alive=x.get("is_alive", True),
                    powers=powers(x.get("powers", [])),
                    intents=tuple(
                        Intent(
                            type=y.get("intent_type", "unknown"),
                            damage=y.get("damage"),
                            hits=y.get("hits"),
                            text=y.get("label") or "",
                        )
                        for y in x.get("intents", [])
                    ),
                )
                for i, x in enumerate(c.get("enemies", []))
            ),
            **pile_values,
        )
    map_state = None
    m = ctx.get("map")
    if m:
        reachable = {coord(x) for x in m.get("available_nodes", [])}
        map_state = MapState(
            current_node=coord(m.get("current_node")),
            nodes=tuple(
                MapNode(
                    id=coord(x),
                    type=x.get("node_type", "unknown"),
                    reachable=coord(x) in reachable,
                    children=tuple(coord(child) for child in x.get("children", [])),
                )
                for x in m.get("nodes") or m.get("available_nodes", [])
            ),
        )
    actions = []
    raw_choices = payload.get("choices", [])
    has_claimable_reward = scene == Scene.CARD_REWARD and any(
        x.get("kind") == "claim_reward" for x in raw_choices
    )
    potion_claim_has_open_slot = any(
        x.get("kind") == "claim_reward"
        and str((x.get("source") or {}).get("reward_type") or "").lower() == "potion"
        and (x.get("source") or {}).get("potion_slot_available") is True
        for x in raw_choices
    )
    for x in raw_choices:
        if "debug_only" in x.get("risk_tags", []) or "auto_flow" in x.get("risk_tags", []):
            continue
        if (x.get("params_schema") or {}).get("required"):
            continue  # v1 accepts fully bound actions only
        source, kind = x.get("source") or {}, x.get("kind", "")
        if kind == "discard_potion" and not (
            scene == Scene.CARD_REWARD
            and source.get("opens_reward_potion_slot") is True
            and not potion_claim_has_open_slot
        ):
            continue
        if (
            has_claimable_reward
            and kind == "proceed"
            and (source.get("skips_remaining_rewards") or x.get("action_id") == "reward:proceed")
        ):
            continue
        known = ActionKind(kind) if kind in ActionKind._value2member_map_ else ActionKind.OTHER
        label = x.get("label", "")
        description = x.get("summary") or ""
        if (
            scene == Scene.CARD_REWARD
            and kind == "claim_reward"
            and str(source.get("reward_type") or "").lower() == "card"
        ):
            known = ActionKind.OPEN_CARD_REWARD
            label = "View card reward choices"
            description = (
                "Open the card reward to inspect the offered cards. This action does not add a card; "
                "the next decision will show each candidate and a skip option."
            )
        if kind in {"select_deck_card", "toggle_card"} and selection_op == "exhaust":
            label = label.replace("Select ", "Exhaust ", 1)
            description = (
                "Choosing this card exhausts it without playing its card text. " + description
            ).strip()
        actions.append(
            Action(
                id=x["action_id"],
                decision_id=decision_id,
                kind=KINDS.get(kind, known),
                label=label,
                description=description,
                card_id=source.get("card_ref") or source.get("card_id"),
                target_id=source.get("target_entity_ref")
                or (str(source["target_index"]) if "target_index" in source else None),
                node_id=coord(source) or None,
                item_id=source.get("item_id") or source.get("relic_id") or source.get("potion_id"),
                option_id=str(source["option_index"]) if "option_index" in source else None,
                character=norm_id(source["character_id"]) if source.get("character_id") else None,
                ascension=source.get("ascension"),
                risk_tags=tuple(x.get("risk_tags", [])),
            )
        )
    choices, facts = public_options(ctx, scene)
    if scene == Scene.CARD_SELECTION and summary.get("energy") is not None:
        combat_summary_fields = (
            "turn",
            "current_hp",
            "max_hp",
            "block",
            "energy",
            "stars",
            "cards_played_this_turn",
            "incoming_damage",
            "player_powers",
            "enemy_powers",
        )
        combat_summary = {k: summary[k] for k in combat_summary_fields if summary.get(k) is not None}
        facts = PublicFacts.of(facts.unpack() | {"in_combat": True, "combat_summary": combat_summary})
    return GameState(
        scene=scene,
        run=run,
        combat=combat,
        map=map_state,
        choices=choices,
        legal_actions=tuple(actions),
        revision=revision,
        decision_id=decision_id,
        game_version=game_version,
        scene_facts=facts,
        victory=over.get("is_victory") if scene == Scene.GAME_OVER else None,
    )
