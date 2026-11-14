"""Async AgentSession state machine orchestrating observe -> plan/decide -> validate -> execute -> trace."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from spiremind.agent.context import ContextCompiler, DeckAnalyzer, RunTracker, state_view
from spiremind.agent.mechanics.effects import verify_effect
from spiremind.agent.mechanics.planner import assess
from spiremind.agent.policies import (
    CombatStrategy,
    DecisionFrame,
    EventStrategy,
    MapStrategy,
    RunStrategy,
    SceneRouter,
    conservative_choice,
    lifecycle_decision,
)
from spiremind.bridge.client import MCPEnvironment
from spiremind.config import Config, GameConfig, redact_config
from spiremind.domain.decision import (
    ContextBudget,
    DecisionProvider,
    EnvironmentError,
    GameEnvironment,
    ProviderError,
    StaleDecision,
)
from spiremind.domain.safety import ActionValidator, NoProgress, ProgressGuard
from spiremind.domain.state import ActionKind, GameState, Scene, owner_for, resolve
from spiremind.knowledge.loader import EnemyKnowledge, StrategyLibrary
from spiremind.llm.client import OpenAIProvider
from spiremind.storage.trace_store import TraceWriter

SessionStatus = Literal["idle", "running", "paused", "stopping", "error"]
PolicyMode = Literal["model", "rules"]
RunMode = Literal["start", "attach"]


def validate_entry(state: GameState, mode: RunMode) -> None:
    """Validate that the observed game scene is legal for starting a new run or attaching."""
    has_saved = any(action.kind == ActionKind.CONTINUE_RUN for action in state.legal_actions)
    if mode == "start":
        if state.scene not in {Scene.MAIN_MENU, Scene.CHARACTER_SELECT}:
            raise ValueError("Start requires the game to be on the main menu")
        if state.scene == Scene.MAIN_MENU and has_saved:
            raise ValueError("Cannot start a new run over an existing saved run; attach instead")
        return
    if state.scene == Scene.MAIN_MENU and not has_saved:
        raise ValueError("No active or saved run to attach to")


class AgentSession:
    """Thread-safe async session controller backing both the Web UI and headless CLI."""

    def __init__(
        self,
        config: Config,
        *,
        env_factory: Callable[[Config], GameEnvironment] | None = None,
        provider_factory: Callable[[Config], DecisionProvider] | None = None,
    ) -> None:
        self.config = config
        self._env_factory = env_factory or self._default_env_factory
        self._provider_factory = provider_factory or self._default_provider_factory

        self.library = StrategyLibrary()
        self.enemies = EnemyKnowledge()
        self.analyzer = DeckAnalyzer(self.library)
        self.compiler = ContextCompiler(
            self.library,
            cards=None,
            budget=ContextBudget(config.runtime.context_tokens, config.runtime.max_context_tokens),
            enemies=self.enemies,
        )
        self.tracker = RunTracker()
        self.validator = ActionValidator()
        self.progress = ProgressGuard()

        self.status: SessionStatus = "idle"
        self.run_mode: RunMode = "attach"
        self.policy: PolicyMode = "model"
        self.attempt_id: str | None = None
        self.latest_state: GameState | None = None
        self.latest_decision: dict[str, Any] | None = None
        self.latest_assessment: dict[str, Any] | None = None
        self.recent_steps: deque[dict[str, Any]] = deque(maxlen=200)
        self.stats: dict[str, Any] = self._empty_stats()
        self.last_error: str | None = None

        self._op_lock = asyncio.Lock()
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._stop_requested = False
        self._task: asyncio.Task[dict[str, Any]] | None = None
        self._active_trace: TraceWriter | None = None
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._run_started_mono: float = 0.0

    @staticmethod
    def _empty_stats() -> dict[str, Any]:
        return {
            "steps": 0,
            "verified_actions": 0,
            "fallbacks": 0,
            "policy_rules": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        }

    @staticmethod
    def _default_env_factory(cfg: Config) -> GameEnvironment:
        return MCPEnvironment(cfg.game, Path(cfg.runtime.runs_dir) / ".pending.json")

    @staticmethod
    def _default_provider_factory(cfg: Config) -> DecisionProvider:
        return OpenAIProvider(cfg.model)

    def update_config(self, config: Config) -> None:
        if self.status in {"running", "paused", "stopping"}:
            raise RuntimeError("Cannot modify runtime settings while a run is active")
        self.config = config
        self.compiler = ContextCompiler(
            self.library,
            cards=None,
            budget=ContextBudget(config.runtime.context_tokens, config.runtime.max_context_tokens),
            enemies=self.enemies,
        )

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        packet = {"type": event_type, "data": data}
        stale: list[asyncio.Queue[dict[str, Any]]] = []
        for queue in list(self._subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(packet)
            except Exception:
                stale.append(queue)
        for queue in stale:
            self._subscribers.discard(queue)

    def _set_status(self, status: SessionStatus, error: str | None = None) -> None:
        self.status = status
        if error is not None:
            self.last_error = error
        elif status in {"running", "idle"}:
            self.last_error = None
        self._emit(
            "session_status",
            {
                "status": self.status,
                "run_mode": self.run_mode,
                "policy": self.policy,
                "attempt_id": self.attempt_id,
                "last_error": self.last_error,
            },
        )

    def _safe_state_view(self, state: GameState | None) -> dict[str, Any] | None:
        if state is None or state.scene in {
            Scene.MAIN_MENU,
            Scene.CHARACTER_SELECT,
            Scene.GAME_OVER,
            Scene.UNKNOWN,
        }:
            return None
        try:
            return state_view(state, owner_for(state))
        except Exception:
            return None

    def _assessment_for(self, state: GameState | None) -> dict[str, Any] | None:
        if state is None or state.scene != Scene.COMBAT or state.combat is None:
            return None
        try:
            return assess(state, lost_hp_this_turn=self.tracker.working.lost_hp_this_turn)
        except Exception:
            return None

    def snapshot(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "run_mode": self.run_mode,
            "policy": self.policy,
            "attempt_id": self.attempt_id,
            "state": self.latest_state.model_dump(mode="json") if self.latest_state else None,
            "state_view": self._safe_state_view(self.latest_state),
            "latest_decision": self.latest_decision,
            "combat_assessment": self.latest_assessment,
            "run_context": self.tracker.summary(),
            "recent_steps": list(self.recent_steps),
            "stats": dict(self.stats),
            "last_error": self.last_error,
        }

    def _router(self, provider: DecisionProvider | None) -> SceneRouter:
        return SceneRouter(
            CombatStrategy(self.compiler, provider, conservative_choice, self.config.strategy),
            RunStrategy(self.compiler, provider, conservative_choice),
            MapStrategy(self.compiler, provider, conservative_choice),
            EventStrategy(self.compiler, provider, conservative_choice),
        )

    async def observe_once(self) -> GameState:
        async with self._op_lock:
            env = self._env_factory(self.config)
            try:
                state = await env.observe()
            finally:
                await _close_quietly(env)
            self.latest_state = state
            self.latest_assessment = self._assessment_for(state)
            if not state.terminal and state.scene not in {
                Scene.MAIN_MENU,
                Scene.CHARACTER_SELECT,
                Scene.UNKNOWN,
            }:
                self.tracker.apply_analysis(state, self.analyzer.analyze(state))
            self._emit(
                "state_updated",
                {
                    "state": state.model_dump(mode="json"),
                    "state_view": self._safe_state_view(state),
                    "combat_assessment": self.latest_assessment,
                    "run_context": self.tracker.summary(),
                },
            )
            return state

    async def step_once(
        self,
        policy: PolicyMode | None = None,
        *,
        env: GameEnvironment | None = None,
        provider: DecisionProvider | None = None,
    ) -> dict[str, Any]:
        if self.status == "running":
            raise RuntimeError("Pause or stop the continuous loop before stepping manually")
        chosen_policy = policy or self.policy
        self.policy = chosen_policy
        async with self._op_lock:
            owned_env = env is None
            owned_provider = provider is None and chosen_policy == "model"
            active_env = env or self._env_factory(self.config)
            active_provider = (
                provider
                if provider is not None
                else (self._provider_factory(self.config) if chosen_policy == "model" else None)
            )
            if self._active_trace is None:
                self._reset_run_buffers()
                self._active_trace = TraceWriter(
                    self.config.runtime.runs_dir,
                    f"interactive_{chosen_policy}",
                    redact_config(self.config),
                )
                self.attempt_id = self._active_trace.attempt_id
            try:
                res = await self._perform_step(active_env, active_provider, self._active_trace, self.run_mode)
                if res.get("terminal") and self._active_trace is not None:
                    last_run = self.latest_state.run if self.latest_state else None
                    summary = {
                        "outcome": res.get("outcome", "complete"),
                        "complete": True,
                        "steps": self.stats["steps"],
                        "verified_actions": self.stats["verified_actions"],
                        "fallbacks": self.stats["fallbacks"],
                        "policy_rules": self.stats["policy_rules"],
                        "input_tokens": self.stats["input_tokens"],
                        "output_tokens": self.stats["output_tokens"],
                        "character": last_run.character if last_run else self.config.game.character,
                        "ascension": last_run.ascension if last_run else self.config.game.ascension,
                        "game_version": self.latest_state.game_version if self.latest_state else None,
                        "floor": last_run.floor if last_run else 0,
                        "hp": last_run.hp if last_run else 0,
                        "max_hp": last_run.max_hp if last_run else 0,
                        "error": self.last_error,
                    }
                    self._active_trace.finish(summary)
                    self._emit(
                        "run_finished", {"attempt_id": self._active_trace.attempt_id, "summary": summary}
                    )
                    self._active_trace = None
                return res
            finally:
                if owned_provider:
                    await _close_quietly(active_provider)
                if owned_env:
                    await _close_quietly(active_env)

    async def start_run(
        self,
        *,
        character: str | None = None,
        ascension: int | None = None,
        policy: PolicyMode = "model",
        game_override: GameConfig | None = None,
    ) -> dict[str, Any]:
        return await self._launch(
            run_mode="start",
            policy=policy,
            character=character,
            ascension=ascension,
            game_override=game_override,
        )

    async def attach_run(
        self,
        *,
        policy: PolicyMode = "model",
    ) -> dict[str, Any]:
        return await self._launch(run_mode="attach", policy=policy)

    async def _launch(
        self,
        *,
        run_mode: RunMode,
        policy: PolicyMode,
        character: str | None = None,
        ascension: int | None = None,
        game_override: GameConfig | None = None,
    ) -> dict[str, Any]:
        if self.status in {"running", "paused", "stopping"}:
            raise RuntimeError("A session is already active; stop it first")

        if character is not None or ascension is not None or game_override is not None:
            game_cfg = game_override or self.config.game.model_copy(
                update={
                    k: v for k, v in {"character": character, "ascension": ascension}.items() if v is not None
                }
            )
            self.config = self.config.model_copy(update={"game": game_cfg})

        env = self._env_factory(self.config)
        try:
            initial_state = await env.observe()
            validate_entry(initial_state, run_mode)
        finally:
            await _close_quietly(env)

        self._reset_run_buffers()
        self.run_mode = run_mode
        self.policy = policy
        self.latest_state = initial_state
        self.latest_assessment = self._assessment_for(initial_state)
        self._stop_requested = False
        self._pause_event.set()
        self._run_started_mono = time.monotonic()

        trace = TraceWriter(self.config.runtime.runs_dir, f"ui_{policy}", redact_config(self.config))
        self._active_trace = trace
        self.attempt_id = trace.attempt_id
        self._set_status("running")

        self._task = asyncio.create_task(
            self._run_loop(trace, run_mode, policy), name=f"session-{trace.attempt_id}"
        )
        return {
            "attempt_id": self.attempt_id,
            "status": self.status,
            "policy": self.policy,
            "run_mode": run_mode,
        }

    def pause(self) -> dict[str, Any]:
        if self.status != "running":
            return {"status": self.status, "attempt_id": self.attempt_id}
        self._pause_event.clear()
        self._set_status("paused")
        return {"status": self.status, "attempt_id": self.attempt_id}

    def resume(self) -> dict[str, Any]:
        if self.status != "paused":
            return {"status": self.status, "attempt_id": self.attempt_id}
        self._pause_event.set()
        self._set_status("running")
        return {"status": self.status, "attempt_id": self.attempt_id}

    async def stop(self) -> dict[str, Any]:
        if self._task is None or self._task.done():
            self._stop_requested = False
            self._pause_event.set()
            if self.status != "idle":
                self._set_status("idle")
            return {"status": self.status, "attempt_id": self.attempt_id}

        self._stop_requested = True
        self._pause_event.set()
        self._set_status("stopping")
        try:
            await asyncio.wait_for(self._task, timeout=15.0)
        except TimeoutError:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        return {"status": self.status, "attempt_id": self.attempt_id}

    async def run_until_done(
        self,
        *,
        run_mode: RunMode = "attach",
        policy: PolicyMode = "rules",
        env: GameEnvironment | None = None,
        provider: DecisionProvider | None = None,
        validate_initial: bool = False,
    ) -> dict[str, Any]:
        """Run a full session in-process cleanly (used by `spiremind play` CLI and offline tests)."""
        if env is not None:
            initial = await env.observe()
            if validate_initial:
                validate_entry(initial, run_mode)
            self._reset_run_buffers()
            self.run_mode = run_mode
            self.policy = policy
            self.latest_state = initial
            self._stop_requested = False
            self._pause_event.set()
            self._run_started_mono = time.monotonic()
            trace = TraceWriter(self.config.runtime.runs_dir, f"play_{policy}", redact_config(self.config))
            self._active_trace = trace
            self.attempt_id = trace.attempt_id
            self._set_status("running")
            return await self._run_loop(trace, run_mode, policy, env_override=env, provider_override=provider)

        await self._launch(run_mode=run_mode, policy=policy)
        assert self._task is not None
        return await self._task

    def _reset_run_buffers(self) -> None:
        self.tracker.reset()
        self.progress = ProgressGuard()
        self.latest_decision = None
        self.latest_assessment = None
        self.recent_steps.clear()
        self.stats = self._empty_stats()
        self.last_error = None

    async def _run_loop(
        self,
        trace: TraceWriter,
        run_mode: RunMode,
        policy: PolicyMode,
        *,
        env_override: GameEnvironment | None = None,
        provider_override: DecisionProvider | None = None,
    ) -> dict[str, Any]:
        env = env_override or self._env_factory(self.config)
        provider = (
            provider_override
            if provider_override is not None
            else (self._provider_factory(self.config) if policy == "model" else None)
        )
        outcome = "stopped"
        bridge_fail_started: float | None = None

        summary: dict[str, Any] = {}
        try:
            while not self._stop_requested:
                await self._pause_event.wait()
                if self._stop_requested:
                    break

                if self.stats["steps"] >= self.config.runtime.max_steps:
                    outcome = "max_steps"
                    break
                if (
                    self.config.runtime.max_total_tokens is not None
                    and (self.stats["input_tokens"] + self.stats["output_tokens"])
                    >= self.config.runtime.max_total_tokens
                ):
                    outcome = "token_budget"
                    break
                if (
                    self.config.runtime.max_seconds is not None
                    and (time.monotonic() - self._run_started_mono) >= self.config.runtime.max_seconds
                ):
                    outcome = "time_budget"
                    break

                try:
                    async with self._op_lock:
                        result = await self._perform_step(env, provider, trace, run_mode)
                    bridge_fail_started = None
                    if result.get("terminal"):
                        outcome = result.get("outcome", "complete")
                        break
                except (EnvironmentError, StaleDecision) as exc:
                    now = time.monotonic()
                    if bridge_fail_started is None:
                        bridge_fail_started = now
                    elapsed = now - bridge_fail_started
                    if elapsed > self.config.runtime.error_retry_seconds:
                        outcome = "error"
                        self._set_status("error", str(exc))
                        self._emit("error", {"message": str(exc), "stage": "bridge"})
                        break
                    await asyncio.sleep(min(1.0, max(0.2, self.config.runtime.step_delay_seconds)))
                    continue
                except (ProviderError, NoProgress, ValueError) as exc:
                    outcome = "error"
                    self._set_status("error", str(exc))
                    self._emit("error", {"message": str(exc), "stage": "decision"})
                    break

                if self.config.runtime.step_delay_seconds > 0 and not self._stop_requested:
                    await asyncio.sleep(self.config.runtime.step_delay_seconds)

        except asyncio.CancelledError:
            outcome = "cancelled"
        finally:
            if provider_override is None:
                await _close_quietly(provider)
            if env_override is None:
                await _close_quietly(env)

            last_run = self.latest_state.run if self.latest_state else None
            summary = {
                "outcome": outcome,
                "complete": outcome in {"victory", "death"},
                "steps": self.stats["steps"],
                "verified_actions": self.stats["verified_actions"],
                "fallbacks": self.stats["fallbacks"],
                "policy_rules": self.stats["policy_rules"],
                "input_tokens": self.stats["input_tokens"],
                "output_tokens": self.stats["output_tokens"],
                "character": last_run.character if last_run else self.config.game.character,
                "ascension": last_run.ascension if last_run else self.config.game.ascension,
                "game_version": self.latest_state.game_version if self.latest_state else None,
                "floor": last_run.floor if last_run else 0,
                "hp": last_run.hp if last_run else 0,
                "max_hp": last_run.max_hp if last_run else 0,
                "error": self.last_error,
            }
            trace.finish(summary)
            self._emit("run_finished", {"attempt_id": trace.attempt_id, "summary": summary})
            if self.status != "error":
                self._set_status("idle")
        return summary

    async def _perform_step(
        self,
        env: GameEnvironment,
        provider: DecisionProvider | None,
        trace: TraceWriter,
        run_mode: RunMode,
    ) -> dict[str, Any]:
        before = await env.observe()
        self.latest_state = before
        if before.terminal:
            outcome = "victory" if before.victory else "death"
            self.latest_assessment = None
            self._emit(
                "state_updated",
                {
                    "state": before.model_dump(mode="json"),
                    "state_view": None,
                    "combat_assessment": None,
                    "run_context": self.tracker.summary(),
                },
            )
            return {"terminal": True, "outcome": outcome}

        t0 = time.perf_counter()
        policy_state = self.progress.policy_state(before)
        assessment: dict[str, Any] | None = None
        excluded: dict[str, str] = {}
        frame: DecisionFrame | None = None
        strategy_name = "lifecycle"

        if policy_state.scene in {Scene.MAIN_MENU, Scene.CHARACTER_SELECT}:
            decision = lifecycle_decision(policy_state, self.config.game, new_run=(run_mode == "start"))
            if decision is None:
                raise ValueError(f"No lifecycle action available in scene {policy_state.scene.value}")
        else:
            strategy_name = owner_for(policy_state)
            self.tracker.apply_analysis(policy_state, self.analyzer.analyze(policy_state))
            mem_ctx = await self.tracker.context_for(policy_state, strategy_name)
            frame = DecisionFrame.prepare(policy_state, mem_ctx)
            excluded = dict(frame.excluded)
            assessment = frame.memory.assessment if frame.memory else None
            self.latest_assessment = assessment
            router = self._router(provider)
            strategy = router.route(frame.policy_state)
            decision = await strategy.decide(frame.policy_state, frame.memory)
            if decision.provider_error and not self.config.runtime.allow_fallback:
                raise ProviderError(decision.provider_error)
            frame.validate(decision)

        self.validator.validate(before, decision.action)
        receipt = await env.execute(decision.action)
        after = await env.observe()
        verify_ok = bool(await resolve(env.verify(before, decision.action, after)))
        if self.config.runtime.verify_effects and verify_ok:
            _ = verify_effect(before, decision.action, after)

        if verify_ok:
            self.progress.confirmed(before, decision.action, after)
        audit = self.tracker.update(
            before,
            decision.action,
            after,
            decision.strategy_update,
            semantic_success=verify_ok,
            producer=strategy_name if strategy_name != "lifecycle" else "event",
            analyzer=self.analyzer,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)

        self.stats["steps"] += 1
        if verify_ok:
            self.stats["verified_actions"] += 1
        if decision.fallback:
            self.stats["fallbacks"] += 1
        if decision.policy_rule:
            self.stats["policy_rules"] += 1
        self.stats["input_tokens"] += decision.input_tokens
        self.stats["output_tokens"] += decision.output_tokens

        decision_payload = {
            "action": decision.action.model_dump(mode="json"),
            "reason": decision.reason,
            "confidence": decision.confidence,
            "strategy_name": strategy_name,
            "policy_rule": decision.policy_rule,
            "model_name": decision.model_name,
            "calculations": decision.calculations,
            "fallback": decision.fallback,
            "provider_error": decision.provider_error,
            "strategy_update": decision.strategy_update.model_dump(mode="json")
            if decision.strategy_update
            else None,
            "strategy_update_audit": audit,
            "excluded": excluded,
            "action_evaluation": decision.action_evaluation,
        }
        self.latest_decision = decision_payload

        run_summary = self.tracker.summary()
        step_record = {
            "step": self.stats["steps"],
            "timestamp": datetime.now(UTC).isoformat(),
            "decision_id": before.decision_id,
            "revision": before.revision,
            "scene": before.scene.value,
            "state": before.model_dump(mode="json"),
            "decision": decision_payload,
            "combat_assessment": assessment,
            "run_context": run_summary,
            "receipt": receipt.model_dump(mode="json"),
            "verify_ok": verify_ok,
            "latency_ms": latency_ms,
            "input_tokens": decision.input_tokens,
            "output_tokens": decision.output_tokens,
            "error": decision.provider_error,
        }
        trace.record_step(step_record)
        self.recent_steps.append(step_record)

        self.latest_state = after
        self.latest_assessment = self._assessment_for(after)

        self._emit(
            "decision_made",
            {
                "step": self.stats["steps"],
                "scene": before.scene.value,
                "decision": decision_payload,
                "receipt": receipt.model_dump(mode="json"),
                "verify_ok": verify_ok,
                "latency_ms": latency_ms,
                "stats": dict(self.stats),
                "step_record": step_record,
            },
        )
        self._emit(
            "state_updated",
            {
                "state": after.model_dump(mode="json"),
                "state_view": self._safe_state_view(after),
                "combat_assessment": self.latest_assessment,
                "run_context": run_summary,
            },
        )
        if after.terminal:
            return {"terminal": True, "outcome": "victory" if after.victory else "death"}
        return {"terminal": False, "step": self.stats["steps"], "verify_ok": verify_ok}


async def _close_quietly(resource: Any) -> None:
    if resource is None:
        return
    close = getattr(resource, "close", None)
    if callable(close):
        await resolve(close())
