"""Official OpenAI list prices, USD per 1M tokens (developers.openai.com/api/docs/pricing, 2026-11-25)."""

from __future__ import annotations

# model: (input, cached input, output)
OPENAI_PRICES: dict[str, tuple[float, float, float]] = {
    "gpt-6-luna": (0.10, 0.01, 0.50),
    "gpt-6.1-terra": (1.00, 0.05, 5.00),
    "gpt-6.1-sol": (2.00, 0.10, 10.00),
    "gpt-6.2-sol": (2.00, 0.10, 10.00),
    "gpt-6-astra": (10.00, 1.00, 50.00),
    "gpt-6.2-astra": (8.00, 0.40, 40.00),
    "gpt-5.6-luna": (0.20, 0.02, 1.20),
    "gpt-5.6-terra": (2.00, 0.20, 12.00),
    "gpt-5.6-sol": (4.00, 0.40, 20.00),
    "gpt-5.4-mini": (0.75, 0.075, 4.50),
    "gpt-5.4-nano": (0.20, 0.02, 1.25),
    "gpt-5-mini": (0.25, 0.025, 2.00),
    "gpt-4.1-mini": (0.40, 0.10, 1.60),
    "gpt-4o-mini": (0.15, 0.075, 0.60),
}


def estimate_cost(model_id: str, input_tokens: int, cached_tokens: int, output_tokens: int) -> float | None:
    provider, _, name = model_id.partition(":")
    if provider in ("ollama", "test"):
        return 0.0
    if provider != "openai" or name not in OPENAI_PRICES:
        return None
    p_in, p_cached, p_out = OPENAI_PRICES[name]
    fresh = max(0, input_tokens - cached_tokens)
    return (fresh * p_in + cached_tokens * p_cached + output_tokens * p_out) / 1_000_000
