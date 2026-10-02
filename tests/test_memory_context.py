import json

import pytest

from spiremind.context.budget import ContextBudget, ContextOverflow
from spiremind.context.compiler import ContextCompiler
from spiremind.context.views import state_view
from spiremind.core.decision import StrategyUpdate
from spiremind.core.state import Card, Power, PublicFacts
from spiremind.knowledge.cards import CardDB, CardFact
from spiremind.knowledge.library import StrategyLibrary
from spiremind.memory.manager import MemoryContext, MemoryManager
from spiremind.memory.skills import SkillMemory
from spiremind.memory.storage_sqlite import MemoryStore
from spiremind.strategies.run import DeckAnalyzer


async def test_memory_cross_scene_restart_and_run_isolation(states, tmp_path):
    store = MemoryStore(tmp_path / "mem.sqlite")
    memory = MemoryManager(store)
    await memory.context_for(states[5], "run")
    await memory.update(
        states[5],
        states[5].legal_actions[0],
        states[6],
        StrategyUpdate(boss_plan="Need scaling", gold_policy="Reserve 100 for removal"),
    )
    memory.working.current_plan = [states[6].legal_actions[0]]
    memory.working.rejected_options = ["stale"]
    ctx = await memory.context_for(states[7], "map")
    assert ctx.run["boss_plan"] == "Need scaling"
    assert memory.working.current_plan == []
    assert "hp" not in memory.run.model_dump()
    restored = MemoryManager(store)
    assert (await restored.context_for(states[7], "combat")).run["boss_plan"] == "Need scaling"
    other = states[7].model_copy(update={"run": states[7].run.model_copy(update={"id": "new-run"})})
    assert (await restored.context_for(other, "run")).run["boss_plan"] == ""
    store.close()


async def test_working_memory_tracks_same_turn_hp_loss(states, tmp_path):
    old = next(state for state in states if state.combat and state.legal_actions)
    new = old.model_copy(
        update={
            "run": old.run.model_copy(update={"hp": old.run.hp - 3}),
            "revision": old.revision + 1,
            "decision_id": old.decision_id + ":after-loss",
        }
    )
    store = MemoryStore(tmp_path / "turn-loss.sqlite")
    memory = MemoryManager(store)
    await memory.context_for(old, "combat")

    await memory.update(old, old.legal_actions[0], new)
    context = await memory.context_for(new, "combat")

    assert context.working["lost_hp_this_turn"] is True
    next_turn = new.model_copy(
        update={
            "combat": new.combat.model_copy(update={"turn": new.combat.turn + 1}),
            "revision": new.revision + 1,
            "decision_id": new.decision_id + ":next-turn",
        }
    )
    assert (await memory.context_for(next_turn, "combat")).working["lost_hp_this_turn"] is False
    store.close()


async def test_context_views_budget_and_version_facts(states, tmp_path):
    store, db = MemoryStore(tmp_path / "m.sqlite"), CardDB(tmp_path / "c.sqlite")
    db.put(CardFact(card_id="strike", game_version="v0.1", source_version="old", text="STALE_FACT"))
    db.put(CardFact(card_id="strike", game_version="v0.111.0", source_version="live", text="EXACT_FACT"))
    memory = MemoryManager(store)
    compiler = ContextCompiler(StrategyLibrary(), db, ContextBudget())
    context = await compiler.build(
        states[4], "combat", await memory.context_for(states[4], "combat"), "fight"
    )
    assert "EXACT_FACT" not in context.user  # resolved live card text has priority
    unresolved = states[4].model_copy(
        update={
            "combat": states[4].combat.model_copy(
                update={"hand": tuple(c.model_copy(update={"text": ""}) for c in states[4].combat.hand)}
            )
        }
    )
    ctx_with_facts = await compiler.build(
        unresolved, "combat", await memory.context_for(unresolved, "combat"), "fight"
    )
    assert "EXACT_FACT" in ctx_with_facts.user
    assert "STALE_FACT" not in context.user
    assert "map" not in json.loads(context.user)["L1_current_state"]
    assert context.estimated_tokens <= 4000
    before = states[4].model_dump_json()
    with pytest.raises(ContextOverflow):
        await ContextCompiler(StrategyLibrary(), db, ContextBudget(1, 10)).build(
            states[4], "combat", await memory.context_for(states[4], "combat"), "fight"
        )
    assert states[4].model_dump_json() == before
    db.close()
    store.close()


def test_context_does_not_repeat_visible_card_text_in_legal_actions(states):
    combat = states[4]
    action = combat.legal_actions[0].model_copy(update={"description": "Deal 6 damage."})
    combat = combat.model_copy(update={"legal_actions": (action, *combat.legal_actions[1:])})

    view = state_view(combat, "combat")

    assert view["combat"]["hand"][0]["text"] == "Deal 6 damage."
    assert "description" not in view["legal_actions"][0]


