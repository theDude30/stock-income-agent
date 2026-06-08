import logging

import anthropic

from app.llm.base import LLMUsage

logger = logging.getLogger(__name__)

# ($ per 1M input tokens, $ per 1M output tokens)
_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

_MAX_TOKENS = 1024


def compute_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    in_price, out_price = _PRICING.get(model, (3.0, 15.0))
    return input_tokens / 1_000_000 * in_price + output_tokens / 1_000_000 * out_price


class AnthropicLLMClient:
    def __init__(self, model: str, api_key: str) -> None:
        self.model = model
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete_structured(self, *, system, prompt, schema, prompt_version, key):
        response = self._client.messages.parse(
            model=self.model,
            max_tokens=_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=schema,
        )
        parsed = response.parsed_output
        if parsed is None:
            raise ValueError(f"LLM returned no parsable output for {key} (prompt {prompt_version})")
        usage = LLMUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cost_usd=compute_cost_usd(self.model, response.usage.input_tokens, response.usage.output_tokens),
        )
        return parsed, usage
