"""Build the version-pinned local enemy bestiary from public Spire Codex data."""

import argparse
import hashlib
import json
import re
from pathlib import Path

import httpx

VERSION = "v0.111.0"
BASE = f"https://raw.githubusercontent.com/ptrlrd/spire-codex/main/data-beta/{VERSION}"
URLS = {
    "monsters_eng": f"{BASE}/eng/monsters.json",
    "monsters_zhs": f"{BASE}/zhs/monsters.json",
    "powers_eng": f"{BASE}/eng/powers.json",
}

CURATED = {
    "BYGONE_EFFIGY": {
        "strategy": [
            "Slow increases the damage this enemy receives for every card played this turn; "
            "play weaker attacks first and the strongest multi-hit attack last.",
            "After Wake grants Strength, repeated Slashes become a damage race; use Block to "
            "cross a survival threshold, not as the default use of all energy.",
        ],
    },
    "THE_INSATIABLE": {
        "traits": [
            "Liquify Ground starts Sandpit: when its live countdown expires, the player is eaten and dies.",
        ],
        "strategy": [
            "When sandpit_power is at 1, play the bound frantic_escape card before "
            "spending its energy; never end the turn while that escape is playable.",
            "Preserve at least 1 energy and do not exhaust frantic_escape while the "
            "Sandpit countdown is active.",
            "Prepare Block or Weak for Lunging Bite and finish before repeated Strength buffs compound.",
        ],
    },
    "WATERFALL_GIANT": {
        "traits": ["Its special sequence includes About to Blow followed by Explode."],
        "strategy": [
            "Treat About to Blow as the final setup window: secure lethal or maximum "
            "mitigation before Explode."
        ],
    },
}


def normalized(value: str) -> str:
    return value.lower().replace(" ", "_")


def clean(value: str | None) -> str:
    return re.sub(r"\[[^]]+]", "", value or "").strip()


def fetch(client: httpx.Client, url: str) -> tuple[list[dict], str]:
    response = client.get(url)
    response.raise_for_status()
    return response.json(), hashlib.sha256(response.content).hexdigest()


def hp_text(monster: dict) -> str:
    def span(low, high) -> str:
        if low is None:
            return "not listed"
        return str(low) if high in (None, low) else f"{low}-{high}"

    normal = span(monster.get("min_hp"), monster.get("max_hp"))
    ascension = span(monster.get("min_hp_ascension"), monster.get("max_hp_ascension"))
    return f"HP {normal}; ascension HP {ascension}."


def compact_damage(damage: dict | None) -> dict | None:
    if not damage:
        return None
    return {
        "normal": damage.get("normal"),
        "ascension": damage.get("ascension"),
        "hits": damage.get("hit_count") or 1,
    }


def attack_text(move: dict) -> str:
    damage = compact_damage(move.get("damage")) or {}
    hits = damage.get("hits", 1)
    normal = str(damage.get("normal")) + (f"x{hits}" if hits > 1 else "")
    if damage.get("ascension") is None:
        return f"{move['name']} {normal}"
    ascension = str(damage["ascension"]) + (f"x{hits}" if hits > 1 else "")
    return f"{move['name']} {normal} (ascension {ascension})"


def move_detail(move: dict, power_names: dict[str, str]) -> str:
    parts = []
    if move.get("damage"):
        parts.append(attack_text(move))
    if move.get("block") is not None:
        parts.append(f"Block {move['block']}")
    if move.get("heal") is not None:
        parts.append(f"heal {move['heal']}")
    for power in move.get("powers") or []:
        name = power_names.get(power["power_id"], power["power_id"].replace("_", " ").title())
        amount = power.get("amount")
        target = power.get("target") or "target"
        parts.append(f"{name}{f' {amount:+d}' if isinstance(amount, int) else ''} to {target}")
    return ", ".join(parts) or move.get("intent") or "special"


def make_traits(monster: dict, powers: dict[str, dict], power_names: dict[str, str]) -> list[str]:
    acts = sorted(
        {encounter.get("act", "") for encounter in monster.get("encounters") or [] if encounter.get("act")}
    )
    traits = [f"Encounter: {', '.join(acts) or 'special/unknown'}; {hp_text(monster)}"]
    pattern = monster.get("attack_pattern") or {}
    if pattern.get("description"):
        traits.append(f"Pattern ({pattern.get('type', 'unknown')}): {pattern['description']}.")

    attacks = [move for move in monster.get("moves") or [] if move.get("damage")]
    if attacks:
        peak = max(
            attacks,
            key=lambda move: (
                (move["damage"].get("ascension") or move["damage"].get("normal") or 0)
                * (move["damage"].get("hit_count") or 1)
            ),
        )
        traits.append(f"Peak listed attack: {attack_text(peak)}.")

    innate = []
    for power in monster.get("innate_powers") or []:
        detail = powers.get(power["power_id"], {})
        description = clean(detail.get("description")).rstrip(".")
        amount = power.get("amount")
        name = detail.get("name") or power["power_id"].replace("_", " ").title()
        innate.append(f"{name}{f' {amount}' if amount is not None else ''}: {description}".rstrip(": "))
    if innate:
        traits.append("Innate: " + "; ".join(innate[:3]) + ".")

    utility = [
        f"{move['name']} ({move.get('intent', 'Unknown')}: {move_detail(move, power_names)})"
        for move in monster.get("moves") or []
        if not move.get("damage") or any(move.get(key) is not None for key in ("block", "heal", "powers"))
    ]
    if utility:
        traits.append("Utility/special moves: " + "; ".join(utility[:4]) + ".")
    return CURATED.get(monster["id"], {}).get("traits", []) + traits


