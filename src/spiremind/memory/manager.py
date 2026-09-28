from dataclasses import dataclass
from typing import Any

from spiremind.core.actions import Action
from spiremind.core.decision import StrategyUpdate
from spiremind.core.enums import Scene
from spiremind.core.state import GameState

from .run import RunMemory
from .skills import Skill, SkillMemory
from .storage_sqlite import MemoryStore
from .working import WorkingMemory

VIEWS = {
    "combat": ("needs", "archetype_scores", "boss_plan", "potion_policy", "derived_metrics"),
    "run": (
        "needs",
        "strengths",
        "weaknesses",
        "archetype_scores",
        "boss_plan",
        "potion_policy",
        "gold_policy",
        "route_preferences",
        "elite_readiness",
        "derived_metrics",
        "key_decisions",
    ),
    "map": ("needs", "boss_plan", "potion_policy", "gold_policy", "route_preferences", "elite_readiness"),
    "event": ("needs", "potion_policy", "gold_policy", "weaknesses"),
}

RUN_STRATEGY_SCENES = {Scene.CARD_REWARD, Scene.SHOP, Scene.REST, Scene.MAP}
UPDATE_LIMITS = {
    "boss_plan": 240,
    "potion_policy": 180,
    "gold_policy": 180,
    "route_preferences": 5,
    "current_goal": 180,
}


@dataclass(frozen=True)
class MemoryContext:
    snapshot_id: str
    run: dict
    working: dict
    skills: tuple[Skill, ...]


