from typing import Protocol

from spiremind.core.budget import ContextOverflow
from spiremind.core.context import MemoryContext
from spiremind.core.decision import Decision
from spiremind.core.model import DecisionProvider, ProviderError
from spiremind.core.state import GameState
from spiremind.decision.context import ContextCompiler


class DecisionStrategy(Protocol):
    name: str

    async def decide(self, state: GameState, memory: MemoryContext) -> Decision: ...


class LLMStrategy:
    name = "event"
    task = "Choose the most useful legal option."

    def __init__(self, compiler: ContextCompiler, provider: DecisionProvider | None, fallback):
        self.compiler, self.provider, self.fallback = compiler, provider, fallback
        self.last_context = None

    def task_for(self, state: GameState, memory: MemoryContext) -> str:
        return self.task

    async def decide(
        self, state: GameState, memory: MemoryContext, *, task_override: str | None = None
    ) -> Decision:
        if not state.legal_actions:
            raise ValueError("No legal actions at this decision")
        self.last_context = None
        if len(state.legal_actions) == 1:
            return Decision(action=state.legal_actions[0], reason="Only one legal action", confidence=1)
        if self.provider is None:
            return self.fallback(state, memory)
        try:
            context = await self.compiler.build(
                state, self.name, memory, task_override or self.task_for(state, memory)
            )
            self.last_context = context
            result = await self.provider.choose(context, {a.id for a in state.legal_actions})
            choice = result.choice
            return Decision(
                action=next(a for a in state.legal_actions if a.id == choice.action_id),
                reason=choice.reason,
                confidence=choice.confidence,
                strategy_update=choice.strategy_update,
                model_name=result.model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                calculations=list(result.calculations),
                context_id=context.id,
                action_evaluation=next(
                    (row for row in context.action_evaluations if row["action_id"] == choice.action_id), None
                ),
            )
        except (ProviderError, ContextOverflow) as error:
            decision = self.fallback(state, memory)
            decision.provider_error = str(error)
            return decision
