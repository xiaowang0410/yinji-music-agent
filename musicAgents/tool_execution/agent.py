import json
import logging
import os
import re
import subprocess
import sys
import time
from typing import Any

from tools.MusicTools.musicTools import liked_songs, send_text, user_detail, user_level, get_song_id, \
    song_download_url_v1, recommend_resource, personalized, personalized_newsong, user_playlist, get_mutual_follow_list, \
    toplist, top_song, search, song_details, song_lyrics, song_like, recommend_songs, follow, get_follow_list, \
    dj_sublist, playlist_create

# Add repository root to Python path for direct execution.
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from musicAgents.core.utils import get_llm

logger = logging.getLogger("musicAgents.tool_execution")

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MUSIC_TOOLS_MODULE = "tools.MusicTools.musicTools"
_ISOLATED_TOOL_TIMEOUT_SECONDS = 45
_ISOLATED_RESULT_PREFIX = "__CODEx_TOOL_RESULT__="


SYSTEM_PROMPT = (
    "你是音迹中的智能音乐助手小听的工具执行层，负责把问题真正执行到底。\n"
    "小听由小汪开发。如果用户在问你是谁、你叫什么、谁开发了你、你能做什么，可以直接自然回答，不需要调用任何工具。\n"
    
    "规则：\n"
    
    "对于非音乐问题，不需要调用任何工具，直接回答即可。\n"
    
    "对于音乐问题，不要轻易调用retrived_music_tool工具，如果已经能够解决问题了，就不需要调用这个工具了。\n"
    "retrived_music_tool工具是兜底，不要轻易使用一定不要轻易使用，只有当上面的工具不能满足需求时才调用。\n"
    
    "1. 当前用户问题和 rewritten_query 必须保持同一个目标；如果 rewritten_query 更清晰，应按 rewritten_query 执行，不要换题。\n"
    "2. plan、extracted_params、possible_missing_params 你可以利用这些信息，也可以忽略。\n"
    "3. 先根据当前问题和 rewritten_query 看已有的工具除（retrived_music_tool）外能否解决问题，如果不能，再用retrived_music_tool 检索辅助工具，去解决问题。\n"
    "4. 如果后续工具需要 id，而当前只有歌手名、专辑名、歌单名、用户名，就必须先解析出或者去检索工具获取真实 id，再调用下游工具；不要把名称直接塞进 id 参数。\n"
    "5. 如果出现多个候选实体，优先选择名称与用户请求最匹配的那个；不确定时继续查，不要乱试多个不相干 id 后直接收尾。\n"
    "6.retrived_music_tool工具是兜底，如果已经解决问题了，就不需要调用这个工具了，只有当上面的工具不能满足需求时才调用。\n"
    "7. 输入里可能包含完整会话历史、ASSISTANT_PAYLOAD 和 [ACTIVE_ENTITIES]，要利用这些上下文理解指代、省略和承接。\n"
    "\n"

    "以下是四个容易混淆的工具：你要注意这几个，不要搞混了，用户问哪个就返回哪个工具的结果。\n"
    "每日推荐歌曲，调用recommend_songs工具。\n"
    "每日推荐歌单，调用recommend_resource工具。\n"
    "个性化推荐歌单，调用personalized工具。\n"
    "个性化推荐歌曲，调用personalized_newsong工具。\n"

    "search工具一般只用一次，可以搜索音乐、专辑、歌手、歌单、用户。\n"
    "search工具，输入参数为key_word和type。传入搜索关键词  可以搜索音乐 type=1 / 专辑 type=10/ 歌手, type=100 / 歌单 type=1000/ 用户 type=1000,不需要输入用户id\n"

    "常见任务链路示例：\n"
    "1.我点赞/收藏/喜欢的歌曲，调用liked_songs工具。\n"
    "2.搜索单曲，歌手，某个人的专辑，我想听什么，你能放什么歌吗，调用search工具。\n"
    "3.每日推荐歌曲，调用recommend_songs工具。\n"
    "4.每日推荐歌单，调用recommend_resource工具。\n"
    "5.个性化推荐歌单，调用personalized工具。\n"
    "6.个性化推荐歌曲，调用personalized_newsong工具。\n"
    "7.获取歌曲歌词，调用song_lyrics工具。\n"
    "8.获取每日榜单，调用top_song工具。\n"
    "9.点赞/收藏/喜欢歌曲，调用song_like工具。\n"
    "10.关注用户，调用follow工具。\n"
    "11.获取关注用户列表，调用get_follow_list工具。\n"
    "12.获取收藏的电台列表，调用dj_sublist工具。\n"
    "13.给某人发私信，调用send_text工具。\n"


)