class MemoryManager:
    def __init__(self, store: MemoryStore, skills: SkillMemory | None = None):
        self.store, self.skills = store, skills or SkillMemory()
        self.working = WorkingMemory()
        self.run: RunMemory | None = None
        self.last_scene: Scene | None = None
        self.last_strategy_update: dict[str, Any] | None = None

    def ensure_run(self, state: GameState):
        if not self.run or (self.run.run_id, self.run.game_version) != (state.run.id, state.game_version):
            restored = self.store.load(state.run.id, state.game_version)
            # The bridge run id is seed-like and can repeat. A terminal memory is
            # history, not the starting strategy for a fresh play of that seed.
            self.run = (
                RunMemory(run_id=state.run.id, game_version=state.game_version)
                if restored and restored.outcome is not None and not state.terminal
                else restored or RunMemory(run_id=state.run.id, game_version=state.game_version)
            )
            self.working = WorkingMemory()
            self.last_strategy_update = None
            self.store.persist(self.run)
        elif self.run.outcome is not None and not state.terminal:
            self.run = RunMemory(run_id=state.run.id, game_version=state.game_version)
            self.working = WorkingMemory()
            self.last_strategy_update = None
            self.store.persist(self.run)
        if self.working.revision != state.revision:
            self.working.invalidate_plan()
            self.working.revision = state.revision

    async def context_for(self, state: GameState, agent: str) -> MemoryContext:
        self.ensure_run(state)
        data = self.run.model_dump()
        run_view = {key: data[key] for key in VIEWS[agent]}
        # Revision is an internal invalidation token; it carries no strategy
        # meaning and would otherwise create a new snapshot every decision.
        working_view = self.working.model_dump(exclude={"current_plan", "revision"})
        skills = tuple(self.skills.triggered(state)) if agent == "combat" else ()
        self.store.persist(self.run)
        snapshot_id = self.store.snapshot(
            {
                "schema_version": 2,
                "agent": agent,
                "run": run_view,
                "working": working_view,
                "skills": [skill.model_dump(mode="json") for skill in skills],
            }
        )
        return MemoryContext(
            snapshot_id,
            run_view,
            working_view,
            skills,
        )

    def apply_analysis(self, state: GameState, analysis: dict):
        self.ensure_run(state)
        for key in (
            "archetype_scores",
            "needs",
            "strengths",
            "weaknesses",
            "elite_readiness",
            "derived_metrics",
        ):
            if key in analysis:
                setattr(self.run, key, analysis[key])

    @staticmethod
    def _clean_text(value: str) -> str:
        return " ".join(value.split())

    def _validated_update(self, state: GameState, proposal: StrategyUpdate) -> dict[str, Any]:
        proposed = proposal.model_dump(exclude_none=True)
        applied: dict[str, Any] = {}
        rejected: dict[str, str] = {}
        if state.scene not in RUN_STRATEGY_SCENES:
            return {
                "proposed": proposed,
                "applied": applied,
                "rejected": {key: "scene_not_run_or_map_strategy" for key in proposed},
            }

        persistent_changes = 0
        for key, raw_value in proposed.items():
            if key == "route_preferences" and state.scene != Scene.MAP:
                rejected[key] = "route_preferences_require_map_scene"
                continue
            if key == "boss_plan" and not state.run.boss:
                rejected[key] = "boss_plan_requires_visible_boss"
                continue
            if isinstance(raw_value, str):
                value: Any = self._clean_text(raw_value)
                if not value:
                    rejected[key] = "empty"
                    continue
                if len(value) > UPDATE_LIMITS[key]:
                    rejected[key] = "too_long"
                    continue
            else:
                value = [self._clean_text(item) for item in raw_value if self._clean_text(item)]
                if len(value) > UPDATE_LIMITS[key] or any(len(item) > 120 for item in value):
                    rejected[key] = "too_long"
                    continue
            current = self.working.current_goal if key == "current_goal" else getattr(self.run, key)
            if value == current:
                rejected[key] = "unchanged"
                continue
            if key != "current_goal":
                if persistent_changes >= 2:
                    rejected[key] = "persistent_change_limit"
                    continue
                persistent_changes += 1
            applied[key] = value
        return {"proposed": proposed, "applied": applied, "rejected": rejected}

    async def update(
        self,
        old_state: GameState,
        action: Action,
        new_state: GameState,
        proposal: StrategyUpdate | None = None,
        *,
        semantic_success: bool = True,
    ) -> dict[str, Any] | None:
        self.ensure_run(new_state)
        self.last_strategy_update = None
        if proposal:
            if semantic_success:
                self.last_strategy_update = self._validated_update(old_state, proposal)
            else:
                proposed = proposal.model_dump(exclude_none=True)
                self.last_strategy_update = {
                    "proposed": proposed,
                    "applied": {},
                    "rejected": {key: "action_not_semantically_verified" for key in proposed},
                }
            for key, value in self.last_strategy_update["applied"].items():
                if key == "current_goal":
                    self.working.current_goal = value
                else:
                    setattr(self.run, key, value)
        meaningful = {
            "choose_card",
            "skip",
            "choose_map_node",
            "buy_item",
            "remove_card",
            "upgrade_card",
            "choose_event_option",
            "rest",
            "choose_treasure_relic",
        }
        if semantic_success and old_state.scene != Scene.COMBAT and action.kind.value in meaningful:
            self.run.key_decisions = (
                self.run.key_decisions + [f"Floor {old_state.run.floor}: {action.label or action.kind.value}"]
            )[-12:]
        old_in_combat = old_state.scene == Scene.COMBAT or (
            old_state.scene == Scene.CARD_SELECTION
            and (old_state.combat is not None or old_state.scene_facts.unpack().get("in_combat") is True)
        )
        new_in_combat = new_state.scene == Scene.COMBAT or (
            new_state.scene == Scene.CARD_SELECTION
            and (new_state.combat is not None or new_state.scene_facts.unpack().get("in_combat") is True)
        )
        if old_in_combat and not new_in_combat:
            await self.clear_working()
        self.store.persist(self.run)
        return self.last_strategy_update

    async def clear_working(self):
        self.working = WorkingMemory()

    async def finish_run(self, outcome: str):
        if self.run:
            self.run.outcome = outcome
            self.store.persist(self.run)
        await self.clear_working()
