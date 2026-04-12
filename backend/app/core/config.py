from functools import lru_cache
from threading import Lock
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "LearnPath-KG"
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    SQLITE_URL: str = "sqlite+aiosqlite:///./learnpath.db"

    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "learnpath"

    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-3.5-turbo"
    SEARCH_API_KEY: str = ""

    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


class RuntimeSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm_base_url: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] | None = None
    llm_model: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] | None = None
    llm_api_key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] | None = None
    search_api_key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] | None = None


# Runtime overrides for config (survives until process restart)
_runtime_overrides: dict[str, str] = {}
_lock = Lock()


def get_llm_config() -> dict[str, str]:
    settings = get_settings()
    with _lock:
        return {
            "llm_base_url": _runtime_overrides.get("llm_base_url", settings.LLM_BASE_URL),
            "llm_model": _runtime_overrides.get("llm_model", settings.LLM_MODEL),
            "llm_api_key": _runtime_overrides.get("llm_api_key", settings.LLM_API_KEY),
        }


def get_search_api_key() -> str:
    settings = get_settings()
    with _lock:
        return _runtime_overrides.get("search_api_key", settings.SEARCH_API_KEY)


def update_runtime_settings(payload: RuntimeSettingsUpdate) -> None:
    with _lock:
        if payload.llm_base_url is not None:
            _runtime_overrides["llm_base_url"] = payload.llm_base_url
        if payload.llm_model is not None:
            _runtime_overrides["llm_model"] = payload.llm_model
        if payload.llm_api_key is not None:
            _runtime_overrides["llm_api_key"] = payload.llm_api_key
        if payload.search_api_key is not None:
            _runtime_overrides["search_api_key"] = payload.search_api_key
