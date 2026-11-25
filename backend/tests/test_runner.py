import asyncio
from pathlib import Path

import pytest
from pydantic import BaseModel

from revizorro.config import GOOGLE_FREE_CHAIN, Settings
from revizorro.llm import runner as rn


class Out(BaseModel):
    value: str


def _settings(tmp_path: Path, **kw) -> Settings:
    return Settings(GEMINI_API_KEY="g", OPENAI_API_KEY="o", REVIZORRO_CACHE_DIR=str(tmp_path), **kw)


def test_provider_defaults(tmp_path):
    s = _settings(tmp_path)
    assert s.batch_for("google:gemini-3.5-flash") == 15 and s.batch_for("openai:gpt-6-luna") == 6
    assert s.concurrency_for("google:x") == 2 and s.concurrency_for("openai:x") == 6
    assert s.resolve_fallbacks("google:gemini-3.5-flash") == list(GOOGLE_FREE_CHAIN)
    assert s.resolve_fallbacks("openai:gpt-6-luna") == []
    custom = _settings(tmp_path, MODEL_FALLBACKS="openai:gpt-6-luna, google:gemini-3.1-flash-lite")
    assert custom.resolve_fallbacks("openai:gpt-6.1-sol") == ["openai:gpt-6-luna"]


def test_fallback_on_exhausted_quota_then_cache(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    calls: list[str] = []

    async def fake_call(self, agent_name, model_id, instructions, prompt, output_type):
        calls.append(model_id)
        if model_id == "google:gemini-3.5-flash":
            raise rn._ModelExhausted("исчерпана квота провайдера")
        self._record(agent_name, model_id, False, 0.1, 10, 5, 0.0, 1)
        return output_type(value=model_id), {"input": 10, "output": 5, "cost": 0.0}

    monkeypatch.setattr(rn.LLMRunner, "_call", fake_call)
    events: list[dict] = []
    r = rn.LLMRunner(s, "google:gemini-3.5-flash", "google:gemini-3.5-flash", on_event=events.append)

    out = asyncio.run(r.run(agent_name="a", role="default", instructions="i", prompt="p", output_type=Out))
    assert out.value == "google:gemini-3.8-flash"
    assert any(e["type"] == "llm_fallback" and e["to"] == "google:gemini-3.8-flash" for e in events)

    # Exhausted model is skipped for later calls in the same run.
    asyncio.run(r.run(agent_name="b", role="strong", instructions="i", prompt="p", output_type=Out))
    assert calls == ["google:gemini-3.5-flash", "google:gemini-3.8-flash", "google:gemini-3.8-flash"]

    # A fresh run finds the cached answer of the fallback model without calling anything.
    r2 = rn.LLMRunner(s, "google:gemini-3.5-flash", "google:gemini-3.5-flash")
    out2 = asyncio.run(r2.run(agent_name="a", role="default", instructions="i", prompt="p", output_type=Out))
    assert out2.value == "google:gemini-3.8-flash" and r2.records[0].cached
    assert len(calls) == 3


def test_all_models_exhausted_raises(tmp_path, monkeypatch):
    s = _settings(tmp_path)

    async def always_exhausted(self, *args, **kwargs):
        raise rn._ModelExhausted("исчерпана квота провайдера")

    monkeypatch.setattr(rn.LLMRunner, "_call", always_exhausted)
    r = rn.LLMRunner(s, "google:gemini-3.5-flash", "google:gemini-3.5-flash")
    with pytest.raises(rn.LLMCallError, match="ни одна модель"):
        asyncio.run(r.run(agent_name="a", role="default", instructions="i", prompt="p", output_type=Out))