def test_packages_mixed_archetypes_and_version(states):
    cards = tuple(
        Card(id=x)
        for x in (
            "dark_embrace",
            "feel_no_pain",
            "fiend_fire",
            "second_wind",
            "inflame",
            "demon_form",
            "sword_boomerang",
            "bash",
        )
    )
    state = states[4].model_copy(update={"run": states[4].run.model_copy(update={"deck": cards})})
    library = StrategyLibrary()
    assert len(library.packages) == 15
    active = library.retrieve(state, "combat")
    assert {p.archetype for _, p in active} >= {"exhaust", "strength"}
    assert len(active) <= 3
    assert library.retrieve(state.model_copy(update={"game_version": "v0.112.0"}), "combat") == []


def test_skill_matches_real_bridge_power_ids(states):
    state = states[4].model_copy(
        update={
            "run": states[4].run.model_copy(update={"character": "necrobinder"}),
            "combat": states[4].combat.model_copy(
                update={"hand": (Card(id="bury"),), "powers": (Power(id="lethality_power", amount=1),)}
            ),
        }
    )
    assert [s.name for s in SkillMemory().triggered(state)] == ["first_attack"]


def test_old_export_without_numbers_is_refreshed(tmp_path):
    db = CardDB(tmp_path / "cards.sqlite")
    old = {
        "card_id": "bash",
        "game_version": "v0.111.0",
        "source_version": "loaded_game_model:v0.111.0",
        "text": "Deal {Damage} damage",
        "upgraded": False,
    }
    db.db.execute("INSERT INTO cards VALUES (?,?,?,?)", ("v0.111.0", "bash", 0, json.dumps(old)))
    assert db.needs_sync("v0.111.0")
    db.put(CardFact.model_validate(old))
    assert not db.needs_sync("v0.111.0")
    db.close()


def test_starter_defends_are_not_a_block_strength_or_elite_ready(states):
    starter = (
        Card(id="strike", count=5),
        Card(id="defend", text="Gain 5 Block", count=4),
        Card(id="bash"),
    )
    state = states[4].model_copy(
        update={"run": states[4].run.model_copy(update={"deck": starter, "hp": states[4].run.max_hp})}
    )

    analysis = DeckAnalyzer(StrategyLibrary()).analyze(state)

    assert "block" not in analysis["strengths"]
    assert analysis["needs"]["block"] > 0.5
    assert analysis["elite_readiness"] < 0.5


def test_persistent_archetype_fit_does_not_change_with_current_hand(states):
    deck = (
        Card(id="dark_embrace"),
        Card(id="feel_no_pain"),
        Card(id="second_wind"),
        Card(id="fiend_fire"),
        Card(id="strike", count=6),
    )
    base = states[4].model_copy(update={"run": states[4].run.model_copy(update={"deck": deck})})
    signal = base.model_copy(
        update={"combat": base.combat.model_copy(update={"hand": (Card(id="dark_embrace"),)})}
    )
    no_signal = base.model_copy(
        update={"combat": base.combat.model_copy(update={"hand": (Card(id="strike"),)})}
    )
    library = StrategyLibrary()

    assert library.scores(signal) == library.scores(no_signal)
    signal_match = next(
        row for row in library.retrieve_detailed(signal, "combat") if row[2].archetype == "exhaust"
    )
    no_signal_match = next(
        row for row in library.retrieve_detailed(no_signal, "combat") if row[2].archetype == "exhaust"
    )
    assert signal_match[0] == no_signal_match[0]
    assert signal_match[1] > no_signal_match[1]


async def test_strategy_updates_are_scene_scoped_bounded_and_auditable(states, tmp_path):
    store = MemoryStore(tmp_path / "strategy.sqlite")
    memory = MemoryManager(store)
    await memory.context_for(states[4], "combat")

    rejected = await memory.update(
        states[4],
        states[4].legal_actions[0],
        states[4].model_copy(update={"revision": states[4].revision + 1}),
        StrategyUpdate(boss_plan="Invent a combat plan", gold_policy="Spend everything"),
    )
    assert rejected["applied"] == {}
    assert set(rejected["rejected"]) == {"boss_plan", "gold_policy"}
    assert memory.run.boss_plan == ""

    accepted = await memory.update(
        states[3],
        states[3].legal_actions[0],
        states[3].model_copy(update={"revision": states[3].revision + 1}),
        StrategyUpdate(route_preferences=["  prefer rest before elite  "], current_goal="  survive act 1  "),
    )
    assert accepted["applied"] == {
        "route_preferences": ["prefer rest before elite"],
        "current_goal": "survive act 1",
    }
    assert accepted["rejected"] == {}
    assert memory.last_strategy_update == accepted

    bounded = await memory.update(
        states[3],
        states[3].legal_actions[0],
        states[3].model_copy(update={"revision": states[3].revision + 2}),
        StrategyUpdate(
            boss_plan="Scale before the boss",
            potion_policy="Use a potion to prevent lethal",
            gold_policy="Reserve enough gold for removal",
        ),
    )
    assert set(bounded["applied"]) == {"boss_plan", "potion_policy"}
    assert bounded["rejected"] == {"gold_policy": "persistent_change_limit"}
    store.close()


