import asyncio
import time
from dataclasses import asdict
from datetime import UTC, datetime

import httpx

from spiremind.config import Config
from spiremind.core.enums import ActionKind
from spiremind.environment.base import EnvironmentError, GameEnvironment, StaleDecision
from spiremind.memory.manager import MemoryManager
from spiremind.strategies.run import DeckAnalyzer

from .lifecycle import lifecycle_decision
from .progress import NoProgress, ProgressGuard
from .router import SceneRouter
from .trace import TraceWriter
from .validator import ActionValidator


class ProviderFallbackLimit(EnvironmentError):
    """Repeated model failures reached the configured safety limit."""


class AgentRuntime:
    def __init__(
        self,
        env: GameEnvironment,
        memory: MemoryManager,
        router: SceneRouter,
        analyzer: DeckAnalyzer,
        trace: TraceWriter,
        config: Config,
        provider=None,
    ):
        self.env, self.memory, self.router = env, memory, router
        self.analyzer, self.trace, self.config, self.provider = analyzer, trace, config, provider
        self.validator = ActionValidator()
        self.progress = ProgressGuard()
        self.last_state = None
        self.steps = self.errors = self.consecutive_errors = self.fallbacks = self.verified = 0
        self.used_tokens = 0
        self.started_scene = None
        self.started_new_run = False
        self.uncertain_actions = self.policy_rules = 0
        self.reconciled_actions = self.semantic_successes = 0
        self.provider_error_streak = self.max_provider_error_streak = 0
        self._last_traced_state: tuple[str, int] | None = None

    def _trace_state(self, state) -> None:
        identity = (state.decision_id, state.revision)
        if identity != self._last_traced_state:
            self.trace.append("states.jsonl", state.model_dump(mode="json"))
            self._last_traced_state = identity

    async def step(self):
        started = time.monotonic()
        state = await self.env.observe()
        if self.started_scene is None:
            self.started_scene = state.scene.value
        self.last_state = state
        self._trace_state(state)
        can_clear_initial_terminal = self.steps == 0 and any(
            action.kind == ActionKind.RETURN_TO_MAIN_MENU for action in state.legal_actions
        )
        if state.terminal and not can_clear_initial_terminal:
            self.memory.ensure_run(state)
            await self.memory.finish_run("victory" if state.victory else "death")
            self.trace.write_json("terminal-state.json", state.model_dump(mode="json"))
            return state
        lifecycle = lifecycle_decision(state, self.config.game)
        strategy = None
        context = None
        if lifecycle is None:
            strategy = self.router.route(state)
            self.memory.apply_analysis(state, self.analyzer.analyze(state))
            context = await self.memory.context_for(state, strategy.name)
        row = dict(
            run_id=state.run.id,
            decision_id=state.decision_id,
            timestamp=datetime.now(UTC).isoformat(),
            game_version=state.game_version,
            state_revision=state.revision,
            scene=state.scene.value,
            strategy_name=strategy.name if strategy else "lifecycle",
            memory_snapshot_id=context.snapshot_id if context else None,
            action=None,
            legal_action_count=len(state.legal_actions),
            model_name=None,
            latency_ms=0,
            execution_result=None,
            verify_ok=False,
            error=None,
        )
        try:
            decision = lifecycle
            if decision is None:
                assert strategy is not None and context is not None
                policy_state = self.progress.policy_state(state)
                row["policy_action_count"] = len(policy_state.legal_actions)
                decision = await strategy.decide(policy_state, context)
                if strategy.last_context:
                    self.trace.append("contexts.jsonl", asdict(strategy.last_context))
            row.update(
                action=decision.action.model_dump(mode="json"),
                model_name=decision.model_name,
                reason=decision.reason,
                confidence=decision.confidence,
                fallback=decision.fallback,
                provider_error=decision.provider_error,
                strategy_update=(
                    decision.strategy_update.model_dump(exclude_none=True)
                    if decision.strategy_update
                    else None
                ),
                input_tokens=decision.input_tokens,
                output_tokens=decision.output_tokens,
                context_id=decision.context_id,
                policy_rule=decision.policy_rule,
            )
            if decision.provider_error:
                self.errors += 1
                self.provider_error_streak += 1
                self.max_provider_error_streak = max(
                    self.max_provider_error_streak, self.provider_error_streak
                )
                if self.provider_error_streak >= self.config.runtime.max_errors:
                    raise ProviderFallbackLimit("Repeated provider failures reached max_errors")
            elif decision.context_id is not None:
                self.provider_error_streak = 0
            self.fallbacks += int(decision.fallback)
            self.policy_rules += int(decision.policy_rule is not None)
            self.used_tokens += decision.input_tokens + decision.output_tokens
            self.validator.validate(state, decision.action)
            receipt = await self.env.execute(decision.action)
            self.uncertain_actions += int(receipt.status == "uncertain")
            row["execution_result"] = receipt.model_dump()
            new_state = await self.env.observe()
            self.last_state = new_state
            self._trace_state(new_state)
            transition_ok = await self.env.verify(state, decision.action, new_state)
            identity_ok = (
                receipt.action_id == decision.action.id and receipt.previous_decision_id == state.decision_id
            )
            completed_ok = receipt.status != "completed" or receipt.next_decision_id == new_state.decision_id
            accepted_status = receipt.status in {"completed", "pending", "uncertain"}
            ok = transition_ok and identity_ok and completed_ok and accepted_status
            reconciled = ok and receipt.status in {"pending", "uncertain"}
            semantic_success = ok and receipt.status == "completed"
            row["transition_verified"] = transition_ok
            row["semantic_success"] = semantic_success
            row["reconciled_after_uncertain"] = ok and receipt.status == "uncertain"
            row["reconciled_after_pending"] = ok and receipt.status == "pending"
            row["verify_ok"] = ok
            if not ok:
                self.memory.working.invalidate_plan()
                raise EnvironmentError("Action transition verification failed")
            self.verified += 1
            self.reconciled_actions += int(reconciled)
            self.semantic_successes += int(semantic_success)
            if decision.action.kind == ActionKind.EMBARK:
                self.started_new_run = True
            self.progress.confirmed(state, decision.action, new_state)
            strategy_update_audit = None
            if lifecycle is None:
                strategy_update_audit = await self.memory.update(
                    state,
                    decision.action,
                    new_state,
                    decision.strategy_update,
                    semantic_success=semantic_success,
                )
            if strategy_update_audit is not None:
                row["strategy_update_audit"] = strategy_update_audit
            if new_state.terminal:
                await self.memory.finish_run("victory" if new_state.victory else "death")
                self.trace.write_json("terminal-state.json", new_state.model_dump(mode="json"))
            self.consecutive_errors = 0
            return new_state
        except Exception as error:
            # Only local, sanitized messages. HTTP clients never expose request headers here.
            row["error"] = (
                f"{type(error).__name__}: {str(error)[:300]}"
                if isinstance(error, (ValueError, EnvironmentError))
                else type(error).__name__
            )
            self.memory.working.invalidate_plan()
            raise
        finally:
            row["latency_ms"] = round((time.monotonic() - started) * 1000, 2)
            self.trace.append("decisions.jsonl", row)
            self.steps += 1

    async def run(self) -> dict:
        started, outcome = time.monotonic(), "step_limit"
        rt = self.config.runtime
        try:
            while self.steps < rt.max_steps:
                if time.monotonic() - started > rt.max_seconds:
                    outcome = "time_limit"
                    break
                tokens = (
                    (self.provider.input_tokens + self.provider.output_tokens)
                    if self.provider
                    else self.used_tokens
                )
                if tokens >= rt.max_total_tokens:
                    outcome = "token_limit"
                    break
                try:
                    state = await self.step()
                    self.trace.write_json("progress.json", self.summary("running", started))
                    if state.terminal:
                        outcome = "victory" if state.victory else "death"
                        break
                    if self.steps % 10 == 0:
                        print(
                            f"step={self.steps} floor={state.run.floor} hp={state.run.hp}/{state.run.max_hp} "
                            f"scene={state.scene.value}",
                            flush=True,
                        )
                except NoProgress:
                    self.errors += 1
                    outcome = "stalled"
                    break
                except ProviderFallbackLimit:
                    outcome = "error_limit"
                    break
                except ValueError as error:
                    self.errors += 1
                    self.trace.append("errors.jsonl", {"error": type(error).__name__, "step": self.steps})
                    outcome = "invalid_state"
                    break
                except (EnvironmentError, httpx.TransportError) as error:
                    self.errors += 1
                    self.consecutive_errors += 1
                    self.trace.append("errors.jsonl", {"error": type(error).__name__, "step": self.steps})
                    if self.consecutive_errors >= rt.max_errors:
                        outcome = "error_limit"
                        break
                    await asyncio.sleep(0.2 if isinstance(error, StaleDecision) else 1)
            else:
                outcome = "step_limit"
        except BaseException:
            outcome = "interrupted"
            raise
        finally:
            if self.last_state is not None:
                self._trace_state(self.last_state)
                self.trace.write_json("final-state.json", self.last_state.model_dump(mode="json"))
            summary = self.summary(outcome, started)
            self.trace.write_json("summary.json", summary)
            self.trace.write_json("progress.json", summary)
        return summary

    def summary(self, outcome: str, started: float) -> dict:
        state = self.last_state
        return dict(
            attempt_id=self.trace.attempt_id,
            mode=self.trace.mode,
            outcome=outcome,
            complete=outcome in {"victory", "death"},
            started_scene=self.started_scene,
            started_new_run=self.started_new_run,
            full_lifecycle_complete=self.started_new_run and outcome in {"victory", "death"},
            steps=self.steps,
            verified_actions=self.verified,
            transition_verified_actions=self.verified,
            semantic_success_actions=self.semantic_successes,
            errors=self.errors,
            fallbacks=self.fallbacks,
            uncertain_actions=self.uncertain_actions,
            reconciled_actions=self.reconciled_actions,
            policy_rule_decisions=self.policy_rules,
            provider_error_streak=self.provider_error_streak,
            max_provider_error_streak=self.max_provider_error_streak,
            floor=state.run.floor if state else None,
            character=state.run.character if state else None,
            game_version=state.game_version if state else None,
            model_requested=self.config.model.model if self.provider else None,
            model_resolved=self.provider.last_model if self.provider else None,
            model_calls=self.provider.calls if self.provider else 0,
            input_tokens=self.provider.input_tokens if self.provider else 0,
            output_tokens=self.provider.output_tokens if self.provider else 0,
            reasoning_responses=self.provider.reasoning_responses if self.provider else 0,
            incomplete_model_responses=self.provider.incomplete_responses if self.provider else 0,
            invalid_model_responses=self.provider.invalid_responses if self.provider else 0,
            model_transport_errors=self.provider.transport_errors if self.provider else 0,
            retryable_model_http_responses=(self.provider.retryable_http_responses if self.provider else 0),
            duration_seconds=round(time.monotonic() - started, 2),
            trace_dir=str(self.trace.path.resolve()),
        )
