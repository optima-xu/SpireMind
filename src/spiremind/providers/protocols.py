"""Decision and reflection transports are separate capabilities."""

from typing import Protocol


class DecisionProvider(Protocol):
    async def choose(self, context, legal_ids: set[str]): ...


class ReflectionProvider(Protocol):
    async def reflect(self, evidence: list[dict]) -> list[dict]: ...


class BudgetExceeded(RuntimeError):
    pass


class RequestBudget:
    """Reserve the entire possible request before dispatch; reconcile observed usage."""

    def __init__(self, max_requests: int | None, max_tokens: int | None, parent=None):
        self.max_requests, self.max_tokens = max_requests, max_tokens
        self.requests = self.tokens = self.reserved = 0
        self.parent = parent

    def reserve(self, tokens):
        if (self.max_requests is not None and self.requests >= self.max_requests) or (
            self.max_tokens is not None and self.tokens + self.reserved + tokens > self.max_tokens
        ):
            raise BudgetExceeded("request_budget_exhausted")
        if self.parent:
            self.parent.reserve(tokens)
        self.requests += 1
        self.reserved += tokens
        return tokens

    def settle(self, reservation, tokens):
        self.reserved -= reservation
        self.tokens += tokens
        if self.parent:
            self.parent.settle(reservation, tokens)

    def report(self):
        return dict(
            requests=self.requests,
            tokens=self.tokens,
            reserved=self.reserved,
            max_requests=self.max_requests,
            max_tokens=self.max_tokens,
        )