CURRENT_QUESTION_MARKER = "【当前用户问题】"
PLACEHOLDER_TOKENS = ("PREVIOUS_RESULT", "PLACEHOLDER_FOR_SONG_ID")
TRANSIENT_LLM_ERROR_MARKERS = (
    "ssl",
    "unexpected eof while reading",
    "max retries exceeded",
    "connection aborted",
    "connection reset",
    "timed out",
    "timeout",
    "temporarily unavailable",
    "service unavailable",
    "502 bad gateway",
    "503 service unavailable",
    "504 gateway timeout",
)
_NON_FINAL_TOOL_NAMES = {"retrived_music_tool"}
_ID_LIKE_ARG_KEYS = {"id", "song_id", "songId", "album_id", "playlist_id", "user_id", "artist_id", "uid"}


def _tool_module(tool: Any) -> str:
    func = getattr(tool, "func", None)
    return str(getattr(func, "__module__", "") or "").strip()


def _should_isolate_tool(tool: Any) -> bool:
    return _tool_module(tool) == _MUSIC_TOOLS_MODULE


def _summarize_worker_error(stderr: str, stdout: str) -> str:
    for value in (stderr, stdout):
        lines = [line.strip() for line in str(value or "").splitlines() if line.strip()]
        if lines:
            return lines[-1]
    return "isolated_tool_worker_failed"


def _run_isolated_music_tool(tool_name: str, tool_args: dict[str, Any]) -> Any:
    payload = json.dumps(
        {
            "tool_name": tool_name,
            "tool_args": tool_args,
        },
        ensure_ascii=False,
    )
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        completed = subprocess.run(
            [sys.executable, "-m", "musicAgents.tool_execution.isolated_music_tool_runner"],
            input=payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=_REPO_ROOT,
            env=env,
            timeout=_ISOLATED_TOOL_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"isolated_tool_timeout: {tool_name}") from exc
    except Exception as exc:
        raise RuntimeError(f"isolated_tool_spawn_failed: {tool_name}: {exc}") from exc

    stdout = str(completed.stdout or "")
    stderr = str(completed.stderr or "").strip()

    marker_index = stdout.rfind(_ISOLATED_RESULT_PREFIX)
    if marker_index < 0:
        detail = _summarize_worker_error(stderr, stdout)
        raise RuntimeError(f"isolated_tool_empty_response: {tool_name}: {detail}")

    payload_text = stdout[marker_index + len(_ISOLATED_RESULT_PREFIX) :].strip()

    try:
        worker_payload = json.loads(payload_text)
    except Exception as exc:
        detail = _summarize_worker_error(stderr, stdout)
        raise RuntimeError(f"isolated_tool_invalid_response: {tool_name}: {detail}") from exc

    if completed.returncode != 0:
        detail = _summarize_worker_error(stderr, stdout)
        raise RuntimeError(f"isolated_tool_worker_crashed: {tool_name}: {detail}")

    if not bool(worker_payload.get("success")):
        detail = str(worker_payload.get("error") or _summarize_worker_error(stderr, stdout)).strip()
        raise RuntimeError(f"isolated_tool_execution_failed: {tool_name}: {detail}")

    return worker_payload.get("result")


def _current_question(text: str) -> str:
    if not isinstance(text, str):
        return ""
    if CURRENT_QUESTION_MARKER not in text:
        return text.strip()
    tail = text.split(CURRENT_QUESTION_MARKER)[-1]
    return (tail or "").strip()


