from collections import Counter

from spiremind.core.state import Card, GameState


def card_view(card: Card):
    return {
        k: v for k, v in card.model_dump(exclude={"values"}, exclude_defaults=True).items() if v is not None
    } | ({"values": card.values.unpack()} if card.values.unpack() else {})


def progress_view(value):
    result = value.model_dump(exclude={"trigger_progress"}, exclude_defaults=True)
    progress = value.trigger_progress.unpack()
    if progress:
        result["trigger_progress"] = progress
    return result


def grouped_card_view(cards: tuple[Card, ...]) -> list[dict]:
    grouped: dict[tuple, dict] = {}
    for card in cards:
        key = (card.id, card.name, card.type, card.upgraded)
        if key not in grouped:
            grouped[key] = {
                "id": card.id,
                **({"name": card.name} if card.name else {}),
                **({"type": card.type} if card.type else {}),
                **({"upgraded": True} if card.upgraded else {}),
                "count": 0,
            }
        grouped[key]["count"] += card.count
    for value in grouped.values():
        if value["count"] == 1:
            value.pop("count")
    return list(grouped.values())


def pile_card_view(cards: tuple[Card, ...]) -> list[dict]:
    counts = Counter()
    for card in cards:
        counts[(card.id, card.upgraded)] += card.count
    return [
        {"id": card_id, **({"upgraded": True} if upgraded else {}), **({"count": count} if count > 1 else {})}
        for (card_id, upgraded), count in sorted(counts.items())
    ]


def state_view(state: GameState, agent: str) -> dict:
    r = state.run
    result = dict(
        scene=state.scene,
        character=r.character,
        ascension=r.ascension,
        act=r.act,
        floor=r.floor,
        hp=r.hp,
        max_hp=r.max_hp,
        gold=r.gold,
        max_energy=r.max_energy,
        boss=r.boss,
        second_boss=r.second_boss,
        relics=[progress_view(x) for x in r.relics],
        potions=[progress_view(x) for x in r.potions],
    )
    if agent == "run":
        result["deck"] = grouped_card_view(r.deck)
    else:
        summary = Counter()
        for card in r.deck:
            summary[card.id + ("+" if card.upgraded else "")] += card.count
        result["deck_summary"] = dict(summary)
    if agent == "combat" and state.combat:
        c = state.combat
        result["combat"] = dict(
            turn_phase=c.turn_phase,
            energy=c.energy,
            stars=c.stars,
            focus=c.focus,
            block=c.block,
            turn=c.turn,
            attacks_played=c.attacks_played,
            hand=[card_view(x) for x in c.hand],
            enemies=[
                e.model_dump(exclude={"powers"}, exclude_defaults=True)
                | ({"powers": [progress_view(p) for p in e.powers]} if e.powers else {})
                for e in c.enemies
            ],
            powers=[progress_view(p) for p in c.powers],
            orbs=c.orbs.unpack(),
            piles={
                k: {
                    "count": getattr(c, k).count,
                    "unordered_cards": pile_card_view(getattr(c, k).cards),
                }
                for k in ("draw", "discard", "exhaust")
            },
        )
    if agent == "map" and state.map:
        result["map"] = state.map.model_dump()
    if state.choices:
        result["choices"] = [
            x.model_dump(exclude_defaults=True, exclude={"card"})
            | ({"card": card_view(x.card)} if x.card else {})
            for x in state.choices
        ]
    if state.scene_facts.unpack():
        result["scene_facts"] = state.scene_facts.unpack()
    visible_cards = [choice.card for choice in state.choices if choice.card]
    if state.combat:
        visible_cards.extend(state.combat.hand)
    visible_card_ids = {identity for card in visible_cards for identity in (card.id, card.ref) if identity}
    actions = []
    for action in state.legal_actions:
        value = action.model_dump(exclude={"decision_id"}, exclude_none=True, exclude_defaults=True)
        if action.card_id in visible_card_ids:
            # The resolved card text is already present once in hand/choices.
            value.pop("description", None)
        actions.append(value)
    result["legal_actions"] = actions
    return result
