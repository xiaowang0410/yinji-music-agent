import json
import logging
import os
import re
import sys
import threading
import time
from functools import lru_cache
from typing import Any, Callable, Optional

# Support direct script execution while keeping package-style imports.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from musicAgents.core.logging_utils import setup_logging
from musicAgents.intent_detection.agent import get_intent_detection_agent
from musicAgents.output_check.agent import (
    extract_client_action,
    extract_rich_content,
    format_structured_output,
    polish_with_guard,
    polish_with_guard_stream,
    should_polish_response,
)
from musicAgents.output_check.reflection import reflect_on_tool_result
from musicAgents.core.settings import get_llm_settings
from musicAgents.core.tracing import AgentRunTracker
from musicAgents.tool_execution.agent import get_tool_execution_agent

logger = logging.getLogger("musicAgents.main")

PROJECT_NAME = "音迹"
ASSISTANT_NAME = "小听"
DEVELOPER_NAME = "小汪"
ASSISTANT_INTRO_REPLY = (
    f"我叫{ASSISTANT_NAME}，是由{DEVELOPER_NAME}开发的智能音乐助手，也是{PROJECT_NAME}的核心助手。\n\n"
    "我可以帮你找歌、查歌词、查看你点赞的歌曲、推荐适合不同场景的音乐、获取歌单和专辑信息、"
    "拿播放或下载链接，也能陪你聊音乐。"
)

_VISIBLE_URL_RE = re.compile(r"https?://[^\s<]+")
_STREAM_BOUNDARY_RE = re.compile(r"[\n。！？!?]")
_SHORTCUT_QUERY_NORMALIZE_RE = re.compile(r"[\s,，.。!！?？:：;；、\"'“”‘’()\[\]（）【】《》<>~`·…-]+")
_ID_LABELS = (
    r"song[\s_-]*id|user[\s_-]*id|playlist[\s_-]*id|album[\s_-]*id|track[\s_-]*id|"
    r"歌曲\s*id|歌单\s*id|用户\s*id|专辑\s*id|曲目\s*id|播放列表\s*id|"
    r"歌曲编号|歌单编号|用户编号|曲目编号|id|编号"
)
_EXPOSED_ID_RE = re.compile(
    rf"""(?ix)
    (?:
        ["'“”]?
        (?:{_ID_LABELS})
        ["'“”]?
        \s*
        (?:为|是|:|：|-\s*|\s+)?
        \s*
        ["'“”]?[A-Za-z0-9_-]{{5,}}["'“”]?
        \s*
        (?:[,，。；;)]|$)?
    )
    """
)
_INTERNAL_ERROR_MARKERS = (
    "access violation",
    "maximum call stack",
    "failed to register environment variables",
    "error during request setup",
    "anonymous registration",
    "reasoning_content",
    "not a function",
    "resolve_song_",
    "nativecommanderror",
    "url using bad/illegal format",
)
_DIRECT_TEXT_TOOLS = {"song_url_v1", "song_download_url_v1"}
_AGENT_RUNTIME_WARM_LOCK = threading.Lock()
_AGENT_RUNTIME_WARMED = False
_AGENT_RUNTIME_WARM_THREAD: threading.Thread | None = None


def _configure_console_io() -> None:
    """尽量把 Windows 控制台切到 UTF-8，避免打印中断。"""
    if not hasattr(sys.stdout, "reconfigure"):
        return
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def safe_print(text: str, *, end: str = "", flush: bool = True) -> None:
    try:
        print(text, end=end, flush=flush)
    except UnicodeEncodeError:
        try:
            payload = (str(text) + end).encode(sys.stdout.encoding or "utf-8", errors="replace")
            getattr(sys.stdout, "buffer", sys.stdout).write(payload)
            if flush:
                sys.stdout.flush()
        except Exception:
            return
    except OSError:
        return


def _extract_current_user_question(text: str) -> str:
    marker = "【当前用户问题】"
    if not isinstance(text, str):
        return ""
    if marker not in text:
        return text.strip()
    tail = text.split(marker)[-1]
    return (tail or "").strip()


