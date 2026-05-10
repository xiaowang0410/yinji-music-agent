from __future__ import annotations

import logging
from typing import Any

from langchain_community.chat_models import ChatTongyi
from langchain_openai import ChatOpenAI

from musicAgents.core.deepseek_chat import DeepSeekChatOpenAI
from musicAgents.core.settings import get_llm_settings

logger = logging.getLogger("musicAgents.llm_provider")


def _deepseek_extra_body(task: str) -> dict[str, Any]:
    settings = get_llm_settings()
    if not settings.deepseek_thinking:
        return {}
    if str(task or "").strip().lower() not in {"tool", "reflection"}:
        return {}
    return {
        "thinking": {
            "type": "enabled",
            "budget_tokens": 1024,
        }
    }


def build_llm(
    *,
    task: str = "default",
    model: str | None = None,
    temperature: float = 0,
    timeout: int | None = None,
):
    settings = get_llm_settings()
    provider = settings.resolved_provider
    resolved_timeout = timeout or settings.request_timeout

    if provider == "deepseek":
        resolved_model = model or settings.model_for_task(task)
        kwargs: dict[str, Any] = {
            "model": resolved_model,
            "temperature": temperature,
            "api_key": settings.deepseek_api_key,
            "base_url": settings.deepseek_base_url,
            "timeout": resolved_timeout,
            "max_retries": settings.max_retries,
        }
        extra_body = _deepseek_extra_body(task)
        if extra_body:
            kwargs["extra_body"] = extra_body
        logger.debug("Using DeepSeek model for %s: %s", task, resolved_model)
        return DeepSeekChatOpenAI(**kwargs)

    resolved_model = model or settings.model_for_task(task)
    logger.debug("Using Qwen model for %s: %s", task, resolved_model)
    return ChatTongyi(
        model=resolved_model,
        temperature=temperature,
        api_key=settings.qwen_api_key or None,
        max_retries=settings.max_retries,
    )
