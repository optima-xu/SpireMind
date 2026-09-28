import json

from spiremind.context.budget import ContextBudget
from spiremind.context.compiler import ContextCompiler
from spiremind.core.state import Enemy
from spiremind.knowledge.cards import CardDB
from spiremind.knowledge.enemies import EnemyKnowledge
from spiremind.knowledge.library import StrategyLibrary
from spiremind.memory.manager import MemoryContext


def empty_memory() -> MemoryContext:
    return MemoryContext(snapshot_id="test", run={}, working={}, skills=())


def test_bundled_enemy_catalog_is_complete_and_versioned():
    knowledge = EnemyKnowledge()

    assert knowledge.catalog.game_version == "v0.111.0"
    assert knowledge.catalog.enemy_count == 115
    assert len({enemy.id for enemy in knowledge.catalog.enemies}) == 115
    assert {enemy.type for enemy in knowledge.catalog.enemies} == {"normal", "elite", "boss"}
    assert all(enemy.traits and enemy.strategy and enemy.moves for enemy in knowledge.catalog.enemies)
    assert knowledge.catalog.source["files"]["monsters_eng"].endswith("/data-beta/v0.111.0/eng/monsters.json")


def test_catalog_ids_match_observed_bridge_ids_and_unknown_is_safe():
    knowledge = EnemyKnowledge()
    observed = {
        "nibbit",
        "bygone_effigy",
        "decimillipede_segment_front",
        "decimillipede_segment_middle",
        "decimillipede_segment_back",
        "the_insatiable",
    }

    assert all(knowledge.get(enemy_id) for enemy_id in observed)
    unknown = Enemy(id="future_enemy", ref="e0", hp=10)
    assert knowledge.lookup((unknown,), "v0.111.0") == []
    assert knowledge.lookup((knowledge_enemy("the_insatiable"),), "v0.112.0") == []


def knowledge_enemy(enemy_id: str, *, alive: bool = True) -> Enemy:
    return Enemy(id=enemy_id, ref=f"enemy:{enemy_id}", name=enemy_id, hp=10, alive=alive)


async def test_combat_context_injects_only_current_living_enemy_guidance(states, tmp_path):
    db = CardDB(tmp_path / "cards.sqlite")
    base = states[4]
    combat = base.combat.model_copy(
        update={
            "enemies": (
                knowledge_enemy("the_insatiable"),
                knowledge_enemy("aeonglass", alive=False),
                knowledge_enemy("the_insatiable"),
            )
        }
    )
    state = base.model_copy(update={"combat": combat})

    context = await ContextCompiler(StrategyLibrary(), db, ContextBudget()).build(
        state, "combat", empty_memory(), "survive"
    )
    payload = json.loads(context.user)

    assert [row["id"] for row in payload["L4_enemy_knowledge"]] == ["the_insatiable"]
    assert "sandpit_power is at 1" in context.user
    assert "frantic_escape" in context.user
    assert all(row["id"] != "aeonglass" for row in payload["L4_enemy_knowledge"])
    assert "live powers, intents, HP" in context.system
    db.close()


async def test_enemy_guidance_is_combat_only_and_requires_matching_version(states, tmp_path):
    db = CardDB(tmp_path / "cards.sqlite")
    compiler = ContextCompiler(StrategyLibrary(), db, ContextBudget())
    base = states[4]
    combat = base.combat.model_copy(update={"enemies": (knowledge_enemy("the_insatiable"),)})
    wrong_version = base.model_copy(update={"combat": combat, "game_version": "v0.112.0"})

    mismatch = await compiler.build(wrong_version, "combat", empty_memory(), "fight")
    noncombat = await compiler.build(states[5], "run", empty_memory(), "choose")

    assert "L4_enemy_knowledge" not in json.loads(mismatch.user)
    assert "L4_enemy_knowledge" not in json.loads(noncombat.user)
    db.close()


async def test_context_reserves_space_for_all_current_enemy_types(states, tmp_path):
    db = CardDB(tmp_path / "cards.sqlite")
    base = states[4]
    ids = ("queen", "knowledge_demon", "frog_knight", "kin_priest", "ovicopter")
    state = base.model_copy(
        update={"combat": base.combat.model_copy(update={"enemies": tuple(map(knowledge_enemy, ids))})}
    )

    context = await ContextCompiler(StrategyLibrary(), db, ContextBudget(1, 16000)).build(
        state, "combat", empty_memory(), "fight"
    )
    payload = json.loads(context.user)

    assert [row["id"] for row in payload["L4_enemy_knowledge"]] == list(ids)
    assert all(len(row["traits"]) <= 3 and len(row["strategy"]) <= 2 for row in payload["L4_enemy_knowledge"])
    db.close()
