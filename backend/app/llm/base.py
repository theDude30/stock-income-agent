from collections.abc import Set
from dataclasses import dataclass, field
from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int
    output_tokens: int
    cost_usd: float


class LLMClient(Protocol):
    def complete_structured(
        self, *, system: str, prompt: str, schema: type[T], prompt_version: str, key: str,
    ) -> tuple[T, LLMUsage]: ...


@dataclass
class FakeLLMClient:
    """Deterministic test double. Returns canned schema instances keyed by `key`."""

    by_key: dict[str, BaseModel]
    usage: LLMUsage
    raise_for: Set[str] = field(default_factory=set)

    def complete_structured(self, *, system, prompt, schema, prompt_version, key):
        if key in self.raise_for:
            raise ValueError(f"fake LLM forced failure for {key}")
        value = self.by_key[key]
        if not isinstance(value, schema):
            raise TypeError(f"canned value for {key} is not {schema.__name__}")
        return value, self.usage
