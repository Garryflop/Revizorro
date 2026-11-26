"""One place for every LLM call: disk cache, concurrency limit, retries, fallbacks, usage accounting."""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, TypeVar

from pydantic import BaseModel
from pydantic_ai import Agent, UsageLimits
from pydantic_ai.exceptions import (
    ModelConnectionError,
    ModelQuotaExceededError,
    ModelRateLimitError,
    ModelServerError,
    ModelUnavailableError,
    UnexpectedModelBehavior,
)
from pydantic_ai.settings import ModelSettings

from revizorro.config import Settings
from revizorro.domain.models import LLMCallRecord
from revizorro.llm.factory import build_model
from revizorro.llm.pricing import estimate_cost

T = TypeVar("T", bound=BaseModel)
Role = Literal["default", "strong"]
EventSink = Callable[[dict[str, Any]], None]

_TRANSIENT = (ModelRateLimitError, ModelUnavailableError, ModelServerError, ModelConnectionError)
_SHORT_WAIT_S = 120  # quota errors asking to wait longer than this are treated as "exhausted for today"


class LLMCallError(RuntimeError):
    pass


class _ModelExhausted(Exception):
    """The model cannot serve requests now (daily quota, persistent overload); try the next one."""


class LLMRunner:
    def __init__(
        self,
        settings: Settings,
        model_default: str,
        model_strong: str,
        *,
        use_cache: bool = True,
        cache_only: bool = False,
        on_event: EventSink | None = None,
    ) -> None:
        self.settings = settings
        self.model_ids: dict[Role, str] = {"default": model_default, "strong": model_strong}
        self.fallbacks = settings.resolve_fallbacks(model_default)
        self.use_cache = use_cache or cache_only
        self.cache_only = cache_only  # never call the model: a cache miss is an error
        self.cache_dir = Path(settings.cache_dir)
        self.on_event = on_event or (lambda _e: None)
        self.records: list[LLMCallRecord] = []
        self._semaphore = asyncio.Semaphore(settings.concurrency_for(model_default))
        self._models: dict[str, Any] = {}
        self._exhausted: set[str] = set()

    def _model(self, model_id: str) -> Any:
        if model_id not in self._models:
            self._models[model_id] = build_model(model_id, self.settings)
        return self._models[model_id]

    def chain(self, role: Role) -> list[str]:
        primary = self.model_ids[role]
        return [primary, *[m for m in self.fallbacks if m != primary]]

    def _cache_file(
        self, agent_name: str, model_id: str, instructions: str, prompt: str, schema: dict
    ) -> Path:
        payload = json.dumps(
            {
                "agent": agent_name,
                "model": model_id,
                "thinking": self.settings.thinking,
                "instructions": instructions,
                "prompt": prompt,
                "schema": schema,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        key = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{agent_name}-{key[:24]}.json"

    async def run(
        self,
        *,
        agent_name: str,
        role: Role,
        instructions: str,
        prompt: str,
        output_type: type[T],
    ) -> T:
        schema = output_type.model_json_schema()
        chain = self.chain(role)

        if self.use_cache:
            for model_id in chain:
                cache_file = self._cache_file(agent_name, model_id, instructions, prompt, schema)
                if cache_file.is_file():
                    data = json.loads(cache_file.read_text(encoding="utf-8"))
                    u = data.get("usage", {})
                    self._record(
                        agent_name,
                        model_id,
                        True,
                        0.0,
                        u.get("input", 0),
                        u.get("output", 0),
                        u.get("cost"),
                        0,
                    )
                    return output_type.model_validate(data["output"])

        if self.cache_only:
            raise LLMCallError(
                f"{agent_name}: ответа нет в кэше для модели {chain[0]}, а режим --cache-only запрещает "
                "обращаться к модели. Уберите флаг или запустите с теми же моделями, что и прошлый прогон."
            )

        reasons: list[str] = []
        for model_id in chain:
            if model_id in self._exhausted:
                continue
            try:
                output, usage = await self._call(agent_name, model_id, instructions, prompt, output_type)
            except _ModelExhausted as e:
                self._exhausted.add(model_id)
                reasons.append(f"{model_id}: {e}")
                nxt = next((m for m in chain if m not in self._exhausted), None)
                self.on_event(
                    {
                        "type": "llm_fallback",
                        "agent": agent_name,
                        "from": model_id,
                        "to": nxt,
                        "reason": str(e),
                    }
                )
                continue
            if self.use_cache:
                path = self._cache_file(agent_name, model_id, instructions, prompt, schema)
                self._store(path, agent_name, model_id, output, usage)
            return output
        raise LLMCallError(
            f"{agent_name}: ни одна модель не смогла ответить. "
            + "; ".join(reasons)
            + ". Подождите, укажите другую модель в MODEL_DEFAULT/MODEL_STRONG или запасные в MODEL_FALLBACKS."
        )

    async def _call(
        self, agent_name: str, model_id: str, instructions: str, prompt: str, output_type: type[T]
    ) -> tuple[T, dict[str, Any]]:
        agent: Agent[None, T] = Agent(
            self._model(model_id),
            output_type=output_type,
            instructions=instructions,
            retries=3,
            model_settings=ModelSettings(thinking=self.settings.thinking, timeout=600),
        )
        has_fallback = any(m not in self._exhausted and m != model_id for m in self.fallbacks)
        max_attempts = self.settings.max_attempts if not has_fallback else min(3, self.settings.max_attempts)

        started = time.perf_counter()
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                async with self._semaphore:
                    self.on_event(
                        {"type": "llm_start", "agent": agent_name, "model": model_id, "attempt": attempt}
                    )
                    result = await agent.run(prompt, usage_limits=UsageLimits(request_limit=10))
            except ModelQuotaExceededError as e:
                last_error = e
                if e.retry_after is None or e.retry_after > _SHORT_WAIT_S:
                    raise _ModelExhausted("исчерпана квота провайдера") from e
                await self._backoff(agent_name, model_id, attempt, max_attempts, e.retry_after, e)
                continue
            except _TRANSIENT as e:
                last_error = e
                await self._backoff(agent_name, model_id, attempt, max_attempts, e.retry_after, e)
                continue
            except UnexpectedModelBehavior as e:
                # Output failed validation several times; one more full attempt usually fixes it.
                last_error = e
                self.on_event(
                    {"type": "llm_retry", "agent": agent_name, "model": model_id, "reason": "invalid_output"}
                )
                if attempt >= 2:
                    break
                continue

            usage = result.usage
            cost = estimate_cost(model_id, usage.input_tokens, usage.cache_read_tokens, usage.output_tokens)
            if cost is None and usage.cost is not None:
                cost = float(usage.cost)
            self._record(
                agent_name,
                model_id,
                False,
                time.perf_counter() - started,
                usage.input_tokens,
                usage.output_tokens,
                cost,
                attempt,
            )
            return result.output, {"input": usage.input_tokens, "output": usage.output_tokens, "cost": cost}

        if isinstance(last_error, (*_TRANSIENT, ModelQuotaExceededError)):
            raise _ModelExhausted(f"не отвечает после {max_attempts} попыток ({type(last_error).__name__})")
        raise LLMCallError(f"{agent_name}: модель {model_id} вернула некорректный ответ: {last_error}")

    def _store(
        self, path: Path, agent_name: str, model_id: str, output: BaseModel, usage: dict[str, Any]
    ) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "agent": agent_name,
                    "model": model_id,
                    "output": output.model_dump(mode="json"),
                    "usage": usage,
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )

    async def _backoff(
        self,
        agent: str,
        model: str,
        attempt: int,
        max_attempts: int,
        retry_after: float | None,
        err: Exception,
    ) -> None:
        if attempt >= max_attempts:
            return
        wait = retry_after if retry_after is not None else min(60.0, 4.0 * 2 ** (attempt - 1))
        wait += random.uniform(0, 1.5)
        self.on_event(
            {
                "type": "llm_retry",
                "agent": agent,
                "model": model,
                "wait_s": round(wait, 1),
                "reason": type(err).__name__,
            }
        )
        await asyncio.sleep(wait)

    def _record(
        self,
        agent: str,
        model: str,
        cached: bool,
        duration: float,
        tokens_in: int,
        tokens_out: int,
        cost: float | None,
        attempts: int,
    ) -> None:
        rec = LLMCallRecord(
            agent=agent,
            model=model,
            cached=cached,
            duration_s=round(duration, 2),
            input_tokens=tokens_in,
            output_tokens=tokens_out,
            cost_usd=cost,
            attempts=attempts,
        )
        self.records.append(rec)
        self.on_event({"type": "llm_done", **rec.model_dump()})
