"""Runtime settings loaded from environment variables and the nearest .env file."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_DIR = Path(__file__).resolve().parent

# Free-tier Gemini models, each with its own daily quota; tried in order when one is exhausted or overloaded.
GOOGLE_FREE_CHAIN = (
    "google:gemini-3.5-flash",
    "google:gemini-3.8-flash",
    "google:gemini-3.7-flash",
    "google:gemini-3.5-flash-lite",
    "google:gemini-3.1-flash-lite",
)
REPO_ROOT = PACKAGE_DIR.parents[2]  # backend/src/revizorro -> repo root


def find_env_file(start: Path | None = None) -> Path | None:
    """Return the first .env found from `start` upwards, then at the repo root."""
    here = (start or Path.cwd()).resolve()
    for folder in (here, *here.parents):
        candidate = folder / ".env"
        if candidate.is_file():
            return candidate
    candidate = REPO_ROOT / ".env"
    return candidate if candidate.is_file() else None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    gemini_api_key: SecretStr | None = Field(default=None, alias="GEMINI_API_KEY")
    ollama_base_url: str = Field(default="http://localhost:11434/v1", alias="OLLAMA_BASE_URL")

    model_default: str | None = Field(default=None, alias="MODEL_DEFAULT")
    model_strong: str | None = Field(default=None, alias="MODEL_STRONG")
    # Compatibility with the organisers' .env.example
    openai_model: str | None = Field(default=None, alias="OPENAI_MODEL")
    gemini_model: str | None = Field(default=None, alias="GEMINI_MODEL")

    model_fallbacks: str | None = Field(default=None, alias="MODEL_FALLBACKS")

    # None = pick per provider (see concurrency_for / batch_for)
    concurrency: int | None = Field(default=None, ge=1, le=32, alias="REVIZORRO_CONCURRENCY")
    batch_size: int | None = Field(default=None, ge=1, le=60, alias="REVIZORRO_BATCH_SIZE")
    thinking: Literal["low", "medium", "high"] = Field(default="medium", alias="REVIZORRO_THINKING")
    cache_dir: Path = Field(default=Path(".revizorro_cache"), alias="REVIZORRO_CACHE_DIR")
    # Never call the model: answers come from the cache or the run stops (safe demos, zero spend).
    cache_only: bool = Field(default=False, alias="REVIZORRO_CACHE_ONLY")
    max_attempts: int = Field(default=6, ge=1, le=20, alias="REVIZORRO_MAX_ATTEMPTS")

    def resolve_fallbacks(self, primary: str) -> list[str]:
        """Models to try when the primary one is out of quota; same provider only."""
        if self.model_fallbacks:
            chain = [normalize_model_id(m) for m in self.model_fallbacks.split(",") if m.strip()]
        elif primary.startswith("google:"):
            chain = list(GOOGLE_FREE_CHAIN)
        else:
            chain = []
        provider = primary.split(":", 1)[0]
        return [m for m in chain if m.split(":", 1)[0] == provider]

    def concurrency_for(self, model_id: str) -> int:
        if self.concurrency:
            return self.concurrency
        return 2 if model_id.startswith("google:") else 6

    def batch_for(self, model_id: str) -> int:
        if self.batch_size:
            return self.batch_size
        # Gemini free tier allows ~20 requests per model per day: fewer, larger batches.
        return 15 if model_id.startswith("google:") else 6

    def resolve_models(self) -> tuple[str, str]:
        """Pick (default, strong) model ids, falling back to whichever key is present."""
        default = self.model_default
        auto_strong: str | None = None
        if not default:
            if self.openai_model and self.openai_api_key:
                default = f"openai:{self.openai_model}"
            elif self.gemini_model and self.gemini_api_key:
                default = f"google:{self.gemini_model}"
            elif self.openai_api_key:
                # Recommended balance: cheap model for bulk steps, stronger one where depth matters.
                default, auto_strong = "openai:gpt-6-luna", "openai:gpt-6.1-terra"
            elif self.gemini_api_key:
                default = "google:gemini-3.5-flash"
            else:
                raise RuntimeError(
                    "Не найден ключ модели. Укажите GEMINI_API_KEY или OPENAI_API_KEY в файле .env "
                    "(образец — .env.example) либо задайте MODEL_DEFAULT=ollama:<модель>."
                )
        strong = self.model_strong or auto_strong or default
        return normalize_model_id(default), normalize_model_id(strong)


def normalize_model_id(model_id: str) -> str:
    """Accept bare model names and a few provider aliases."""
    model_id = model_id.strip()
    if ":" not in model_id:
        prefix = "google" if model_id.startswith(("gemini", "gemma")) else "openai"
        return f"{prefix}:{model_id}"
    provider, name = model_id.split(":", 1)
    aliases = {"gemini": "google", "google-gla": "google", "openai-responses": "openai"}
    return f"{aliases.get(provider, provider)}:{name}"


def load_settings(env_file: Path | None = None) -> Settings:
    path = env_file or find_env_file()
    if path is not None:
        return Settings(_env_file=path, _env_file_encoding="utf-8")  # pyright: ignore[reportCallIssue]
    return Settings()