def _sanitize_exposed_ids_plain_text(text: str) -> str:
    value = str(text or "")
    if not value:
        return value
    cleaned = _EXPOSED_ID_RE.sub("", value)
    cleaned = re.sub(r"([，,；;:：])\s*([。！？!?])", r"\2", cleaned)
    cleaned = re.sub(r"([，,；;:：]){2,}", lambda match: match.group(0)[0], cleaned)
    cleaned = re.sub(r"(?m)^[，,；;:：\s]+", "", cleaned)
    cleaned = re.sub(r"(?m)[ \t]+$", "", cleaned)
    return cleaned


def _sanitize_exposed_ids(text: str) -> str:
    value = str(text or "")
    if not value:
        return value

    parts: list[str] = []
    last = 0
    for match in _VISIBLE_URL_RE.finditer(value):
        prefix = value[last:match.start()]
        if prefix:
            parts.append(_sanitize_exposed_ids_plain_text(prefix))
        parts.append(match.group(0))
        last = match.end()

    suffix = value[last:]
    if suffix:
        parts.append(_sanitize_exposed_ids_plain_text(suffix))
    return "".join(parts)


def _sanitize_user_output_core(text: str, *, trim: bool) -> str:
    value = str(text or "")
    if not value:
        return ""

    value = value.replace("**", "")
    value = re.sub(r"(?im)^\s*[-*\u2022]+\s*", "", value)
    value = re.sub(r"(?im)^\s*\?\s*", "", value)
    value = value.replace("\u2014", "，")
    value = _sanitize_exposed_ids(value)
    value = re.sub(r"[\U0001F300-\U0001FAFF]", "", value)
    value = re.sub(r"[\u2600-\u27BF]", "", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip() if trim else value


def sanitize_user_output(text: str) -> str:
    return _sanitize_user_output_core(text, trim=True)


def _sanitize_user_output_fragment(text: str) -> str:
    return _sanitize_user_output_core(text, trim=False)


def _iter_sanitized_stream_chunks(chunks):
    buffer = ""
    reserve = 96
    hard_limit = 240
    emitted = False

    def normalize(fragment: str, *, final: bool) -> str:
        cleaned = sanitize_user_output(fragment) if final else _sanitize_user_output_fragment(fragment)
        if not emitted:
            cleaned = cleaned.lstrip()
        if final:
            cleaned = cleaned.rstrip()
        return cleaned

    for chunk in chunks:
        piece = str(chunk or "")
        if not piece:
            continue
        buffer += piece

        while True:
            flush_idx = 0
            if len(buffer) > reserve:
                search_end = len(buffer) - reserve
                matches = list(_STREAM_BOUNDARY_RE.finditer(buffer[:search_end]))
                if matches:
                    flush_idx = matches[-1].end()
                elif len(buffer) > hard_limit:
                    flush_idx = len(buffer) - reserve

            if flush_idx <= 0:
                break

            fragment = normalize(buffer[:flush_idx], final=False)
            buffer = buffer[flush_idx:]
            if not fragment:
                continue
            emitted = True
            yield fragment

    tail = normalize(buffer, final=True)
    if tail:
        yield tail


def _iter_output_chunks(text: str):
    value = str(text or "")
    if not value:
        return

    def iter_plain_chunks(plain_text: str):
        if not plain_text:
            return
        if len(plain_text) <= 16:
            yield plain_text
            return

        soft_limit = 20
        hard_limit = 40
        split_chars = {"\n", "。", "，", "！", "？", "；", "：", ",", ".", "!", "?", ";", ":"}
        buffer: list[str] = []
        for ch in plain_text:
            buffer.append(ch)
            current = "".join(buffer)
            if ch == "\n":
                yield current
                buffer = []
                continue
            if len(current) >= hard_limit:
                yield current
                buffer = []
                continue
            if len(current) >= soft_limit and ch in split_chars:
                yield current
                buffer = []
        if buffer:
            yield "".join(buffer)

    last = 0
    for match in _VISIBLE_URL_RE.finditer(value):
        prefix = value[last:match.start()]
        yield from iter_plain_chunks(prefix)
        url = match.group(0)
        if url:
            yield url
        last = match.end()

    suffix = value[last:]
    yield from iter_plain_chunks(suffix)


def _final_tool_name(tool_result: Any) -> str:
    if not isinstance(tool_result, dict):
        return ""
    final = tool_result.get("final")
    if not isinstance(final, dict):
        return ""
    return str(final.get("tool_name") or "").strip()


def _sanitize_internal_failure_text(tool_result: Any, text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return value

    lowered = value.lower()
    if not any(marker in lowered for marker in _INTERNAL_ERROR_MARKERS):
        return value

    friendly_map = {
        "recommend_songs": "暂时获取不到每日推荐歌曲，请稍后再试。",
        "personalized_newsong": "暂时获取不到个性化推荐新歌，请稍后再试。",
        "recommend_resource": "暂时获取不到每日推荐歌单，请稍后再试。",
        "personalized": "暂时获取不到个性化推荐歌单，请稍后再试。",
        "song_url_v1": "暂时获取不到歌曲播放地址，请稍后再试。",
        "song_download_url_v1": "暂时获取不到歌曲下载地址，请稍后再试。",
        "song_lyrics": "暂时获取不到这首歌的歌词，请稍后再试。",
    }
    return friendly_map.get(_final_tool_name(tool_result), "抱歉，刚刚后端服务出了点问题，请稍后再试。")


def _extract_raw_result(tool_result: Any) -> str:
    if isinstance(tool_result, str):
        return tool_result
    if not isinstance(tool_result, dict):
        return str(tool_result or "")

    final = tool_result.get("final")
    if isinstance(final, dict):
        result = final.get("result")
        return "" if result is None else str(result)
    if isinstance(final, str):
        return final
    return ""


@lru_cache(maxsize=1)
def _intent_agent():
    return get_intent_detection_agent()


@lru_cache(maxsize=1)
def _tool_executor():
    return get_tool_execution_agent()


def warm_agent_runtime() -> None:
    global _AGENT_RUNTIME_WARMED
    start_time = time.time()
    if _AGENT_RUNTIME_WARMED:
        return
    with _AGENT_RUNTIME_WARM_LOCK:
        if _AGENT_RUNTIME_WARMED:
            return
        try:
            _intent_agent()
            _tool_executor()
        except Exception:
            logger.exception("Agent runtime warmup failed")
            return
        _AGENT_RUNTIME_WARMED = True
        logger.info("Agent runtime warmup complete in %.2fs", time.time() - start_time)


def warm_agent_runtime_async() -> None:
    global _AGENT_RUNTIME_WARM_THREAD
    if _AGENT_RUNTIME_WARMED:
        return
    with _AGENT_RUNTIME_WARM_LOCK:
        if _AGENT_RUNTIME_WARMED:
            return
        if _AGENT_RUNTIME_WARM_THREAD is not None and _AGENT_RUNTIME_WARM_THREAD.is_alive():
            return
        _AGENT_RUNTIME_WARM_THREAD = threading.Thread(
            target=warm_agent_runtime,
            name="agent-runtime-warmup",
            daemon=True,
        )
        _AGENT_RUNTIME_WARM_THREAD.start()


def _normalize_plan(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()]
    if isinstance(value, str):
        text = str(value).strip()
        return [text] if text else []
    return []


def _normalize_extracted_params(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key).strip(): item
        for key, item in value.items()
        if str(key or "").strip() and item not in (None, "")
    }


def _normalize_possible_missing_params(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()]
    if isinstance(value, str):
        text = str(value).strip()
        return [text] if text else []
    return []


def _normalize_shortcut_query(text: str) -> str:
    value = str(text or "").strip().lower()
    if not value:
        return ""
    return _SHORTCUT_QUERY_NORMALIZE_RE.sub("", value)


def _assistant_intro_shortcut_reply(text: str) -> str | None:
    normalized = _normalize_shortcut_query(text)
    if not normalized:
        return None

    shortcut_patterns = (
        "你是谁",
        "你是谁呀",
        "你叫什么",
        "你叫什么名字",
        "介绍一下你自己",
        "介绍下你自己",
        "自我介绍",
        "你是谁开发的",
        "谁开发的你",
        "你是做什么的",
        "你能干嘛",
        "你能做什么",
        "你能做啥",
        "你会什么",
        "你有什么功能",
        "你能帮我什么",
        "音迹是什么",
        "小听是谁",
    )
    if len(normalized) > 36 and not normalized.startswith(
        ("你是谁", "你叫什么", "介绍", "自我介绍", "你能", "你会", "谁开发", "音迹", "小听")
    ):
        return None
    if any(pattern in normalized for pattern in shortcut_patterns):
        return ASSISTANT_INTRO_REPLY
    return None


def run_three_layer_agent(
    user_input: str,
    *,
    polish_model: str | None = None,
    event_cb: Optional[Callable[[dict], None]] = None,
    token_cb: Optional[Callable[[str], None]] = None,
) -> str:
    """主链路：查询改写 -> 工具执行 -> 输出返回。"""
    _configure_console_io()
    current_q = _extract_current_user_question(user_input)

    settings = get_llm_settings()
    if polish_model is None:
        polish_model = settings.model_for_task("polish")
    tracker = AgentRunTracker(event_cb=event_cb)

    def emit(event: str, **payload: Any) -> None:
        tracker.emit(event, **payload)

    logger.info("用户输入: %s", current_q or user_input)
    start_time = time.time()
    emit(
        "run_started",
        provider=settings.resolved_provider,
        intent_model=settings.model_for_task("intent"),
        tool_model=settings.model_for_task("tool"),
        polish_model=polish_model,
    )

    shortcut_reply = _assistant_intro_shortcut_reply(current_q or user_input)
    if shortcut_reply:
        logger.info("命中品牌直答: %s / %s", PROJECT_NAME, ASSISTANT_NAME)
        emit("stage", stage="intent_detection")
        emit(
            "intent",
            rewritten_query=current_q or user_input,
            plan=["直接回答助手身份与能力"],
            extracted_params={},
            possible_missing_params=[],
            route_source="identity_shortcut",
        )
        emit("stage", stage="output_return_raw")
        emit("polish", use_polish=False)

        full_content = sanitize_user_output(shortcut_reply)
        safe_print("\n[最终回答]: ", end="", flush=True)
        if token_cb:
            for piece in _iter_output_chunks(full_content):
                fragment = str(piece or "")
                if fragment:
                    token_cb(fragment)
        safe_print(full_content, end="", flush=True)

        duration = time.time() - start_time
        logger.info("总耗时: %.2fs", duration)
        emit("done", success=True, elapsed_ms=tracker.elapsed_ms())
        return full_content

    emit("stage", stage="intent_detection")
    tracker.thought("我先理解问题、补全上下文，再决定是否需要工具。", kind="plan")
    try:
        intent_result = _intent_agent()(user_input)
    except Exception as exc:
        logger.exception("意图识别失败")
        message = sanitize_user_output(f"抱歉，我在理解你的需求时遇到问题：{exc}")
        safe_print(f"\n[最终回答]: {message}")
        emit("done", success=False, error=str(exc))
        return message
    tracker.stage_done("intent_detection", label="意图识别完成")

    rewritten_query = str(intent_result.get("rewritten_query") or current_q or user_input).strip()
    plan = _normalize_plan(intent_result.get("plan"))
    extracted_params = _normalize_extracted_params(intent_result.get("extracted_params"))
    possible_missing_params = _normalize_possible_missing_params(intent_result.get("possible_missing_params"))
    logger.info("第一层改写结果: %s", json.dumps(intent_result, ensure_ascii=False))
    emit(
        "intent",
        rewritten_query=rewritten_query,
        plan=plan,
        extracted_params=extracted_params,
        possible_missing_params=possible_missing_params,
        route_source="llm",
    )

    emit("stage", stage="tool_execution")
    tracker.thought("我会优先调用明确匹配的音乐工具，必要时再检索更多工具。", kind="plan")
    try:
        tool_result = _tool_executor()(
            user_input=user_input,
            rewritten_query=rewritten_query,
            plan=plan,
            extracted_params=extracted_params,
            possible_missing_params=possible_missing_params,
            event_cb=event_cb,
        )
    except Exception as exc:
        logger.exception("工具执行失败")
        message = sanitize_user_output(f"抱歉，我在执行工具时遇到问题：{exc}")
        safe_print(f"\n[最终回答]: {message}")
        emit("done", success=False, error=str(exc))
        return message
    tracker.stage_done("tool_execution", label="工具执行完成")

    reflection = reflect_on_tool_result(tool_result, question=current_q or user_input)
    if reflection:
        emit("reflection", **reflection)
        tracker.thought(
            str(reflection.get("summary") or ""),
            kind="reflection",
            confidence=reflection.get("confidence"),
            need_retry=reflection.get("need_retry"),
        )

    executed_tool_names = [
        str(item.get("tool_name") or "").strip()
        for item in tool_result.get("tool_results", [])
        if isinstance(item, dict) and str(item.get("tool_name") or "").strip()
    ]
    if executed_tool_names:
        logger.info("工具调用链: %s", " -> ".join(executed_tool_names))

    final_tool_name = _final_tool_name(tool_result)
    if final_tool_name:
        logger.info("最终工具: %s", final_tool_name)

    client_action = extract_client_action(tool_result)
    if client_action:
        emit("client_action", payload=client_action)

    rich_content = extract_rich_content(tool_result)
    if rich_content:
        emit("rich_content", payload=rich_content)

    emit("stage", stage="output_polish_decide")
    structured_text = format_structured_output(tool_result) or ""
    raw_text = structured_text or _extract_raw_result(tool_result)
    if final_tool_name in _DIRECT_TEXT_TOOLS and structured_text:
        cleaned_raw = raw_text.rstrip()
    else:
        cleaned_raw = sanitize_user_output(raw_text)
        cleaned_raw = _sanitize_internal_failure_text(tool_result, cleaned_raw)
    use_polish = should_polish_response(cleaned_raw, tool_result)
    emit("polish", use_polish=bool(use_polish))
    tracker.stage_done("output_polish_decide", label="输出策略确定", use_polish=bool(use_polish))

    safe_print("\n[最终回答]: ", end="", flush=True)

    if not use_polish and cleaned_raw:
        emit("stage", stage="output_return_raw")
        full_content = cleaned_raw
        if token_cb:
            for piece in _iter_output_chunks(full_content):
                fragment = str(piece or "")
                if fragment:
                    token_cb(fragment)
    else:
        emit("stage", stage="output_polishing")
        pieces: list[str] = []
        stream = polish_with_guard_stream(tool_result, model=polish_model)

        if token_cb:
            def raw_stream():
                for piece in stream:
                    fragment = str(piece or "")
                    if not fragment:
                        continue
                    pieces.append(fragment)
                    yield fragment

            for safe_piece in _iter_sanitized_stream_chunks(raw_stream()):
                fragment = str(safe_piece or "")
                if fragment:
                    token_cb(fragment)
        else:
            for piece in stream:
                fragment = str(piece or "")
                if fragment:
                    pieces.append(fragment)

        full_content = "".join(pieces) if pieces else polish_with_guard(tool_result, model=polish_model)

    if final_tool_name in _DIRECT_TEXT_TOOLS and structured_text:
        full_content = str(full_content or "").rstrip()
    else:
        full_content = sanitize_user_output(full_content)
        full_content = _sanitize_internal_failure_text(tool_result, full_content)
    safe_print(full_content, end="", flush=True)

    duration = time.time() - start_time
    logger.info("总耗时: %.2fs", duration)
    emit("done", success=True, elapsed_ms=tracker.elapsed_ms())
    return full_content


if __name__ == "__main__":
    _configure_console_io()
    setup_logging()
    begin = time.time()
    for query in ["林俊杰有哪些专辑"]:
        run_three_layer_agent(query)
    logger.info("测试用例耗时: %.2fs", time.time() - begin)
