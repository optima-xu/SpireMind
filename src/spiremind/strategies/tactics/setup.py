"""Local ordering guarantees that do not require a complete combat simulator."""

from spiremind.core.enums import ActionKind, Scene
from spiremind.knowledge.library import version_matches

from .effects import (
    KNOWN_PLAYER_POWERS,
    KNOWN_TARGET_POWERS,
    attack_profile,
    end_turn_block,
    facts_of,
    incoming_from,
    remaining_card_plays,
    tainted_gain,
)

SAFE_RAGE_RELICS = {
    "burning_blood",
    "winged_boots",
    "gremlin_horn",
    "gorget",
    "toasty_mittens",
    "sparkling_rouge",
}
SAFE_RAGE_PLAYER_POWERS = KNOWN_PLAYER_POWERS | {"surrounded_power", "unmovable_power"}
SAFE_RAGE_ENEMY_POWERS = KNOWN_TARGET_POWERS | {
    "back_attack_left_power",
    "back_attack_right_power",
    "crab_rage_power",
}


def free_rage_action(state):
    """An untainted, free Rage can precede an available attack without spending energy.

    Opaque orientation/first-Block counters still disable the global search.
    This rule only orders a non-targeting setup card; it claims no exact survival
    outcome. Play caps, reactive enemy effects and unknown relics make it abstain.
    """
    combat = state.combat
    if (
        state.scene != Scene.COMBAT
        or not combat
        or state.run.hp <= 0
        or not version_matches("0.111.x", state.game_version)
        or remaining_card_plays(state) is not None
        or any(card.id == "normality" for card in combat.hand)
        or any(p.id not in SAFE_RAGE_PLAYER_POWERS for p in combat.powers)
        or any(p.id not in SAFE_RAGE_ENEMY_POWERS for e in combat.enemies if e.alive for p in e.powers)
        or any(relic.id not in SAFE_RAGE_RELICS for relic in state.run.relics)
        or sum(incoming_from(e) for e in combat.enemies) <= combat.block + end_turn_block(state)
    ):
        return None
    cards = {card.ref: card for card in combat.hand}
    plays = [a for a in state.legal_actions if a.kind == ActionKind.PLAY_CARD]
    attacks = [
        cards[a.card_id] for a in plays if a.card_id in cards and cards[a.card_id].type.lower() == "attack"
    ]
    if not any(
        attack_profile(card) is not None
        and tainted_gain(card) == 0
        and isinstance(card.cost, int)
        and 0 <= card.cost <= combat.energy
        and (facts_of(card.values).get("HpLoss", 0) or 0) < state.run.hp
        for card in attacks
    ):
        return None
    for action in plays:
        card = cards.get(action.card_id)
        if (
            card
            and card.id == "rage"
            and card.cost == 0
            and not action.target_id
            and tainted_gain(card) == 0
            and set(facts_of(card.values)) <= {"Power"}
            and (facts_of(card.values).get("Power", 0) or 0) > 0
        ):
            return action
    return None
