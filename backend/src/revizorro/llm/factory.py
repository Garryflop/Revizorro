"""Build pydantic-ai model objects from `provider:model` ids using keys from Settings."""

from __future__ import annotations

from pydantic_ai.models import Model

from revizorro.config import Settings


class MissingKeyError(RuntimeError):
    pass


def build_model(model_id: str, settings: Settings) -> Model:
    provider, _, name = model_id.partition(":")
    if provider in ("openai", "openai-chat"):
        if settings.openai_api_key is None:
            raise MissingKeyError(f"Для модели {model_id} нужен OPENAI_API_KEY в .env")
        from pydantic_ai.providers.openai import OpenAIProvider

        prov = OpenAIProvider(api_key=settings.openai_api_key.get_secret_value())
        if provider == "openai-chat":
            from pydantic_ai.models.openai import OpenAIChatModel

            return OpenAIChatModel(name, provider=prov)
        from pydantic_ai.models.openai import OpenAIResponsesModel

        return OpenAIResponsesModel(name, provider=prov)
    if provider == "google":
        if settings.gemini_api_key is None:
            raise MissingKeyError(f"Для модели {model_id} нужен GEMINI_API_KEY в .env")
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider

        return GoogleModel(name, provider=GoogleProvider(api_key=settings.gemini_api_key.get_secret_value()))
    if provider == "ollama":
        from pydantic_ai.models.ollama import OllamaModel
        from pydantic_ai.providers.ollama import OllamaProvider

        return OllamaModel(name, provider=OllamaProvider(base_url=settings.ollama_base_url))
    if provider == "test":
        from pydantic_ai.models.test import TestModel

        return TestModel()
    raise ValueError(
        f"Неизвестный провайдер «{provider}» в {model_id}. Используйте google:, openai: или ollama:"
    )
