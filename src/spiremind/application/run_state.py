import hashlib
import json
import re
from copy import copy, deepcopy
from typing import Any
from uuid import uuid4

from spiremind.adapters.storage.memory import MemoryStore
from spiremind.core.actions import Action
from spiremind.core.context import MemoryContext
from spiremind.core.decision import StrategyUpdate
from spiremind.core.enums import Scene
from spiremind.core.ports import CardCatalog
from spiremind.core.routing import owner_for
from spiremind.core.run import CombatFeedback, RunMemory
from spiremind.core.state import GameState
from spiremind.core.working import WorkingMemory
from spiremind.decision.planning.route import chosen_route_horizon
from spiremind.decision.planning.run import plan_run
from spiremind.knowledge.skills import SkillMemory

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
        "route_horizon",
        "elite_readiness",
        "derived_metrics",
        "key_decisions",
    ),
    "map": (
        "needs",
        "boss_plan",
        "potion_policy",
        "gold_policy",
        "route_preferences",
        "route_horizon",
        "elite_readiness",
    ),
    "event": ("needs", "potion_policy", "gold_policy", "weaknesses"),
}
VIEWS = {agent: (*fields, "intent", "combat_feedback") for agent, fields in VIEWS.items()}

RUN_STRATEGY_SCENES = {Scene.CARD_REWARD, Scene.SHOP, Scene.REST, Scene.MAP}
UPDATE_LIMITS = {
    "boss_plan": 240,
    "potion_policy": 180,
    "gold_policy": 180,
    "route_preferences": 5,
    "current_goal": 180,
}


