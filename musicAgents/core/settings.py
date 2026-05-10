from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from env_settings import get_first_env, load_env


def _bool_env(name: str, default: bool = False) -> bool:
    value = str(os.getenv(name, "") or "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "y", "on"}


def _int_env(name: str, default: int) -> int:
    value = str(os.getenv(name, "") or "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    qwen_api_key: str
    deepseek_api_key: str
    deepseek_base_url: str
    intent_model: str
    tool_model: str
    polish_model: str
    reflection_model: str
    request_timeout: int
    max_retries: int
    deepseek_thinking: bool
    reasoning_effort: str
    polish_mode: str

    @property
    def resolved_provider(self) -> str:
        provider = self.provider.lower().strip()
        if provider == "deepseek" and self.deepseek_api_key:
            return "deepseek"
        if self.qwen_api_key:
            return "qwen"
        return provider or "qwen"

    def model_for_task(self, task: str, explicit_model: str | None = None) -> str:
        task_name = str(task or "default").strip().lower()
        if self.resolved_provider == "deepseek":
            if task_name == "tool":
                return self.tool_model
            if task_name == "polish":
                return self.polish_model
            if task_name == "reflection":
                return self.reflection_model
            return self.intent_model
        return explicit_model or "qwen-plus"


@lru_cache(maxsize=1)
def get_llm_settings() -> LLMSettings:
    load_env()
    provider = get_first_env("YINJI_LLM_PROVIDER", "LLM_PROVIDER", default="deepseek")
    return LLMSettings(
        provider=provider,
        qwen_api_key=get_first_env("DASHSCOPE_API_KEY", "QWEN_API_KEY", default=""),
        deepseek_api_key=get_first_env("DEEPSEEK_API_KEY", default=""),
        deepseek_base_url=get_first_env("DEEPSEEK_BASE_URL", default="https://api.deepseek.com"),
        intent_model=get_first_env("YINJI_INTENT_MODEL", default="deepseek-v4-flash"),
        tool_model=get_first_env("YINJI_TOOL_MODEL", default="deepseek-v4-flash"),
        polish_model=get_first_env("YINJI_POLISH_MODEL", default="deepseek-v4-flash"),
        reflection_model=get_first_env("YINJI_REFLECTION_MODEL", default="deepseek-v4-flash"),
        request_timeout=_int_env("YINJI_LLM_TIMEOUT_SECONDS", 45),
        max_retries=_int_env("YINJI_LLM_MAX_RETRIES", 2),
        deepseek_thinking=_bool_env("YINJI_DEEPSEEK_THINKING", False),
        reasoning_effort=get_first_env("YINJI_REASONING_EFFORT", default="high"),
        polish_mode=get_first_env("YINJI_POLISH_MODE", default="fast").lower().strip(),
    )


def clear_settings_cache() -> None:
    get_llm_settings.cache_clear()
