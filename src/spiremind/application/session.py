import asyncio
import time
from dataclasses import asdict
from datetime import UTC, datetime

import httpx

from spiremind.adapters.telemetry.trace import TraceWriter
from spiremind.application.execution import PendingTransition
from spiremind.application.run_state import MemoryManager
from spiremind.config import Config
from spiremind.core.actions import ActionResult
from spiremind.core.async_utils import resolve
from spiremind.core.enums import ActionKind
from spiremind.core.model import BudgetExceeded
from spiremind.core.ports import EnvironmentError, GameEnvironment, StaleDecision
from spiremind.core.transitions import verify_transition
from spiremind.core.validation import ActionValidator
from spiremind.decision.deck import DeckAnalyzer
from spiremind.decision.frame import DecisionFrame
from spiremind.decision.mechanics.verification import verify_effect
from spiremind.decision.policies.lifecycle import lifecycle_decision
from spiremind.decision.progress import NoProgress, ProgressGuard
from spiremind.decision.router import SceneRouter


class ProviderFallbackLimit(EnvironmentError):
    """Model recovery exceeded the configured time window."""


class ProviderRetryPending(EnvironmentError):
    """Retry the model without executing its fallback action."""


class EnvironmentRecoveryLimit(EnvironmentError):
    """A game I/O stage exhausted its own recovery window."""