def make_strategy(monster: dict) -> list[str]:
    curated = CURATED.get(monster["id"], {}).get("strategy")
    if curated:
        return curated

    moves = monster.get("moves") or []
    intents = " ".join(move.get("intent", "") for move in moves).lower()
    innate_ids = {power["power_id"] for power in monster.get("innate_powers") or []}
    tips = []
    if "ARTIFACT" in innate_ids:
        tips.append("Strip Artifact before relying on an important Weak, Vulnerable, or other debuff.")
    if "ADAPTABLE" in innate_ids:
        tips.append(
            "Budget damage and resources for its revive instead of treating the first lethal as the end."
        )
    if "BATTLEWORN_DUMMY_TIME_LIMIT" in innate_ids:
        tips.append("Defeat it before the visible Time Limit expires; this encounter is a damage race.")
    if "STOCK" in innate_ids:
        tips.append(
            "Its Stock can replace it after death, so budget damage for the listed replacement count."
        )
    if innate_ids & {"ASLEEP", "SLUMBER"}:
        tips.append(
            "Use safe sleeping turns to set up, then commit damage when ready for the wake-up pattern."
        )
    if "summon" in intents:
        tips.append(
            "Do not allow summons to multiply pressure; prioritize the summoner or the most dangerous add."
        )
    if "escape" in intents or "ESCAPE_ARTIST" in innate_ids:
        tips.append("Front-load damage if allowing its escape would lose rewards or prolong the encounter.")
    if "heal" in intents:
        tips.append("Save enough burst to outpace or finish through its listed healing turn.")
    if "debuff" in intents or "status" in intents:
        tips.append(
            "Keep draw and mitigation available for status/debuff turns instead of overcommitting setup."
        )

    attacks = [move for move in moves if move.get("damage")]
    multi = [move for move in attacks if (move["damage"].get("hit_count") or 1) > 1]
    if multi:
        tips.append(
            "Weak and effects that mitigate each hit are especially valuable against its multi-hit attacks."
        )
    if attacks:
        peak = max(
            attacks,
            key=lambda move: (
                (move["damage"].get("ascension") or move["damage"].get("normal") or 0)
                * (move["damage"].get("hit_count") or 1)
            ),
        )
        total = (peak["damage"].get("ascension") or peak["damage"].get("normal") or 0) * (
            peak["damage"].get("hit_count") or 1
        )
        if total >= 25:
            tips.append(
                f"Plan a dedicated Block, Weak, or lethal turn for {peak['name']}; it is the peak listed hit."
            )
    pattern_type = (monster.get("attack_pattern") or {}).get("type")
    if pattern_type in {"random", "conditional", "mixed"}:
        tips.append(f"Re-check the live intent every turn because its pattern is {pattern_type}.")
    elif pattern_type == "cycle" and attacks:
        tips.append("Use the listed cycle to prepare mitigation one turn before its dangerous attack.")
    if not tips:
        if attacks:
            tips.append(
                "Follow the live intent, cover incoming damage, then spend remaining "
                "energy on the fastest safe lethal line."
            )
        else:
            tips.append("This is a special encounter entity; follow its live intent and legal actions.")
    return list(dict.fromkeys(tips))[:3]


def compact_move(move: dict, translated: dict) -> dict:
    result = {
        "id": normalized(move["id"]),
        "name": move["name"],
        "name_zh": translated.get("name", ""),
        "intent": move.get("intent", "Unknown"),
    }
    damage = compact_damage(move.get("damage"))
    if damage:
        result["damage"] = damage
    for key in ("block", "heal"):
        if move.get(key) is not None:
            result[key] = move[key]
    if move.get("powers"):
        result["powers"] = [
            {
                key: normalized(value) if key == "power_id" else value
                for key, value in power.items()
                if value is not None
            }
            for power in move["powers"]
        ]
    return result