async def test_finished_same_seed_starts_with_clean_memory(states, tmp_path):
    store = MemoryStore(tmp_path / "same-seed.sqlite")
    first = MemoryManager(store)
    await first.context_for(states[5], "run")
    first.run.boss_plan = "Old failed plan"
    first.run.key_decisions = ["Old decision"]
    await first.finish_run("death")

    restarted = MemoryManager(store)
    context = await restarted.context_for(states[2], "event")

    assert context.run["weaknesses"] == []
    assert restarted.run.boss_plan == ""
    assert restarted.run.key_decisions == []
    assert restarted.run.outcome is None
    store.close()


async def test_combat_card_selection_keeps_working_goal(states, tmp_path):
    store = MemoryStore(tmp_path / "selection.sqlite")
    memory = MemoryManager(store)
    combat = states[4]
    selection = states[8].model_copy(
        update={
            "run": combat.run,
            "scene_facts": PublicFacts.of({"in_combat": True, "operation": "exhaust"}),
        }
    )
    await memory.context_for(combat, "combat")
    memory.working.current_goal = "Preserve enough block"

    await memory.update(combat, combat.legal_actions[0], selection)

    assert memory.working.current_goal == "Preserve enough block"
    store.close()


async def test_context_snapshots_are_complete_deduplicated_and_retained(states, tmp_path):
    store = MemoryStore(tmp_path / "snapshots.sqlite", snapshot_limit=2)
    memory = MemoryManager(store)
    first = await memory.context_for(states[4], "combat")
    duplicate = await memory.context_for(states[4], "combat")
    assert first.snapshot_id == duplicate.snapshot_id
    snapshot = store.load_snapshot(first.snapshot_id)
    assert snapshot["schema_version"] == 2
    assert set(snapshot) == {"schema_version", "agent", "run", "working", "skills"}

    memory.working.current_goal = "goal two"
    second = await memory.context_for(states[4], "combat")
    memory.working.current_goal = "goal three"
    third = await memory.context_for(states[4], "combat")
    assert second.snapshot_id != third.snapshot_id
    assert store.load_snapshot(first.snapshot_id) is None
    assert store.db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 2
    store.close()


def test_card_db_is_upgrade_aware_batched_and_content_versioned(tmp_path):
    db = CardDB(tmp_path / "facts.sqlite")
    base = CardFact(card_id="bash", game_version="v0.111.0", source_version="live:a", text="Deal 8")
    upgraded = base.model_copy(update={"upgraded": True, "text": "Deal 10"})
    obsolete = base.model_copy(update={"card_id": "obsolete"})
    assert db.put_many([base, upgraded, obsolete]) == 3

    assert [fact.text for fact in db.lookup({("bash", True)}, "v0.111.0")] == ["Deal 10"]
    assert [fact.text for fact in db.lookup({"bash"}, "v0.111.0")] == ["Deal 8"]
    assert not db.needs_sync("v0.111.0", facts=[base, upgraded, obsolete])
    changed = upgraded.model_copy(update={"text": "Changed in same game version"})
    assert db.needs_sync("v0.111.0", facts=[base, changed, obsolete])

    db.put_many([base, changed])
    assert db.count("v0.111.0") == 2
    assert db.lookup({"obsolete"}, "v0.111.0") == []
    assert db.metadata("v0.111.0")["card_count"] == 2
    db.close()


async def test_context_uses_upgraded_fact_and_preserves_needs_when_trimming(states, tmp_path):
    store = MemoryStore(tmp_path / "context-memory.sqlite")
    db = CardDB(tmp_path / "context-cards.sqlite")
    db.put_many(
        [
            CardFact(
                card_id="defend",
                game_version="v0.111.0",
                source_version="live",
                text="BASE_FACT",
            ),
            CardFact(
                card_id="defend",
                game_version="v0.111.0",
                source_version="live",
                text="UPGRADED_FACT",
                upgraded=True,
            ),
        ]
    )
    reward = states[5].model_copy(
        update={
            "choices": (
                states[5].choices[0].model_copy(update={"card": Card(id="defend", upgraded=True, text="")}),
            )
        }
    )
    memory = MemoryContext(
        snapshot_id="manual",
        run={
            "needs": {"block": 0.8},
            "weaknesses": ["block"],
            "key_decisions": ["x" * 500 for _ in range(20)],
        },
        working={},
        skills=(),
    )
    context = await ContextCompiler(StrategyLibrary(), db, ContextBudget(1300, 1800)).build(
        reward, "run", memory, "choose reward"
    )
    payload = json.loads(context.user)

    assert payload["L4_card_facts"][0]["text"] == "UPGRADED_FACT"
    assert payload["L2_run_strategy"]["needs"] == {"block": 0.8}
    assert "BASE_FACT" not in context.user
    assert "L2_run_strategy" in context.dropped_layers  # lower-priority history was trimmed item-wise
    db.close()
    store.close()