class DecisionInterrupted(Exception):
    """A pause invalidated a computed decision; observe again before acting."""


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
        reflection=None,
        control=None,
        new_run=False,
        journal=None,
    ):
        self.env, self.memory, self.router = env, memory, router
        self.analyzer, self.trace, self.config, self.provider = analyzer, trace, config, provider
        self.reflection = reflection
        self.control, self.new_run = control, new_run
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
        self.provider_failure_started = None
        self.environment_failure_started = None
        self._environment_failures: dict[str, float] = {}
        self._failed_stage = None
        self._pending_transition = None
        self.journal = journal
        saved = journal.load() if journal else None
        if saved:
            self._pending_transition = PendingTransition.restore(saved)
        self.phase = "idle"
        self.phase_started = time.monotonic()
        self._run_started = self.phase_started
        self._last_traced_state: tuple[str, int] | None = None

    def _recovery_clock(self):
        return time.monotonic() - (self.control.paused_seconds if self.control else 0)

    def _retry_remaining(self, failure_started):
        if failure_started is None:
            return self.config.runtime.error_retry_seconds
        return max(0, self.config.runtime.error_retry_seconds - (self._recovery_clock() - failure_started))

    async def _phase(self, name):
        self.phase, self.phase_started = name, time.monotonic()
        await resolve(self.trace.write_json("progress.json", self.summary("running", self._run_started)))

    def _environment_remaining(self, stage):
        return max(0, self.config.runtime.error_retry_seconds - self._environment_failures.get(stage, 0))

    async def _environment_call(self, stage, operation):
        """Charge only game I/O and its backoff, never model or preparation time.

        Separate budgets keep a successful observation from hiding a repeatedly
        invalid receipt. The environment owns pending-action reconciliation;
        this wrapper never re-dispatches an action on its own.
        """
        await self._phase(stage)
        remaining = self._environment_remaining(stage)
        if remaining <= 0:
            raise EnvironmentRecoveryLimit(f"{stage} recovery exceeded error_retry_seconds")
        started = self._recovery_clock()
        try:
            async with asyncio.timeout(remaining):
                result = await operation()
        except (EnvironmentError, httpx.TransportError, TimeoutError) as error:
            self._failed_stage = stage
            self._environment_failures[stage] = self._environment_failures.get(stage, 0) + max(
                0, self._recovery_clock() - started
            )
            if self.environment_failure_started is None:
                self.environment_failure_started = started
            if isinstance(error, TimeoutError):
                raise EnvironmentRecoveryLimit(f"{stage} recovery exceeded error_retry_seconds") from error
            raise
        self._environment_failures.pop(stage, None)
        if not self._environment_failures:
            self.environment_failure_started = None
        return result

    async def _checkpoint(self):
        if self.control and await self.control.checkpoint():
            self.progress = ProgressGuard()
            if hasattr(self.env, "cached_decision"):
                self.env.cached_decision = None
            return True
        return False

    async def _trace_state(self, state) -> None:
        identity = (state.decision_id, state.revision)
        if identity != self._last_traced_state:
            await resolve(self.trace.append("states.jsonl", state.model_dump(mode="json")))
            self._last_traced_state = identity

    async def _finish_transition(self, new_state, pending):
        state, decision, receipt = pending.state, pending.decision, pending.receipt
        context, producer, row = pending.context, pending.producer, pending.row

        async def verify():
            transition_ok = verify_transition(state, decision.action, new_state) and await self.env.verify(
                state, decision.action, new_state
            )
            identity_ok = (
                receipt.action_id == decision.action.id and receipt.previous_decision_id == state.decision_id
            )
            completed_ok = receipt.status != "completed" or receipt.next_decision_id == new_state.decision_id
            accepted_status = receipt.status in {"completed", "pending", "uncertain"}
            row["transition_verified"] = transition_ok
            if not (transition_ok and identity_ok and completed_ok and accepted_status):
                row.update(semantic_success=False, verify_ok=False)
                raise EnvironmentError("Action transition verification failed")
            return True

        ok = await self._environment_call("verify", verify)
        reconciled = ok and receipt.status in {"pending", "uncertain"}
        effect = verify_effect(state, decision.action, new_state)
        accepted = ok and receipt.status == "completed"
        semantic_success = accepted and effect.status != "conflict"
        row["execution_accepted"] = accepted
        row["effect_verification"] = asdict(effect)
        row.update(
            semantic_success=semantic_success,
            reconciled_after_uncertain=ok and receipt.status == "uncertain",
            reconciled_after_pending=ok and receipt.status == "pending",
            verify_ok=ok,
        )
        if decision.action.kind == ActionKind.EMBARK:
            self.started_new_run = True
            await resolve(self.memory.begin_run(new_state, transition_id="begin:" + pending.id))
        if producer != "lifecycle":
            audit = await self.memory.update(
                state,
                decision.action,
                new_state,
                decision.strategy_update,
                semantic_success=semantic_success,
                producer=producer,
                expected_policy_version=context.policy_version,
                expected_instance_id=context.instance_id,
            )
            if audit is not None:
                row["strategy_update_audit"] = audit
        if self.reflection:
            await self.reflection.notify()
        if new_state.terminal:
            await self.memory.finish_run("victory" if new_state.victory else "death")
            await resolve(self.trace.write_json("terminal-state.json", new_state.model_dump(mode="json")))
        if self.journal:
            self.journal.clear()
        self.progress.confirmed(state, decision.action, new_state)
        self.verified += 1
        self.reconciled_actions += int(reconciled)
        self.semantic_successes += int(semantic_success)
        self.consecutive_errors = 0
        self.environment_failure_started = None
        self._environment_failures.clear()
        self._failed_stage = None
        self._pending_transition = None
        return new_state

    async def _resume_transition(self, state):
        """Finish the previous receipt before requesting or sending another action."""
        pending = self._pending_transition
        row = pending.row
        if state.decision_id == pending.state.decision_id:
            # A stable old lease proves nonacceptance in the bridge protocol.
            # A completed receipt contradicting that lease requires investigation.
            if pending.receipt.status == "completed":
                raise EnvironmentError("Completed action returned its old decision lease")
            if self.journal:
                self.journal.clear()
            self._pending_transition = None
            row["recovery"] = "not_accepted_reobserve_before_deciding"
            await resolve(self.trace.append("reconciliations.jsonl", row))
            return state
        row["error"] = None
        row["recovery_attempt"] = row.get("recovery_attempt", 0) + 1
        try:
            return await self._finish_transition(state, pending)
        except Exception as error:
            row["error"] = type(error).__name__
            raise
        finally:
            await resolve(self.trace.append("reconciliations.jsonl", row))

    async def step(self):
        started = time.monotonic()
        state = await self._environment_call("observe", self.env.observe)
        if self.started_scene is None:
            self.started_scene = state.scene.value
        self.last_state = state
        await self._trace_state(state)
        if self._pending_transition is not None:
            return await self._resume_transition(state)
        can_clear_initial_terminal = self.steps == 0 and any(
            action.kind == ActionKind.RETURN_TO_MAIN_MENU for action in state.legal_actions
        )
        if state.terminal and not can_clear_initial_terminal:
            await resolve(self.memory.ensure_run(state))
            await self.memory.finish_run("victory" if state.victory else "death")
            await resolve(self.trace.write_json("terminal-state.json", state.model_dump(mode="json")))
            return state
        lifecycle = lifecycle_decision(
            state, self.config.game, new_run=self.new_run and not self.started_new_run
        )
        strategy = None
        context = None
        if lifecycle is None:
            strategy = self.router.route(state)
            await self._phase("prepare")
            preparation_started = time.monotonic()
            if hasattr(self.memory, "prepare"):
                context = await self.memory.prepare(state, strategy.name)
            else:
                self.memory.apply_analysis(state, self.analyzer.analyze(state))
                context = await self.memory.context_for(state, strategy.name)
            preparation_ms = (time.monotonic() - preparation_started) * 1000
        row = dict(
            run_id=state.run.id,
            decision_id=state.decision_id,
            timestamp=datetime.now(UTC).isoformat(),
            game_version=state.game_version,
            state_revision=state.revision,
            scene=state.scene.value,
            strategy_name=strategy.name if strategy else "lifecycle",
            memory_snapshot_id=context.snapshot_id if context else None,
            run_instance_id=context.instance_id if context else None,
            policy_version=context.policy_version if context else None,
            preparation_ms=preparation_ms if context else 0,
            action=None,
            legal_action_count=len(state.legal_actions),
            model_name=None,
            latency_ms=0,
            execution_result=None,
            verify_ok=False,
            error=None,
        )
        try:
            frame = None
            decision = lifecycle
            if decision is None:
                assert strategy is not None and context is not None
                frame = DecisionFrame.prepare(self.progress.policy_state(state), context)
                policy_state, context = frame.policy_state, frame.memory
                row["excluded_actions"] = frame.excluded
                row["policy_action_count"] = len(policy_state.legal_actions)
                await self._phase("model" if self.provider else "decision")
                if self.provider_failure_started is None:
                    decision = await strategy.decide(policy_state, context)
                else:
                    remaining = self._retry_remaining(self.provider_failure_started)
                    if remaining <= 0:
                        raise ProviderFallbackLimit("Model recovery exceeded error_retry_seconds")
                    try:
                        async with asyncio.timeout(remaining):
                            decision = await strategy.decide(policy_state, context)
                    except TimeoutError as error:
                        raise ProviderFallbackLimit("Model recovery exceeded error_retry_seconds") from error
                if strategy.last_context:
                    await resolve(self.trace.append("contexts.jsonl", asdict(strategy.last_context)))
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
                calculations=decision.calculations,
                context_id=decision.context_id,
                policy_rule=decision.policy_rule,
                action_evaluation=decision.action_evaluation,
            )
            if decision.provider_error:
                self.errors += 1
                self.provider_error_streak += 1
                self.max_provider_error_streak = max(
                    self.max_provider_error_streak, self.provider_error_streak
                )
                if self.provider_failure_started is None:
                    self.provider_failure_started = self._recovery_clock()
                    print(
                        f"Model unavailable; retrying for {self.config.runtime.error_retry_seconds:g}s",
                        flush=True,
                    )
                row["action_sent"] = False
                if self._retry_remaining(self.provider_failure_started) <= 0:
                    raise ProviderFallbackLimit("Model recovery exceeded error_retry_seconds")
                raise ProviderRetryPending("Model unavailable; waiting to retry")
            elif decision.context_id is not None:
                self.provider_error_streak = 0
                self.provider_failure_started = None
            self.fallbacks += int(decision.fallback)
            self.policy_rules += int(decision.policy_rule is not None)
            self.used_tokens += decision.input_tokens + decision.output_tokens
            if await self._checkpoint():
                raise DecisionInterrupted()
            self.validator.validate(state, decision.action)
            if frame is not None:
                frame.validate(decision)
            pending = PendingTransition(
                state,
                decision,
                ActionResult(
                    status="uncertain", action_id=decision.action.id, previous_decision_id=state.decision_id
                ),
                context,
                strategy.name if strategy else "lifecycle",
                row,
            )
            self._pending_transition = pending
            if self.journal:
                self.journal.save(pending.serialize())
            receipt = await self._environment_call("execute", lambda: self.env.execute(decision.action))
            self.uncertain_actions += int(receipt.status == "uncertain")
            row["execution_result"] = receipt.model_dump()
            pending.receipt = receipt
            if self.journal:
                self.journal.save(pending.serialize())
            new_state = await self._environment_call("observe", self.env.observe)
            self.last_state = new_state
            await self._trace_state(new_state)
            return await self._finish_transition(new_state, self._pending_transition)
        except DecisionInterrupted:
            row["discarded_on_resume"] = True
            raise
        except Exception as error:
            # Only local, sanitized messages. HTTP clients never expose request headers here.
            row["error"] = (
                f"{type(error).__name__}: {str(error)[:300]}"
                if isinstance(error, (ValueError, EnvironmentError))
                else type(error).__name__
            )
            raise
        finally:
            row["latency_ms"] = round((time.monotonic() - started) * 1000, 2)
            await resolve(self.trace.append("decisions.jsonl", row))
            if self.provider and hasattr(self.provider, "request_records"):
                await resolve(self.trace.write_json("model-requests.json", self.provider.request_records))
            self.steps += 1

    async def run(self) -> dict:
        started, outcome = time.monotonic(), "step_limit"
        self._run_started = started
        rt = self.config.runtime
        try:
            while rt.max_steps is None or self.steps < rt.max_steps:
                await self._checkpoint()
                elapsed = time.monotonic() - started - (self.control.paused_seconds if self.control else 0)
                if rt.max_seconds is not None and elapsed > rt.max_seconds:
                    outcome = "time_limit"
                    break
                tokens = (
                    (self.provider.input_tokens + self.provider.output_tokens)
                    if self.provider
                    else self.used_tokens
                )
                if rt.max_total_tokens is not None and tokens >= rt.max_total_tokens:
                    outcome = "token_limit"
                    break
                try:
                    if (
                        self.provider_failure_started is not None
                        and self._retry_remaining(self.provider_failure_started) <= 0
                    ):
                        raise ProviderFallbackLimit("Model recovery exceeded error_retry_seconds")
                    state = await self.step()
                    await resolve(self.trace.write_json("progress.json", self.summary("running", started)))
                    if state.terminal:
                        outcome = "victory" if state.victory else "death"
                        break
                    if self.steps % 10 == 0:
                        print(
                            f"step={self.steps} floor={state.run.floor} hp={state.run.hp}/{state.run.max_hp} "
                            f"scene={state.scene.value}",
                            flush=True,
                        )
                except DecisionInterrupted:
                    continue
                except BudgetExceeded:
                    outcome = "token_limit"
                    break
                except NoProgress:
                    self.errors += 1
                    outcome = "stalled"
                    break
                except (ProviderFallbackLimit, EnvironmentRecoveryLimit):
                    outcome = "error_limit"
                    break
                except ProviderRetryPending:
                    await resolve(
                        self.trace.write_json("progress.json", self.summary("retrying_provider", started))
                    )
                    await asyncio.sleep(min(1, self._retry_remaining(self.provider_failure_started)))
                except ValueError as error:
                    self.errors += 1
                    await resolve(
                        self.trace.append("errors.jsonl", {"error": type(error).__name__, "step": self.steps})
                    )
                    outcome = "invalid_state"
                    break
                except (EnvironmentError, httpx.TransportError) as error:
                    self.errors += 1
                    self.consecutive_errors += 1
                    await resolve(
                        self.trace.append("errors.jsonl", {"error": type(error).__name__, "step": self.steps})
                    )
                    stage = self._failed_stage or "verify"
                    self._environment_failures.setdefault(stage, 0)
                    remaining = self._environment_remaining(stage)
                    if remaining <= 0:
                        outcome = "error_limit"
                        break
                    await resolve(
                        self.trace.write_json("progress.json", self.summary("retrying_environment", started))
                    )
                    sleep_started = self._recovery_clock()
                    await asyncio.sleep(min(remaining / 2, 0.2 if isinstance(error, StaleDecision) else 1))
                    self._environment_failures[stage] += max(0, self._recovery_clock() - sleep_started)
            else:
                outcome = "step_limit"
        except BaseException:
            outcome = "interrupted"
            raise
        finally:
            if self.last_state is not None:
                await self._trace_state(self.last_state)
                await resolve(
                    self.trace.write_json("final-state.json", self.last_state.model_dump(mode="json"))
                )
            summary = self.summary(outcome, started)
            summary["phase"] = "stopped"
            await resolve(self.trace.write_json("summary.json", summary))
            await resolve(self.trace.write_json("progress.json", summary))
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
            error_retry_seconds=self.config.runtime.error_retry_seconds,
            phase=self.phase,
            phase_started_at=datetime.fromtimestamp(
                time.time() - (time.monotonic() - self.phase_started), UTC
            ).isoformat(),
            provider_failure_seconds=(
                round(self._recovery_clock() - self.provider_failure_started, 2)
                if self.provider_failure_started is not None
                else 0
            ),
            floor=state.run.floor if state else None,
            environment_failure_seconds=(round(max(self._environment_failures.values(), default=0), 2)),
            environment_recovery_seconds={
                stage: round(seconds, 2) for stage, seconds in self._environment_failures.items()
            },
            character=state.run.character if state else None,
            game_version=state.game_version if state else None,
            model_requested=self.config.model.model if self.provider else None,
            model_resolved=self.provider.last_model if self.provider else None,
            model_calls=self.provider.calls if self.provider else 0,
            calculator_calls=self.provider.calculator_calls if self.provider else 0,
            input_tokens=self.provider.input_tokens if self.provider else 0,
            output_tokens=self.provider.output_tokens if self.provider else 0,
            reported_input_tokens=getattr(self.provider, "reported_input_tokens", 0),
            reported_output_tokens=getattr(self.provider, "reported_output_tokens", 0),
            reasoning_responses=self.provider.reasoning_responses if self.provider else 0,
            incomplete_model_responses=self.provider.incomplete_responses if self.provider else 0,
            invalid_model_responses=self.provider.invalid_responses if self.provider else 0,
            model_transport_errors=self.provider.transport_errors if self.provider else 0,
            retryable_model_http_responses=(self.provider.retryable_http_responses if self.provider else 0),
            duration_seconds=round(time.monotonic() - started, 2),
            trace_dir=str(self.trace.path.resolve()),
        )
