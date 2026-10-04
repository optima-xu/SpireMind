"""Bounded tactical learning from verified, revalidated public transitions.

Free-form model proposals never become executable rules. One seed may produce
a candidate; three independent training seeds are required for prompt admission.
"""

import json

from spiremind.core.state import GameState
from spiremind.strategies.tactics.setup import free_rage_action

from .experience import digest


def rage_evidence(episode):
    if episode.get("kind") != "play_card" or episode["conditions"].get("card") != "rage":
        return None
    try:
        old, new = (GameState.model_validate(episode[key]) for key in ("before", "after"))
    except ValueError:
        return None  # Compact scalar evidence has no tactical state contract.
    action = free_rage_action(old)
    if (
        not action
        or not new.combat
        or new.terminal
        or old.run.id != new.run.id
        or old.run.floor != new.run.floor
    ):
        return None
    if old.combat.turn != new.combat.turn:
        return None
    card = next(c for c in old.combat.hand if c.ref == action.card_id)
    if card.upgraded != episode["conditions"].get("upgraded", False):
        return None
    if episode.get("tactical_features", {}).get("card_ref", card.ref) != card.ref:
        return None
    expected = card.values.unpack()["Power"]
    gain = sum(p.amount or 0 for p in new.combat.powers if p.id == "rage_power") - sum(
        p.amount or 0 for p in old.combat.powers if p.id == "rage_power"
    )
    return dict(
        version=old.game_version,
        character=old.run.character,
        conditions={"card": "rage", "upgraded": card.upgraded, "rage_gain": expected},
        valid=gain == expected and old.run.hp == new.run.hp and old.combat.energy == new.combat.energy,
    )


def consolidate_tactics(store):
    groups = {}
    for (raw,) in store.db.execute(
        "SELECT payload FROM episodes WHERE partition_name='train' AND verified=1 AND agent='combat'"
    ):
        episode = json.loads(raw)
        if episode["conditions"].get("card") != "rage":
            continue
        facts = rage_evidence(episode)
        if facts is not None:
            identity = digest(
                ["rage_before_attack", facts["version"], facts["character"], facts["conditions"]]
            )
            groups.setdefault(identity, []).append((episode, facts))
    results = []
    for identity, evidence in groups.items():
        facts = evidence[0][1]
        seeds = sorted({item[0]["lineage"] for item in evidence})
        status = (
            "disabled"
            if not all(item[1]["valid"] for item in evidence)
            else "active"
            if len(seeds) >= 3
            else "candidate"
        )
        keys = [next(e["id"] for e, _ in evidence if e["lineage"] == seed) for seed in seeds][:30]
        value = dict(
            tactic="rage_before_attack",
            owner="combat",
            game_version=facts["version"],
            character=facts["character"],
            scene="combat",
            conditions=facts["conditions"],
            evidence_ids=keys,
            independent_seeds=len(seeds),
            instruction="Verified free Rage setup increases Rage without spending HP or energy. "
            "With a currently playable attack, place this setup before attacks to gain its extra Block. "
            "Revalidate play caps, current text and reactive effects; "
            "this is no whole-combat survival proof.",
        )
        payload = json.dumps(value, sort_keys=True)
        previous = store.db.execute(
            "SELECT revision,status,payload FROM tactical_lessons WHERE id=?", (identity,)
        ).fetchone()
        if previous and previous[1:] == (status, payload):
            results.append(dict(id=identity, revision=previous[0], status=status))
            continue
        revision = previous[0] + 1 if previous else 1
        with store.db:
            store.db.execute(
                "INSERT OR REPLACE INTO tactical_lessons VALUES (?,?,?,?)",
                (identity, revision, status, payload),
            )
            store.db.execute(
                "INSERT INTO tactical_history VALUES (?,?,?,?)", (identity, revision, status, payload)
            )
        store.changed()
        results.append(dict(id=identity, revision=revision, status=status))
    return results


def retrieve_tactics(store, state, agent):
    if agent != "combat" or free_rage_action(state) is None:
        return [], []
    action = free_rage_action(state)
    card = next(c for c in state.combat.hand if c.ref == action.card_id)
    result = []
    warnings = []
    for identity, status, raw in store.db.execute(
        "SELECT id,status,payload FROM tactical_lessons WHERE status IN ('active','disabled') ORDER BY id"
    ):
        value = json.loads(raw)
        if (
            value["game_version"] == state.game_version
            and value["character"] == state.run.character
            and value["conditions"]
            == {"card": "rage", "upgraded": card.upgraded, "rage_gain": card.values.unpack()["Power"]}
        ):
            if status == "disabled":
                warnings.append(
                    dict(tactic=value["tactic"], status="disabled", reason="verified_training_counterexample")
                )
                continue
            result.append(
                dict(
                    id=identity,
                    tactic=value["tactic"],
                    instruction=value["instruction"],
                    conditions=value["conditions"],
                    evidence_ids=value["evidence_ids"][:3],
                )
            )
    return result[:1], warnings[:1]


def check_tactical_counterexample(store, episode):
    facts = rage_evidence(episode)
    if facts is None or facts["valid"]:
        return
    identity = digest(["rage_before_attack", facts["version"], facts["character"], facts["conditions"]])
    previous = store.db.execute(
        "SELECT revision,status,payload FROM tactical_lessons WHERE id=?", (identity,)
    ).fetchone()
    if previous is None or previous[1] == "disabled":
        return
    revision, _, raw = previous
    value = json.loads(raw)
    value["counterexample_ids"] = [episode["id"]]
    payload = json.dumps(value, sort_keys=True)
    with store.db:
        store.db.execute(
            "UPDATE tactical_lessons SET revision=?,status='disabled',payload=? WHERE id=?",
            (revision + 1, payload, identity),
        )
        store.db.execute(
            "INSERT INTO tactical_history VALUES (?,?,'disabled',?)", (identity, revision + 1, payload)
        )
    store.changed()