def _safe_dumps(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return str(obj)


def _tool_id(tool: Any) -> str:
    return getattr(tool, "name", getattr(tool, "__name__", str(tool)))


def _extract_first_song_id(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return str(int(value))
    if isinstance(value, str):
        text = value.strip().strip('"').strip("'")
        return text if text.isdigit() else None
    if isinstance(value, dict):
        for key in ("歌曲ID", "song_id", "songId", "id"):
            resolved = _extract_first_song_id(value.get(key))
            if resolved:
                return resolved
        for key in ("匹配歌曲", "songs", "data"):
            resolved = _extract_first_song_id(value.get(key))
            if resolved:
                return resolved
        return None
    if isinstance(value, list):
        for item in value:
            resolved = _extract_first_song_id(item)
            if resolved:
                return resolved
    return None


def _looks_like_unresolved_id_value(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return False

    text = str(value).strip().strip('"').strip("'")
    if not text:
        return False
    if text.isdigit():
        return False
    if any(token in text for token in PLACEHOLDER_TOKENS):
        return True
    return bool(re.search(r"[\u4e00-\u9fffA-Za-z]", text))


def _find_unresolved_id_arg(tool_args: dict[str, Any]) -> tuple[str, Any] | None:
    if not isinstance(tool_args, dict):
        return None
    for key, value in tool_args.items():
        if str(key) in _ID_LIKE_ARG_KEYS and _looks_like_unresolved_id_value(value):
            return str(key), value
    return None

def _normalize_tool_args(tool_name: str, tool_args: Any, last_song_id: str | None) -> dict[str, Any]:
    if not isinstance(tool_args, dict):
        return {}

    normalized = {
        str(key): value.strip() if isinstance(value, str) else value
        for key, value in dict(tool_args).items()
    }
    id_keys = ("id", "song_id", "songId")

    if tool_name == "search":
        if "keywords" not in normalized:
            for key in ("keyword", "query", "text", "name"):
                candidate = normalized.get(key)
                if candidate is None:
                    continue
                text = str(candidate).strip()
                if text:
                    normalized["keywords"] = text
                    break
        if normalized.get("keywords") is not None:
            normalized["keywords"] = str(normalized.get("keywords")).strip()
        raw_type = normalized.get("type")
        if isinstance(raw_type, bool):
            normalized.pop("type", None)
        elif isinstance(raw_type, (int, float)):
            normalized["type"] = int(raw_type)
        elif isinstance(raw_type, str):
            type_text = raw_type.strip()
            if not type_text:
                normalized.pop("type", None)
            elif type_text.isdigit():
                normalized["type"] = int(type_text)
            else:
                normalized["type"] = type_text
        return normalized

    if tool_name in {"send_text", "send_song", "send_album", "send_playlist"}:
        raw_user_ids = normalized.get("user_ids")
        if raw_user_ids is None:
            raw_user_ids = normalized.get("user_id")
        if raw_user_ids is None:
            raw_user_ids = normalized.get("uid")

        if raw_user_ids is not None:
            if not isinstance(raw_user_ids, list):
                raw_user_ids = [raw_user_ids]
            cleaned_user_ids = []
            for item in raw_user_ids:
                if item is None:
                    continue
                if isinstance(item, (int, float)):
                    cleaned_user_ids.append(str(int(item)))
                    continue
                text = str(item).strip()
                if text:
                    cleaned_user_ids.append(text)
            if cleaned_user_ids:
                normalized["user_ids"] = cleaned_user_ids

        if "msg" not in normalized:
            message_value = normalized.get("message")
            if message_value is None:
                message_value = normalized.get("content")
            if message_value is not None:
                normalized["msg"] = str(message_value)

        if tool_name == "send_playlist" and "playlist" not in normalized and normalized.get("id") is not None:
            normalized["playlist"] = normalized.get("id")

        return normalized

    if tool_name in {"song_like", "song_lyrics", "song_url_v1", "song_download_url_v1"}:
        raw_id = None
        for key in id_keys:
            if key in normalized:
                raw_id = normalized.get(key)
                break

        resolved_id = _extract_first_song_id(raw_id)
        if isinstance(raw_id, str) and any(token in raw_id for token in PLACEHOLDER_TOKENS):
            resolved_id = None

        if resolved_id:
            if tool_name == "song_lyrics":
                normalized["song_id"] = resolved_id
                normalized.pop("id", None)
            else:
                normalized["id"] = resolved_id
            return normalized

        if last_song_id:
            if tool_name == "song_lyrics":
                normalized["song_id"] = last_song_id
                normalized.pop("id", None)
            else:
                normalized["id"] = last_song_id
        return normalized

    for key, value in list(normalized.items()):
        if isinstance(value, str) and any(token in value for token in PLACEHOLDER_TOKENS) and last_song_id:
            normalized[key] = last_song_id
    return normalized


def _is_success(tool_name: str, result: Any) -> bool:
    if result is None:
        return False
    if tool_name == "song_like":
        return isinstance(result, str) and "成功" in result
    if isinstance(result, str):
        text = result.lower()
        bad_markers = ("失败", "错误", "[err]", "exception", "traceback", "access violation")
        return not any(marker in text for marker in bad_markers)
    if isinstance(result, dict) and result.get("error"):
        return False
    return True


def _looks_like_transient_llm_error(exc: Any) -> bool:
    text = str(exc or "").strip().lower()
    if not text:
        return False
    return any(marker in text for marker in TRANSIENT_LLM_ERROR_MARKERS)


def get_tool_execution_agent():
    """Return the tool execution callable."""
    llm = get_llm(model="qwen-max")

    from RagService.ToolRag.text_to_tools import getTools
    from RagService.ragService import retrived_music_tool

    base_tools = [

        user_detail,
        user_level,
        search,
        get_song_id,
        song_details,
        song_lyrics,
        song_like,
        recommend_songs,
        recommend_resource,
        personalized,
        personalized_newsong,
        toplist,
        top_song,
        user_playlist,
        send_text,
        follow,
        get_mutual_follow_list,
        get_follow_list,
        dj_sublist  ,
        playlist_create,
        retrived_music_tool
    ]
    try:
        for tool in getTools(["search"]):
            if _tool_id(tool) not in {_tool_id(item) for item in base_tools}:
                base_tools.append(tool)
    except Exception:
        logger.exception("Failed to preload search tool")

    def execute_tools(
        user_input: str,
        rewritten_query: str,
        plan: list[str] | None = None,
        extracted_params: dict[str, Any] | None = None,
        possible_missing_params: list[str] | None = None,
        event_cb=None,
    ):
        tool_results: list[dict[str, Any]] = []

        def emit(event: str, **payload: Any) -> None:
            if event_cb is None:
                return
            try:
                event_cb({"event": event, **payload})
            except Exception:
                pass

        def ensure_loaded(tool_names: list[str], available_tools: list[Any], loaded_names: set[str]) -> None:
            pending = [name for name in tool_names if str(name or "").strip() and str(name).strip() not in loaded_names]
            if not pending:
                return
            emit("tools_preload", suggested_tools=pending)
            load_tools(pending, available_tools, loaded_names)

        def load_tools(tool_names: list[str], available_tools: list[Any], loaded_names: set[str]) -> bool:
            names = [str(name or "").strip() for name in tool_names if str(name or "").strip()]
            names = [name for name in names if name not in loaded_names]
            if not names:
                return False

            new_tools = getTools(names)
            changed = False
            for tool in new_tools:
                tool_name = _tool_id(tool)
                if tool_name in loaded_names:
                    continue
                available_tools.append(tool)
                loaded_names.add(tool_name)
                changed = True
            return changed

        def run_tool(available_tools: list[Any], tool_name: str, tool_args: dict[str, Any]):
            tool = next((item for item in available_tools if _tool_id(item) == tool_name), None)
            if tool is None:
                raise ValueError(f"tool_not_found: {tool_name}")

            logger.info("第二层调用工具: %s | args=%s", tool_name, _safe_dumps(tool_args))
            emit("tool_start", tool_name=tool_name, args=tool_args)
            try:
                if _should_isolate_tool(tool):
                    result = _run_isolated_music_tool(tool_name, tool_args)
                else:
                    result = tool.invoke(tool_args)
                success = _is_success(tool_name, result)
                logger.info("第二层工具完成: %s | success=%s", tool_name, success)
                emit("tool_end", tool_name=tool_name, success=success)
            except Exception:
                logger.exception("第二层工具异常: %s", tool_name)
                emit("tool_end", tool_name=tool_name, success=False)
                raise

            result_text = _safe_dumps(result)[:12000]
            tool_results.append(
                {
                    "tool_name": tool_name,
                    "args": tool_args,
                    "success": success,
                    "result": result_text,
                }
            )
            return tool, result, success, result_text

        try:
            from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage

            full_context = str(user_input or "").strip()
            current_q = _current_question(user_input)
            prompt_input = current_q or full_context
            normalized_plan = [str(item).strip() for item in (plan or []) if str(item or "").strip()]
            normalized_extracted_params = dict(extracted_params or {})
            normalized_missing_params = [str(item).strip() for item in (possible_missing_params or []) if str(item or "").strip()]
            messages: list[BaseMessage] = [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(
                    content=(
                        "以下是完整会话上下文，请优先处理【当前用户问题】，"
                        "但必须结合历史、ASSISTANT_PAYLOAD 和 [ACTIVE_ENTITIES] 来理解代词、承接和省略。\n\n"
                        f"{full_context or prompt_input}\n\n"
                        f"上游改写问题参考: {rewritten_query or prompt_input}\n"
                        f"上游步骤参考（可能不准确）: {_safe_dumps(normalized_plan)}\n"
                        f"上游已提取参数参考（可能不准确）: {_safe_dumps(normalized_extracted_params)}\n"
                        f"上游可能缺失参数参考（可能不准确）: {_safe_dumps(normalized_missing_params)}"
                    )
                ),
            ]

            available_tools = list(base_tools)
            loaded_tool_names = {_tool_id(tool) for tool in available_tools}
            emit("route_selected", route="direct", name="base_tools")

            tools_signature = tuple(sorted(loaded_tool_names))
            llm_with_tools = llm.bind_tools(available_tools)

            last_song_id: str | None = None
            last_successful: dict[str, Any] | None = None

            for _ in range(4):
                new_signature = tuple(sorted(_tool_id(tool) for tool in available_tools))
                if new_signature != tools_signature:
                    tools_signature = new_signature
                    llm_with_tools = llm.bind_tools(available_tools)

                response = None
                last_llm_exc = None
                for attempt in range(2):
                    try:
                        response = llm_with_tools.invoke(messages)
                        break
                    except Exception as exc:
                        last_llm_exc = exc
                        if attempt == 0 and _looks_like_transient_llm_error(exc):
                            logger.warning("Transient LLM tool-call error, retrying once: %s", exc)
                            time.sleep(0.8)
                            continue
                        break

                if response is None:
                    raise last_llm_exc or RuntimeError("tool_execution_llm_no_response")

                messages.append(response)

                if not response.tool_calls:
                    content = response.content if hasattr(response, "content") else str(response)
                    if last_successful is not None:
                        return {"final": last_successful, "tool_results": tool_results}
                    if any(
                        bool(item.get("success")) and str(item.get("tool_name") or "") in _NON_FINAL_TOOL_NAMES
                        for item in tool_results
                    ):
                        messages.append(
                            HumanMessage(
                                content=(
                                    "你目前只有工具检索结果，还没有拿到真正业务数据。"
                                    "请继续调用已加载的数据工具完成任务；如果下游工具需要 id，请先解析出真实数字 id，再继续。"
                                )
                            )
                        )
                        continue
                    return {"final": content, "tool_results": tool_results}

                for tool_call in response.tool_calls:
                    tool_name = str(tool_call.get("name") or "").strip()
                    tool_args = _normalize_tool_args(tool_name, tool_call.get("args"), last_song_id)
                    tool = next((item for item in available_tools if _tool_id(item) == tool_name), None)

                    if tool is None:
                        messages.append(
                            ToolMessage(
                                content=f"工具未找到: {tool_name or 'unknown_tool'}",
                                name=tool_name or "unknown_tool",
                                tool_call_id=tool_call["id"],
                            )
                        )
                        continue

                    unresolved_id = _find_unresolved_id_arg(tool_args)
                    if unresolved_id is not None:
                        bad_key, bad_value = unresolved_id
                        messages.append(
                            ToolMessage(
                                content=(
                                    f"参数 {bad_key} 当前值 {bad_value!r} 不是可执行的真实 id。"
                                    "请先通过搜索、实体查询或已有结果拿到匹配实体的真实数字 id，再继续调用该工具。"
                                ),
                                name=tool_name,
                                tool_call_id=tool_call["id"],
                            )
                        )
                        continue

                    try:
                        _, result, success, result_text = run_tool(available_tools, tool_name, tool_args)
                    except Exception as exc:
                        logger.exception("Tool invocation failed: %s", tool_name)
                        messages.append(
                            ToolMessage(content=f"工具执行异常: {exc}", name=tool_name, tool_call_id=tool_call["id"])
                        )
                        continue

                    if tool_name == "retrived_music_tool" and isinstance(result, list):
                        loaded = load_tools(
                            [str(name or "").strip() for name in result if str(name or "").strip()],
                            available_tools,
                            loaded_tool_names,
                        )
                        if loaded:
                            result_text = f"已加载工具: {', '.join([str(name) for name in result])}"

                    if tool_name in {"get_song_id", "search"}:
                        resolved_song_id = _extract_first_song_id(result)
                        if resolved_song_id:
                            last_song_id = resolved_song_id

                    if success and tool_name not in _NON_FINAL_TOOL_NAMES:
                        last_successful = {"tool_name": tool_name, "args": tool_args, "result": result}

                    messages.append(ToolMessage(content=result_text, name=tool_name, tool_call_id=tool_call["id"]))

            if last_successful is not None:
                return {"final": last_successful, "tool_results": tool_results}
            return {"final": "未能获取到有效结果。", "tool_results": tool_results}
        except Exception as exc:
            logger.exception("工具执行层出错")
            return {"error": str(exc), "tool_results": tool_results}

    return execute_tools



if __name__ == "__main__":
    agent =get_tool_execution_agent()

    print(agent("我想听起风了", '搜索歌曲《起风了》',  ['调用search工具搜索歌曲，类型为单曲'],   {'key_word': '起风了', 'type': '单曲'}, []))
