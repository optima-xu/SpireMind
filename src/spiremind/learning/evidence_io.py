"""Import deidentified, arithmetic-checkable training observations for replay."""

import json
import re

from spiremind.learning.experience import digest


def validate_episode(episode):
    before, after = episode["before"], episode["after"]
    if not re.fullmatch(r"[a-f0-9]{64}", episode["id"]) or episode["verified"] is not True:
        raise ValueError("invalid_verified_evidence")
    if episode["producer"] not in {"combat", "run", "map", "event"}:
        raise ValueError("invalid_evidence_owner")
    expected = {
        "hp_delta": after["run"]["hp"] - before["run"]["hp"],
        "gold_delta": after["run"]["gold"] - before["run"]["gold"],
        "deck_delta": after["run"]["deck_count"] - before["run"]["deck_count"],
    }
    if before.get("combat") and after.get("combat"):
        expected["block_delta"] = after["combat"]["block"] - before["combat"]["block"]
    if any(
        metric not in expected or type(value) is not int or expected[metric] != value
        for metric, value in episode["observations"].items()
    ):
        raise ValueError("evidence_arithmetic_mismatch")


def import_evidence(store, path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("partition") != "train":
        raise ValueError("unsupported_training_evidence_schema")
    # Validate the whole batch before changing persistent or cached partitions.
    for episode in data["episodes"]:
        validate_episode(episode)
    inserted = 0
    previous_split = store.history_split
    fingerprint = digest(data)
    try:
        with store.db:
            if data.get("split"):
                store.set_history_split(data["split"])
            for episode in data["episodes"]:
                inserted += store.insert(episode, commit=False)
            store.db.execute(
                "INSERT OR REPLACE INTO import_sources VALUES (?,?)",
                (
                    fingerprint,
                    json.dumps(dict(dataset_sha256=fingerprint, source="deidentified_training_observations")),
                ),
            )
    except BaseException:
        store.history_split = previous_split
        store.changed()
        raise
    store.changed()
    return dict(inserted=inserted, dataset_sha256=fingerprint, source="deidentified_training_observations")
