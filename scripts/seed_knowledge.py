"""Reproduce the initial qualitative knowledge curated from the supplied handoff.

No damage, energy, or patch-sensitive effect values are authored here.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1] / "src/spiremind/knowledge"
DATA = {
    "ironclad": [
        (
            "exhaust",
            ["dark_embrace", "feel_no_pain"],
            ["burning_pact", "second_wind", "stoke", "fiend_fire"],
            ["dark_embrace", "feel_no_pain"],
            "Protect essential setup before mass Exhaust; check hand space and remaining draw.",
            "Turn controlled Exhaust into deck compression and repeated draw/block payoff.",
            "Do not draft weak Exhaust cards without a payoff.",
        ),
        (
            "strength",
            ["inflame", "demon_form"],
            ["inflame", "demon_form", "bash", "dominate"],
            ["sword_boomerang", "heavy_blade", "twin_strike"],
            "Apply efficient Strength or Vulnerable setup before the attacks it improves.",
            "Invest in scaling for long fights; compare setup HP loss with immediate damage.",
            "Do not lose excessive HP setting up a fight that can end now.",
        ),
        (
            "block",
            ["barricade", "entrench"],
            ["entrench", "expect_a_fight", "shrug_it_off"],
            ["body_slam", "barricade"],
            "Check actual retained block and incoming intent before converting block.",
            "Build reliable block generation before taking block payoff cards.",
            "Do not assume block persists without the live mechanic.",
        ),
    ],
    "silent": [
        (
            "shiv",
            ["accuracy", "phantom_blades"],
            ["blade_dance", "cloak_and_dagger", "infinite_blades"],
            ["accuracy", "phantom_blades"],
            "Apply useful damage multipliers before spending Shivs.",
            "Balance Shiv generation, damage multipliers, and defense.",
            "Do not force a pure Shiv deck.",
        ),
        (
            "discard",
            ["tools_of_the_trade", "master_planner"],
            ["prepared", "acrobatics", "dagger_throw"],
            ["reflex", "tactician", "sneaky_strike", "master_planner"],
            "Read Sly and discard trigger text before selecting discard targets.",
            "Balance discard enablers and payoffs, and filter curses/statuses when profitable.",
            "Do not always discard the lowest nominal value card.",
        ),
        (
            "poison",
            ["noxious_fumes", "catalyst"],
            ["deadly_poison", "bouncing_flask", "noxious_fumes"],
            ["catalyst", "noxious_fumes"],
            "Account for poison timing and enemy powers using live facts.",
            "Use poison as scaling while maintaining enough defense to survive.",
            "Do not add slow poison at the expense of immediate survival.",
        ),
    ],
    "regent": [
        (
            "stars",
            ["seven_stars", "comet"],
            ["gather_light", "glow", "astral_pulse"],
            ["seven_stars", "comet", "decisions_decisions"],
            "Check Star reserves and next-turn needs before a large spender.",
            "Balance Star generators and spenders; preserve a useful burst reserve.",
            "Do not spend Stars solely because they are available.",
        ),
        (
            "big_cost",
            ["void_form"],
            ["void_form", "gather_light"],
            ["comet", "seven_stars"],
            "Read live Void Form text and remaining free slots before playing low-cost cards.",
            "Prioritize valuable high effective cost plays when free-play opportunities exist.",
            "Do not waste scarce free-play slots on low-value naturally free cards.",
        ),
        (
            "creation",
            ["pillar_of_creation", "quasar"],
            ["quasar", "spectrum_shift"],
            ["pillar_of_creation", "sovereign_blade"],
            "Use live text to confirm create-card trigger timing.",
            "Balance creation payoffs with resource and hand-space limits.",
            "Do not import numerical effects from another game patch.",
        ),
    ],
    "necrobinder": [
        (
            "osty",
            ["bodyguard", "unleash"],
            ["bodyguard", "summon"],
            ["unleash"],
            "Compare summon-then-spend with immediate use based on actual Osty resources.",
            "Treat Osty as both a damage and defensive resource.",
            "Do not ignore the HP cost of spending Osty.",
        ),
        (
            "doom",
            ["countdown"],
            ["countdown", "doom"],
            ["countdown"],
            "Check Doom trigger timing, enemy powers, and survival before assuming a delayed kill.",
            "Avoid excess damage on enemies already covered by a reliable Doom resolution.",
            "Do not treat Doom as immediate damage or skip necessary defense.",
        ),
        (
            "lethality",
            ["lethality", "bury"],
            ["lethality"],
            ["bury"],
            "If the live first-attack bonus is unused, avoid consuming it with a weak attack.",
            "Use non-attack setup before the best first attack when it is efficient.",
            "Do not infer first-attack availability from prior text; read attacks_played.",
        ),
    ],
    "defect": [
        (
            "orbs",
            ["defragment", "hotfix"],
            ["cold_snap", "ball_lightning", "darkness"],
            ["defragment", "hotfix", "dualcast"],
            "Apply useful Focus before the orb triggers it improves.",
            "Balance orb generation, Focus, and evoke tools with current defense needs.",
            "Do not assume Dark orb timing or values without live facts.",
        ),
        (
            "zero_cost",
            ["all_for_one"],
            ["hotfix", "turbo", "hologram"],
            ["all_for_one"],
            "Check discard contents and hand space before All for One.",
            "Use valuable zero-cost cards before retrieving them when this improves the turn.",
            "Do not value retrieval from deck density alone; inspect the current discard pile.",
        ),
        (
            "status",
            ["smokestack"],
            ["smokestack", "turbo"],
            ["smokestack"],
            "Read the actual status payoff and future draw cost before generating statuses.",
            "Treat status generation as beneficial only with functioning payoffs.",
            "Do not classify every status as either always good or always bad.",
        ),
    ],
}
for character, entries in DATA.items():
    packages = []
    for archetype, strong, enablers, payoffs, hard, heuristic, anti in entries:
        packages.append(
            dict(
                id=f"{character}_{archetype}",
                character=character,
                game_version="0.111.x",
                source="SpireMind handoff v1.1; qualitative guidance, corroborate mechanics with live facts",
                archetype=archetype,
                strong_signals=strong,
                enablers=enablers,
                payoffs=payoffs,
                goals=[archetype, "survive_and_improve_deck"],
                hard_rules=[hard],
                heuristics=[heuristic],
                anti_patterns=[anti],
            )
        )
    folder = ROOT / "strategies" / character
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "packages.yaml").write_text(yaml.safe_dump(packages, sort_keys=False), encoding="utf-8")

skills = [
    (
        "mass_exhaust_order",
        "ironclad",
        ["fiend_fire"],
        [],
        "Before mass Exhaust, check essential setup in hand; preserve lethal lines.",
    ),
    (
        "shiv_setup",
        "silent",
        ["accuracy", "shiv"],
        [],
        "If live Accuracy text boosts Shivs, compare setup then Shiv with immediate lethal; check energy.",
    ),
    (
        "first_attack",
        "necrobinder",
        ["bury"],
        ["lethality"],
        "Read attacks_played. When zero, compare first-attack candidates using live bonus text.",
    ),
    (
        "discard_retrieval",
        "defect",
        ["all_for_one"],
        [],
        "Count retrievable cards in the visible discard pile and available hand slots before retrieval.",
    ),
]
folder = ROOT / "skills"
folder.mkdir(exist_ok=True)
(folder / "tactics.yaml").write_text(
    yaml.safe_dump(
        [
            dict(
                name=name,
                character=char,
                game_version="0.111.x",
                required_hand=hand,
                required_powers=powers,
                instructions=[rule],
                confidence=0.9,
                confirmed=True,
                source="Curated handoff checklist; conditional on live facts; not a learned win-rate claim",
            )
            for name, char, hand, powers, rule in skills
        ],
        sort_keys=False,
    ),
    encoding="utf-8",
)