async def test_deck_facts_ground_roles_and_reject_false_strength_plan(states, tmp_path):
    """A saved boss plan cannot turn the actual Breakthrough/Molten Fist into Strength cards."""
    db = CardDB(tmp_path / "cards.sqlite")
    version = states[3].game_version
    db.put_many(
        [
            CardFact(
                card_id="breakthrough",
                game_version=version,
                source_version="live",
                type="attack",
                cost=1,
                text="失去1点生命。对所有敌人造成9点伤害。",
                values=PublicFacts.of({"Damage": 9, "HpLoss": 1}),
            ),
            CardFact(
                card_id="molten_fist",
                game_version=version,
                source_version="live",
                type="attack",
                cost=1,
                text="造成10点伤害。将该敌人身上的易伤层数翻倍。",
                values=PublicFacts.of({"Damage": 10}),
            ),
            CardFact(
                card_id="dominate",
                game_version=version,
                source_version="live",
                type="skill",
                cost=1,
                text="给予易伤。敌人身上每有一层易伤，就获得1点力量。",
                values=PublicFacts.of({"StrengthPerVulnerable": 1}),
            ),
            CardFact(
                card_id="inflame",
                game_version=version,
                source_version="live",
                type="power",
                cost=1,
                text="获得[blue]2[/blue]点[gold]力量[/gold]。",
            ),
            CardFact(
                card_id="barricade",
                game_version=version,
                source_version="live",
                type="power",
                cost=3,
                text="格挡不再在你的回合开始时消失。",
            ),
        ]
    )
    deck = tuple(
        Card(id=card_id, name=name)
        for card_id, name in (
            ("breakthrough", "突破"),
            ("molten_fist", "熔融之拳"),
            ("dominate", "主宰"),
            ("inflame", "燃烧"),
            ("barricade", "壁垒"),
        )
    )
    state = states[3].model_copy(update={"run": states[3].run.model_copy(update={"deck": deck})})
    analysis = DeckAnalyzer(StrategyLibrary(), db).analyze(state)
    assert analysis["needs"]["aoe"] == 0
    assert analysis["needs"]["scaling"] == 0
    assert analysis["needs"]["block"] == 1  # Barricade retains block; it creates none.

    store = MemoryStore(tmp_path / "memory.sqlite")
    memory = MemoryManager(store, cards=db)
    context = await memory.context_for(state, "run")
    compiled = await ContextCompiler(StrategyLibrary(), db, ContextBudget(4000, 16000)).build(
        state, "run", context, "choose a boss plan"
    )
    deck_facts = {fact["id"]: fact for fact in json.loads(compiled.user)["L4_deck_facts"]}
    assert "力量" not in deck_facts["breakthrough"]["text"]
    assert deck_facts["dominate"]["values"]["StrengthPerVulnerable"] == 1

    wrong = await memory.update(
        state,
        state.legal_actions[0],
        state.model_copy(update={"revision": state.revision + 1}),
        StrategyUpdate(
            boss_plan="Use Barricade to retain block, build strength with Breakthrough and Molten Fist."
        ),
    )
    assert wrong["rejected"] == {"boss_plan": "unsupported_strength_source"}
    assert memory.run.boss_plan == ""

    sound = await memory.update(
        state,
        state.legal_actions[0],
        state.model_copy(update={"revision": state.revision + 2}),
        StrategyUpdate(boss_plan="Build strength with Dominate."),
    )
    assert sound["applied"] == {"boss_plan": "Build strength with Dominate."}
    markup = await memory.update(
        state,
        state.legal_actions[0],
        state.model_copy(update={"revision": state.revision + 3}),
        StrategyUpdate(boss_plan="Build strength with Inflame."),
    )
    assert markup["applied"] == {"boss_plan": "Build strength with Inflame."}

    memory.run.boss_plan = "Build strength with Breakthrough and Molten Fist."
    store.persist(memory.run)
    restored = MemoryManager(store, cards=db)
    assert (await restored.context_for(state, "combat")).run["boss_plan"] == ""
    assert store.load(state.run.id, state.game_version).boss_plan == ""
    db.close()
    store.close()
