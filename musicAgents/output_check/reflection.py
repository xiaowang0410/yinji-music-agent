from __future__ import annotations

import json
import logging
from typing import Any

from musicAgents.core.settings import get_llm_settings
from musicAgents.core.utils import get_llm

logger = logging.getLogger("musicAgents.reflection")


def _safe_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def build_fast_reflection(tool_result: Any) -> dict[str, Any]:
    if not isinstance(tool_result, dict):
        return {
            "confidence": "low",
            "summary": "结果格式不稳定，已退回普通回答。",
            "need_retry": False,
            "next_action": "",
        }

    final = tool_result.get("final")
    tool_results = tool_result.get("tool_results")
    executed = [
        str(item.get("tool_name") or "").strip()
        for item in tool_results or []
        if isinstance(item, dict) and str(item.get("tool_name") or "").strip()
    ]
    failed = [
        str(item.get("tool_name") or "").strip()
        for item in tool_results or []
        if isinstance(item, dict) and not bool(item.get("success"))
    ]

    if isinstance(final, dict):
        final_name = str(final.get("tool_name") or "").strip()
        summary = f"已完成工具链：{' -> '.join(executed) if executed else final_name or 'direct'}。"
        if failed:
            summary += f" 其中 {', '.join(failed)} 执行失败，已使用可用结果收敛回答。"
        return {
            "confidence": "medium" if failed else "high",
            "summary": summary,
            "need_retry": False,
            "next_action": "",
        }

    if isinstance(final, str) and final.strip():
        return {
            "confidence": "medium",
            "summary": "未调用业务工具，直接基于对话上下文回答。",
            "need_retry": False,
            "next_action": "",
        }

    return {
        "confidence": "low",
        "summary": "没有拿到明确工具结果，回答可信度较低。",
        "need_retry": False,
        "next_action": "建议补充关键词或重试。",
    }


def reflect_on_tool_result(tool_result: Any, *, question: str = "") -> dict[str, Any]:
    settings = get_llm_settings()
    if settings.polish_mode == "fast":
        return build_fast_reflection(tool_result)

    llm = get_llm(model=None, task="reflection", temperature=0, timeout=20)
    messages = [
        {
            "role": "system",
            "content": (
                "你是音乐 Agent 的执行反思模块。只输出 JSON，不要输出 Markdown。"
                "判断工具调用是否足够、结果是否可信、是否需要补救。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"用户问题：{question}\n"
                f"工具执行结果：{_safe_dumps(tool_result)[:12000]}\n\n"
                "输出字段：confidence(high/medium/low), summary, need_retry(boolean), next_action。"
            ),
        },
    ]
    try:
        response = llm.invoke(messages)
        content = getattr(response, "content", response)
        obj = json.loads(str(content).replace("```json", "").replace("```", "").strip())
        if isinstance(obj, dict):
            return {
                "confidence": str(obj.get("confidence") or "medium"),
                "summary": str(obj.get("summary") or "").strip(),
                "need_retry": bool(obj.get("need_retry")),
                "next_action": str(obj.get("next_action") or "").strip(),
            }
    except Exception:
        logger.exception("Reflection call failed, falling back to fast reflection")
    return build_fast_reflection(tool_result)