class MemoryManager:
    def __init__(
        self, store: MemoryStore, skills: SkillMemory | None = None, cards: CardCatalog | None = None
    ):
        self.store, self.skills = store, skills or SkillMemory()
        self.cards = cards
        self.working = WorkingMemory()
        self.scopes: dict[tuple[str, str], WorkingMemory] = {}
        self.active_agent = "event"
        self.active_task = ""
        self.experience = None
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
            self.scopes = self.store.scopes(self.run.instance_id)
            self.working = WorkingMemory()
            self.last_strategy_update = None
        elif self.run.outcome is not None and not state.terminal:
            self.run = RunMemory(run_id=state.run.id, game_version=state.game_version)
            self.scopes = self.store.scopes(self.run.instance_id)
            self.working = WorkingMemory()
            self.last_strategy_update = None
        if self.run.boss_plan and self._unsupported_strength_source(state, self.run.boss_plan):
            self.run.boss_plan = ""
        horizon = self.run.route_horizon
        if horizon and (
            horizon.get("act") != state.run.act
            or state.run.floor > max(horizon.get("boss_game_floors") or [0])
        ):
            self.run.route_horizon = {}
        if state.combat and (
            self.working.combat_floor != state.run.floor or self.working.combat_turn != state.combat.turn
        ):
            self.working.combat_floor = state.run.floor
            self.working.combat_turn = state.combat.turn
            self.working.lost_hp_this_turn = False

    owner = staticmethod(owner_for)

    def _select(self, state, agent):
        self.ensure_run(state)
        task = (
            f"combat:{state.run.act}:{state.run.floor}"
            if agent == "combat"
            else f"map:{state.run.act}"
            if agent == "map"
            else f"{state.scene.value}:{state.run.act}:{state.run.floor}"
        )
        self.active_agent, self.active_task = agent, task
        self.working = self.scopes.setdefault((agent, task), WorkingMemory())
        self.ensure_run(state)
        return task

    @staticmethod
    def _resource_signature(state):
        value = (
            state.run.act,
            state.run.floor,
            state.run.hp,
            state.run.gold,
            tuple(c.model_dump_json() for c in state.run.deck),
            tuple(p.model_dump_json() for p in state.run.potions),
        )
        return hashlib.sha256(repr(value).encode()).hexdigest()[:20]

    def _handoff(self, state, agent):
        rows = self.store.db.execute(
            "SELECT payload FROM handoffs WHERE instance=? AND consumer=? ORDER BY rowid DESC LIMIT 8",
            (self.run.instance_id, agent),
        )
        for row in rows:
            packet = json.loads(row[0])
            if (
                packet["resource_signature"] == self._resource_signature(state)
                and packet.get("policy_version", 0) == self.run.policy_version
            ):
                return packet
        return None

    def context(self, state: GameState, agent: str) -> MemoryContext:
        self._select(state, agent)
        data = self.run.model_dump()
        run_view = {key: data[key] for key in VIEWS[agent]}
        working_view = self.working.model_dump()
        skills = tuple(self.skills.triggered(state)) if agent == "combat" else ()
        handoff = self._handoff(state, agent)
        experiences = self.experience.retrieve(state, agent) if self.experience else None
        snapshot_id = self.store.save_context(
            self.run,
            {
                "schema_version": 3,
                "agent": agent,
                "instance_id": self.run.instance_id,
                "policy_version": self.run.policy_version,
                "run": run_view,
                "working": working_view,
                "skills": [skill.model_dump(mode="json") for skill in skills],
                "handoff": handoff,
                "experiences": experiences,
            },
            scopes=self.scopes,
        )
        return MemoryContext(
            snapshot_id,
            run_view,
            working_view,
            skills,
            instance_id=self.run.instance_id,
            policy_version=self.run.policy_version,
            handoff=handoff,
            experiences=experiences,
        )

    async def context_for(self, state: GameState, agent: str) -> MemoryContext:
        return self.context(state, agent)

    def begin_run(self, state, *, transition_id=None):
        if transition_id and self.store.committed_transition(transition_id) is not None:
            self.run = self.store.load(state.run.id, state.game_version)
            if self.run is None:
                raise ValueError("Committed run initialization has no saved run")
            self.scopes = self.store.scopes(self.run.instance_id)
            self.working = WorkingMemory()
            return
        run = RunMemory(run_id=state.run.id, game_version=state.game_version)
        self.store.save_context(
            run,
            None,
            scopes={},
            transition_id=transition_id,
            audit={"producer": "lifecycle", "event": "begin_run"} if transition_id else None,
        )
        self.run, self.scopes, self.working = run, {}, WorkingMemory()

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
        self.run.intent = plan_run(state, analysis, self.run.combat_feedback)

    @staticmethod
    def _clean_text(value: str) -> str:
        return " ".join(value.split())

    def _unsupported_strength_source(self, state: GameState, plan: str) -> bool:
        """Reject an explicit named-card Strength claim contradicted by static facts."""
        if not self.cards:
            return False
        match = re.search(
            r"(?:build|gain|stack|generate)\s+strength\s+(?:with|via|using|from)\s+(.+)",
            plan,
            flags=re.IGNORECASE,
        )
        if not match:
            return False
        source_phrase = match.group(1).lower()
        named = []
        for card in state.run.deck:
            alias = card.id.replace("_", " ")
            if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", source_phrase) or (
                card.name and card.name in match.group(1)
            ):
                named.append(card)
        if not named:
            return False  # No named owned card means the source cannot be checked.
        facts = {
            (fact.card_id, fact.upgraded): fact
            for fact in self.cards.lookup({(card.id, card.upgraded) for card in named}, state.game_version)
        }
        for card in named:
            fact = facts.get((card.id, card.upgraded))
            if not fact:
                return False  # Unknown facts cannot establish a contradiction.
            values = fact.values.unpack()
            if any("strength" in key.lower() and value for key, value in values.items()):
                return False
            text = re.sub(r"\[[^\]]+\]", "", fact.text).lower()
            if re.search(r"(?:获得|gain).{0,24}(?:点力量|strength)", text):
                return False
        return True

    def _validated_update(self, state: GameState, proposal: StrategyUpdate, producer=None) -> dict[str, Any]:
        proposed = proposal.model_dump(exclude_none=True)
        applied: dict[str, Any] = {}
        rejected: dict[str, str] = {}
        producer = producer or self.owner(state)
        owners = {
            "boss_plan": "run",
            "potion_policy": "run",
            "gold_policy": "run",
            "route_preferences": "map",
        }
        persistent_changes = 0
        for key, raw_value in proposed.items():
            if key != "current_goal" and state.scene not in RUN_STRATEGY_SCENES:
                rejected[key] = "scene_not_run_or_map_strategy"
                continue
            if key in owners and owners[key] != producer:
                rejected[key] = "field_owned_by_" + owners[key]
                continue
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
                if key == "boss_plan" and self._unsupported_strength_source(state, value):
                    rejected[key] = "unsupported_strength_source"
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

    def _commit_transition(
        self,
        old_state: GameState,
        action: Action,
        new_state: GameState,
        proposal: StrategyUpdate | None = None,
        *,
        semantic_success: bool = True,
        producer: str | None = None,
        expected_policy_version: int | None = None,
        transition_id: str,
        expected_instance_id: str | None = None,
    ) -> dict[str, Any] | None:
        producer = producer or self.owner(old_state)
        self._select(old_state, producer)
        expected = self.run.policy_version if expected_policy_version is None else expected_policy_version
        if expected_instance_id and self.run.instance_id != expected_instance_id:
            raise ValueError("Pending transition belongs to another run instance")
        database_version = self.store.policy_version(self.run)
        self.ensure_run(new_state)
        if (
            semantic_success
            and old_state.combat
            and new_state.combat
            and old_state.run.floor == new_state.run.floor
            and old_state.combat.turn == new_state.combat.turn
            and new_state.run.hp < old_state.run.hp
        ):
            self.working.lost_hp_this_turn = True
        self.last_strategy_update = None
        if proposal:
            if producer != self.owner(old_state) or expected != self.store.policy_version(self.run):
                proposed = proposal.model_dump(exclude_none=True)
                self.run = self.store.load(self.run.run_id, self.run.game_version) or self.run
                self.last_strategy_update = {
                    "proposed": proposed,
                    "applied": {},
                    "rejected": {key: "stale_or_unauthorized_producer" for key in proposed},
                }
            elif semantic_success:
                self.last_strategy_update = self._validated_update(old_state, proposal, producer)
            else:
                proposed = proposal.model_dump(exclude_none=True)
                self.last_strategy_update = {
                    "proposed": proposed,
                    "applied": {},
                    "rejected": {key: "action_not_semantically_verified" for key in proposed},
                }
            if any(key != "current_goal" for key in self.last_strategy_update["applied"]):
                self.run.policy_version += 1
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
        map_transition_observed = (
            new_state.run.id == old_state.run.id
            and new_state.run.act == old_state.run.act
            and new_state.run.floor > old_state.run.floor
        )
        if old_state.scene == Scene.MAP and action.node_id and (semantic_success or map_transition_observed):
            self.run.route_horizon = chosen_route_horizon(old_state, action) or {}
        old_in_combat = old_state.scene == Scene.COMBAT or (
            old_state.scene == Scene.CARD_SELECTION
            and (old_state.combat is not None or old_state.scene_facts.unpack().get("in_combat") is True)
        )
        new_in_combat = new_state.scene == Scene.COMBAT or (
            new_state.scene == Scene.CARD_SELECTION
            and (new_state.combat is not None or new_state.scene_facts.unpack().get("in_combat") is True)
        )
        if semantic_success and old_in_combat:
            feedback = self.run.combat_feedback
            if (
                not feedback
                or (feedback[-1].act, feedback[-1].floor) != (old_state.run.act, old_state.run.floor)
                or feedback[-1].ended
            ):
                feedback.append(CombatFeedback(act=old_state.run.act, floor=old_state.run.floor))
            report = feedback[-1]
            report.hp_lost += max(0, old_state.run.hp - new_state.run.hp)
            report.hp_restored += max(0, new_state.run.hp - old_state.run.hp)
            report.potions_used += int(action.kind.value == "use_potion")
            report.observed_actions += 1
            if action.kind.value == "end_turn" and old_state.combat:
                report.unspent_energy += old_state.combat.energy
            report.ended = not new_in_combat
            self.run.combat_feedback = feedback[-5:]
        if old_in_combat and not new_in_combat:
            self.scopes = {key: value for key, value in self.scopes.items() if key[0] != "combat"}
            self.working = WorkingMemory()
        self.run.last_floor, self.run.last_act = new_state.run.floor, new_state.run.act
        self.run.last_character = new_state.run.character
        consumer = self.owner(new_state) if not new_state.terminal else "reflection"
        handoff = None
        if semantic_success and producer != consumer:
            summary = f"{producer}: {action.kind.value}; HP {old_state.run.hp}->{new_state.run.hp}; "
            summary += f"gold {old_state.run.gold}->{new_state.run.gold}; floor {new_state.run.floor}."
            if producer == "map" and self.run.route_horizon:
                horizon = self.run.route_horizon
                summary += f" Shops {horizon.get('possible_shop_game_floors', [])}; "
                summary += f"rests {horizon.get('possible_rest_game_floors', [])}; "
                summary += f"boss {horizon.get('boss_game_floors', [])}."
            handoff = dict(
                id=uuid4().hex,
                producer=producer,
                consumer=consumer,
                evidence_revision=new_state.revision,
                summary=summary[:250],
                resource_signature=self._resource_signature(new_state),
                upstream_policy_version=expected,
                policy_version=self.run.policy_version,
            )
        audit = dict(
            producer=producer,
            expected_policy_version=expected,
            evidence_revision=new_state.revision,
            update=self.last_strategy_update,
        )
        episode = None

        def write_evidence():
            self.experience.insert(episode, commit=False)
            if new_state.terminal or (old_in_combat and not new_in_combat):
                self.experience.enqueue(episode["lineage"], reason="scene_boundary", commit=False)

        if self.experience:
            lineage = hashlib.sha256(
                json.dumps(
                    [old_state.game_version, old_state.run.character, old_state.run.id],
                    sort_keys=True,
                    ensure_ascii=False,
                ).encode()
            ).hexdigest()
            episode = self.experience.episode(
                old_state,
                action,
                new_state,
                producer,
                consumer,
                semantic_success,
                lineage,
                handoff,
            )
            episode["instance_id"] = self.run.instance_id
            episode["id"] = hashlib.sha256((self.run.instance_id + episode["id"]).encode()).hexdigest()
            audit["episode_id"] = episode["id"]
        self.store.save_context(
            self.run,
            {"schema_version": 3, "audit": audit},
            scopes=self.scopes,
            audit=audit,
            handoff=handoff,
            evidence=write_evidence if episode else None,
            transition_id=transition_id,
            expected_policy_version=database_version,
        )
        self._committed_episode = episode
        return self.last_strategy_update

    def update_sync(self, old_state, action, new_state, proposal=None, **kwargs):
        # Copy the related state together so working/scopes retain their alias.
        draft = copy(self)
        fields = ("run", "scopes", "working", "active_agent", "active_task", "last_strategy_update")
        values = deepcopy({name: getattr(self, name) for name in fields})
        for name, value in values.items():
            setattr(draft, name, value)
        draft.ensure_run(old_state)
        transition_id = hashlib.sha256(
            json.dumps(
                [
                    kwargs.get("expected_instance_id") or draft.run.instance_id,
                    old_state.decision_id,
                    old_state.revision,
                    action.id,
                    new_state.decision_id,
                    new_state.revision,
                ]
            ).encode()
        ).hexdigest()
        committed = self.store.committed_transition(transition_id)
        if committed is not None:
            if self.experience and committed.get("episode_id"):
                row = self.store.db.execute(
                    "SELECT payload FROM episodes WHERE id=?", (committed["episode_id"],)
                ).fetchone()
                if row:
                    self.experience.check_contradictions(json.loads(row[0]))
            proposed = proposal.model_dump(exclude_none=True) if proposal else None
            previous = committed.get("update") or {}
            if proposed != previous.get("proposed"):
                return {
                    "proposed": proposed or {},
                    "applied": {},
                    "rejected": {key: "transition_already_committed" for key in (proposed or {})},
                }
            return committed.get("update")
        result = draft._commit_transition(
            old_state, action, new_state, proposal, transition_id=transition_id, **kwargs
        )
        for name in fields:
            setattr(self, name, getattr(draft, name))
        if draft._committed_episode:
            self.experience.changed()
            self.experience.check_contradictions(draft._committed_episode)
        return result

    async def update(self, *args, **kwargs):
        return self.update_sync(*args, **kwargs)

    async def clear_working(self):
        self.scopes.clear()
        self.working = WorkingMemory()

    async def finish_run(self, outcome: str):
        if self.run:
            finished = self.run.model_copy(update={"outcome": outcome})
            self.store.save_context(finished, None, scopes={})
            self.run = finished
        await self.clear_working()
