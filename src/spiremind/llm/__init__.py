"""OpenAI-compatible LLM provider client and bounded arithmetic calculator tool."""

from __future__ import annotations

from spiremind.llm.calculator import TOOL, CalculatorError, calculate, execute_calculator
from spiremind.llm.client import OpenAIProvider, ProviderError, probe_llm

__all__ = [
    "CalculatorError",
    "OpenAIProvider",
    "ProviderError",
    "TOOL",
    "calculate",
    "execute_calculator",
    "probe_llm",
]
