import json
from dataclasses import dataclass


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def estimate_tokens(value) -> int:
    # Model-independent conservative estimate, not a tokenizer/cost measurement.
    text = value if isinstance(value, str) else encode(value)
    return (len(text.encode("utf-8")) + 2) // 3


@dataclass(frozen=True)
class ContextBudget:
    target: int = 4000
    maximum: int = 16000


class ContextOverflow(ValueError):
    pass