def build(monsters: list[dict], translated: list[dict], powers_list: list[dict], hashes: dict) -> dict:
    if len(monsters) != 115 or len(translated) != 115:
        raise ValueError("Expected exactly 115 v0.111.0 monsters in each language")
    zh_by_id = {monster["id"]: monster for monster in translated}
    if set(zh_by_id) != {monster["id"] for monster in monsters}:
        raise ValueError("English and Simplified Chinese enemy ids differ")
    powers = {power["id"]: power for power in powers_list}
    power_names = {key: value.get("name", key) for key, value in powers.items()}
    rows = []
    for monster in sorted(monsters, key=lambda row: row["id"]):
        zh = zh_by_id[monster["id"]]
        zh_moves = {move["id"]: move for move in zh.get("moves") or []}
        pattern = monster.get("attack_pattern") or {}
        zh_pattern = zh.get("attack_pattern") or {}
        innate = []
        for power in monster.get("innate_powers") or []:
            detail = powers.get(power["power_id"], {})
            innate.append(
                {
                    "id": normalized(power["power_id"]),
                    "name": detail.get("name", ""),
                    "description": clean(detail.get("description")),
                    "amount": power.get("amount"),
                    "amount_ascension": power.get("amount_ascension"),
                }
            )
        rows.append(
            {
                "id": normalized(monster["id"]),
                "source_id": monster["id"],
                "name": monster["name"],
                "name_zh": zh["name"],
                "type": monster["type"].lower(),
                "acts": sorted(
                    {
                        encounter["act"]
                        for encounter in monster.get("encounters") or []
                        if encounter.get("act")
                    }
                ),
                "hp": {
                    "min": monster.get("min_hp"),
                    "max": monster.get("max_hp"),
                    "ascension_min": monster.get("min_hp_ascension"),
                    "ascension_max": monster.get("max_hp_ascension"),
                },
                "moves": [
                    compact_move(move, zh_moves.get(move["id"], {})) for move in monster.get("moves") or []
                ],
                "pattern": (
                    {
                        "type": pattern.get("type", "unknown"),
                        "description": pattern.get("description", ""),
                        "description_zh": zh_pattern.get("description", ""),
                    }
                    if pattern
                    else {}
                ),
                "innate_powers": innate,
                "traits": make_traits(monster, powers, power_names),
                "strategy": make_strategy(monster),
            }
        )
    body = {
        "schema_version": 1,
        "game_version": VERSION,
        "source_version": f"spire-codex:{VERSION}",
        "enemy_count": len(rows),
        "source": {
            "name": "Spire Codex",
            "repository_url": "https://github.com/ptrlrd/spire-codex",
            "license_url": "https://github.com/ptrlrd/spire-codex/blob/main/LICENSE.md",
            "api_terms_url": "https://github.com/ptrlrd/spire-codex/blob/main/API_TERMS.md",
            "files": URLS,
            "file_sha256": hashes,
        },
        "enemies": rows,
    }
    canonical = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    body["source"]["content_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    return body


def markdown(catalog: dict) -> str:
    lines = [
        f"# Slay the Spire 2 敌人知识库（{catalog['game_version']}）",
        "",
        "本文件由 `scripts/build_enemy_knowledge.py` 从固定版本 Spire Codex 数据生成，"
        "并加入少量 SpireMind 战术摘要。",
        "实时意图、能力、生命和卡牌文字始终优先；版本不匹配时运行时不会注入这些资料。",
        "",
        f"共 {catalog['enemy_count']} 个条目。来源：[Spire Codex](https://github.com/ptrlrd/spire-codex)。",
        "",
    ]
    for enemy in catalog["enemies"]:
        acts = ", ".join(enemy["acts"]) or "特殊/未知"
        lines.extend(
            [
                f"## {enemy['name_zh']} / {enemy['name']} (`{enemy['id']}`)",
                "",
                f"- 类型：{enemy['type']}；区域：{acts}",
                "- 特性：" + " ".join(enemy["traits"]),
                "- 简略攻略：" + " ".join(enemy["strategy"]),
                "",
            ]
        )
    return "\n".join(lines)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "src" / "spiremind" / "knowledge" / "enemies" / f"{VERSION}.json",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=root / "docs" / f"ENEMY_BESTIARY_{VERSION}.md",
    )
    args = parser.parse_args()
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        monsters, eng_hash = fetch(client, URLS["monsters_eng"])
        translated, zhs_hash = fetch(client, URLS["monsters_zhs"])
        powers, powers_hash = fetch(client, URLS["powers_eng"])
    catalog = build(
        monsters,
        translated,
        powers,
        {"monsters_eng": eng_hash, "monsters_zhs": zhs_hash, "powers_eng": powers_hash},
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown.write_text(markdown(catalog), encoding="utf-8")
    print(f"wrote {catalog['enemy_count']} enemies to {args.output}")
    print(f"wrote human-readable bestiary to {args.markdown}")


if __name__ == "__main__":
    main()
