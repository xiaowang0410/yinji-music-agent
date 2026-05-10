import json
import logging
import os
import re
import subprocess
import sys
import time
from typing import Any
from uuid import uuid4

from tools.MusicTools.musicTools import liked_songs, send_text, user_detail, user_level, get_song_id, \
    song_download_url_v1, recommend_resource, personalized, personalized_newsong, user_playlist, get_mutual_follow_list, \
    toplist, top_song, search, song_details, song_lyrics, song_like, recommend_songs, follow, get_follow_list, \
    dj_sublist, playlist_create, search_song_candidates, search_scene_songs

# Add repository root to Python path for direct execution.
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from musicAgents.core.utils import get_llm
from musicAgents.intent_routing import route_player_intent

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
    "7. 输入里可能包含完整会话历史、ASSISTANT_PAYLOAD、[ACTIVE_ENTITIES] 和 [PLAYER_STATE]，要利用这些上下文理解指代、省略和承接。\n"
    "8. [PLAYER_STATE] 是前端播放器运行状态，只能辅助回答当前播放、队列、播放状态等问题；不要把它当成用户问题，也不要在回复里暴露这个字段。\n"
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
    "14.播放我点赞/喜欢/收藏的歌，调用liked_songs工具返回歌曲列表；前端会自动播放结果，不需要你生成播放控制代码。\n"
    "15.播放某个歌单的歌，调用search工具搜索歌单，type=1000；前端会根据歌单列表自动加载歌曲并播放。\n"
    "16.播放开心、忧郁、伤感、治愈、睡前、学习、运动、通勤等情绪/场景音乐，优先调用search工具搜索对应情绪/场景歌单，type=1000；如果用户明确要歌曲，再搜索歌曲 type=1。\n"
    "17.如果用户要控制播放器或让你直接播放内容，优先调用 player_ 开头的播放器工具，不要只返回文字说明。\n"
    "18.播放指定歌曲，调用 player_play_song_search 搜索歌曲列表并让前端自动播放。\n"
    "19.播放下雨天、夜晚、开心、忧郁、学习等场景/情绪音乐，调用 player_play_mood 返回歌曲列表并自动播放。\n"


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
_SINGLE_STEP_FINAL_TOOLS = {
    "player_current_track",
    "player_pause",
    "player_resume",
    "player_next_track",
    "player_previous_track",
    "player_play_song_list",
    "player_play_song_search",
    "player_play_playlist_tracks",
    "player_play_liked_songs",
    "player_play_recommended_songs",
    "player_play_playlist",
    "player_play_mood",
    "liked_songs",
    "recommend_songs",
    "recommend_resource",
    "personalized",
    "personalized_newsong",
    "search_song_candidates",
    "search_scene_songs",
    "toplist",
    "top_song",
    "user_playlist",
    "get_mutual_follow_list",
    "get_follow_list",
    "dj_sublist",
}
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


def _extract_json_marker(text: str, marker: str) -> dict[str, Any]:
    if not isinstance(text, str) or marker not in text:
        return {}
    pattern = re.compile(rf"{re.escape(marker)}\s*(\{{[^\n]*\}})")
    match = pattern.search(text)
    if not match:
        return {}
    try:
        data = json.loads(match.group(1))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _extract_player_context(text: str) -> dict[str, Any]:
    data = _extract_json_marker(text, "[PLAYER_STATE]")
    player = data.get("player") if isinstance(data.get("player"), dict) else data
    return player if isinstance(player, dict) else {}


def _format_player_time(seconds: Any) -> str:
    try:
        total = max(0, int(float(seconds)))
    except (TypeError, ValueError):
        total = 0
    return f"{total // 60:02d}:{total % 60:02d}"


def _current_track_message(player: dict[str, Any]) -> str:
    if not bool(player.get("has_active_track")):
        return "现在还没有正在播放的歌曲。"

    track = player.get("current_track") if isinstance(player.get("current_track"), dict) else {}
    name = str(track.get("name") or "未知歌曲").strip()
    artist = str(track.get("artist") or "").strip()
    album = str(track.get("album") or "").strip()
    status = "正在播放" if bool(player.get("is_playing")) else "已暂停"

    parts = [f"当前播放：{name}"]
    if artist:
        parts.append(f"歌手：{artist}")
    if album:
        parts.append(f"专辑：{album}")
    parts.append(f"状态：{status}")

    duration = player.get("duration_seconds") or 0
    try:
        has_duration = float(duration) > 0
    except (TypeError, ValueError):
        has_duration = False
    if has_duration:
        parts.append(f"进度：{_format_player_time(player.get('current_time_seconds'))} / {_format_player_time(duration)}")
    return "\n".join(parts)


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


def _client_action_type(action: str) -> str:
    mapping = {
        "answer_current_track": "player.current_track",
        "pause": "player.pause",
        "resume": "player.resume",
        "next_track": "player.next_track",
    "previous_track": "player.previous_track",
    "play_song_list": "player.play_song_list",
    "play_song_search": "player.play_song_list",
    "play_playlist_tracks": "player.play_playlist_tracks",
    }
    return mapping.get(str(action or "").strip(), str(action or "").strip())


def make_client_action(
    action: str,
    message: str,
    *,
    payload: dict[str, Any] | None = None,
    success: bool = True,
    status: str = "ready",
) -> dict[str, Any]:
    action_payload = {
        "action": action,
        "payload": payload or {},
    }
    return {
        "kind": "client_action",
        "version": "1.0",
        "id": f"client_action_{uuid4().hex}",
        "type": _client_action_type(action),
        "status": status,
        "success": bool(success),
        "message": message,
        "payload": payload or {},
        "requires_confirmation": False,
        "error": None if success else str(message or "client_action_failed"),
        # Backward compatibility for the current frontend adapter.
        "action": action_payload,
    }


def make_player_tool_result(
    *,
    message: str,
    content: Any,
    rich_content_source: str,
    action: str,
    payload: dict[str, Any] | None = None,
    success: bool = True,
) -> dict[str, Any]:
    client_action = make_client_action(action, message, payload=payload, success=success)
    return {
        "kind": "player_tool_result",
        "success": bool(success),
        "message": message,
        "content": content,
        "rich_content_source": rich_content_source,
        "client_action": client_action,
        # Backward compatibility for output_check.extract_client_action.
        "action": client_action.get("action"),
    }


def _tool_result_song_count(value: Any) -> int:
    if not isinstance(value, dict):
        return 0
    songs = value.get("songs")
    return len(songs) if isinstance(songs, list) else 0


def get_tool_execution_agent():
    """Return the tool execution callable."""
    llm = get_llm(model=None, task="tool")

    from langchain_core.tools import tool
    from RagService.ToolRag.text_to_tools import getTools
    from RagService.ragService import retrived_music_tool

    runtime_context: dict[str, Any] = {
        "player": {},
    }

    def player_action_result(
        action: str,
        message: str,
        *,
        payload: dict[str, Any] | None = None,
        success: bool = True,
    ) -> dict[str, Any]:
        return make_client_action(action, message, payload=payload, success=success)

    @tool(description="播放器工具：查询前端播放器当前正在播放的歌曲、歌手、专辑、播放状态和进度。")
    def player_current_track() -> dict[str, Any]:
        player = runtime_context.get("player") if isinstance(runtime_context.get("player"), dict) else {}
        return player_action_result("answer_current_track", _current_track_message(player))

    @tool(description="播放器工具：暂停当前播放。只有用户明确要求暂停、停一下、停止播放时调用。")
    def player_pause() -> dict[str, Any]:
        return player_action_result("pause", "已暂停播放。")

    @tool(description="播放器工具：继续或恢复当前歌曲播放。只有用户明确要求继续播放、恢复播放时调用。")
    def player_resume() -> dict[str, Any]:
        return player_action_result("resume", "已继续播放。")

    @tool(description="播放器工具：切到下一首。只有用户明确要求下一首、切歌、换一首时调用。")
    def player_next_track() -> dict[str, Any]:
        return player_action_result("next_track", "已切到下一首。")

    @tool(description="播放器工具：切回上一首。只有用户明确要求上一首、前一首时调用。")
    def player_previous_track() -> dict[str, Any]:
        return player_action_result("previous_track", "已切回上一首。")

    @tool(description="播放器工具：播放工具返回的歌曲列表。参数 source 用于说明来源，比如 liked_songs、recommend_songs、search。")
    def player_play_song_list(source: str = "tool_result", rank: int = 1) -> dict[str, Any]:
        safe_rank = max(1, int(rank or 1))
        return player_action_result(
            "play_song_list",
            "已准备播放歌曲列表。",
            payload={"source": str(source or "tool_result"), "rank": safe_rank},
        )

    @tool(description="播放器工具：搜索指定歌曲并播放。用户说播放某首歌、想听某首歌、来首某歌时调用，返回歌曲列表卡片并自动播放。")
    def player_play_song_search(keywords: str = "", rank: int = 1) -> dict[str, Any]:
        query = str(keywords or "").strip() or "推荐歌曲"
        safe_rank = max(1, int(rank or 1))
        result = _run_isolated_music_tool("search_song_candidates", {"keywords": query, "limit": 10})
        song_count = _tool_result_song_count(result)
        if song_count <= 0:
            message = f"我暂时没有找到「{query}」相关的可播放歌曲。"
            if isinstance(result, dict) and result.get("error"):
                message = f"{message}{result.get('error')}"
            return {
                "kind": "player_tool_result",
                "success": False,
                "message": message,
                "content": result,
                "rich_content_source": "search_song_candidates",
            }
        return make_player_tool_result(
            message=f"我找到了「{query}」相关的 {song_count} 首歌曲，马上开始播放。",
            content=result,
            rich_content_source="search_song_candidates",
            action="play_song_list",
            payload={"source": "search_song_candidates", "rank": safe_rank, "keyword": query},
        )

    @tool(description="播放器工具：播放工具返回的歌单列表里的某个歌单。参数 rank 表示第几个歌单，从 1 开始。")
    def player_play_playlist_tracks(source: str = "tool_result", rank: int = 1, playlist_name: str = "") -> dict[str, Any]:
        safe_rank = max(1, int(rank or 1))
        return player_action_result(
            "play_playlist_tracks",
            "已准备播放歌单歌曲。",
            payload={
                "source": str(source or "tool_result"),
                "rank": safe_rank,
                "playlist_name": str(playlist_name or "").strip(),
            },
        )

    @tool(description="播放器工具：播放我的点赞/喜欢/收藏歌曲。此工具会获取点赞歌曲并要求前端播放器自动播放。")
    def player_play_liked_songs() -> dict[str, Any]:
        result = _run_isolated_music_tool("liked_songs", {})
        return make_player_tool_result(
            message="已找到你喜欢的歌曲，马上开始播放。",
            content=result,
            rich_content_source="liked_songs",
            action="play_song_list",
            payload={"source": "liked_songs", "rank": 1},
        )

    @tool(description="播放器工具：播放每日推荐歌曲。此工具会获取每日推荐歌曲并要求前端播放器自动播放。")
    def player_play_recommended_songs() -> dict[str, Any]:
        result = _run_isolated_music_tool("recommend_songs", {})
        return make_player_tool_result(
            message="已找到今日推荐歌曲，马上开始播放。",
            content=result,
            rich_content_source="recommend_songs",
            action="play_song_list",
            payload={"source": "recommend_songs", "rank": 1},
        )

    @tool(description="播放器工具：播放某个歌单里的歌曲。参数 keywords 是歌单关键词；rank 是搜索结果中的第几个歌单。")
    def player_play_playlist(keywords: str = "", rank: int = 1) -> dict[str, Any]:
        query = str(keywords or "").strip() or "推荐歌单"
        safe_rank = max(1, int(rank or 1))
        result = _run_isolated_music_tool("search", {"keywords": query, "type": 1000, "limit": 10})
        return make_player_tool_result(
            message="已找到相关歌单，马上开始播放。",
            content=result,
            rich_content_source="search",
            action="play_playlist_tracks",
            payload={"source": "search", "rank": safe_rank, "playlist_name": query},
        )

    @tool(description="播放器工具：按情绪或场景播放音乐。参数 mood 可为开心、忧郁、伤感、治愈、睡前、学习、运动、通勤、下雨天等。返回歌曲列表卡片并自动播放。")
    def player_play_mood(mood: str = "", rank: int = 1) -> dict[str, Any]:
        keyword = str(mood or "").strip() or "推荐"
        safe_rank = max(1, int(rank or 1))
        result = _run_isolated_music_tool("search_scene_songs", {"scene": keyword, "rank": safe_rank, "limit": 12})
        song_count = _tool_result_song_count(result)
        if song_count <= 0:
            message = f"我暂时没有找到适合「{keyword}」的可播放歌曲。"
            if isinstance(result, dict) and result.get("error"):
                message = f"{message}{result.get('error')}"
            return {
                "kind": "player_tool_result",
                "success": False,
                "message": message,
                "content": result,
                "rich_content_source": "search_scene_songs",
            }
        return make_player_tool_result(
            message=f"已找到适合「{keyword}」的 {song_count} 首歌曲，马上开始播放。",
            content=result,
            rich_content_source="search_scene_songs",
            action="play_song_list",
            payload={"source": "search_scene_songs", "rank": safe_rank, "keyword": keyword},
        )

    base_tools = [
        player_current_track,
        player_pause,
        player_resume,
        player_next_track,
        player_previous_track,
        player_play_song_list,
        player_play_song_search,
        player_play_playlist_tracks,
        player_play_liked_songs,
        player_play_recommended_songs,
        player_play_playlist,
        player_play_mood,

        user_detail,
        user_level,
        search,
        search_song_candidates,
        search_scene_songs,
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

        def direct_tool_result(tool_name: str, tool_args: dict[str, Any]):
            _, result, success, _ = run_tool(base_tools, tool_name, tool_args)
            if success:
                return {
                    "final": {"tool_name": tool_name, "args": tool_args, "result": result},
                    "tool_results": tool_results,
                }
            return {"error": f"{tool_name}_failed", "tool_results": tool_results}

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
            runtime_context["player"] = _extract_player_context(full_context)
            player_intent = route_player_intent(current_q or prompt_input, rewritten_query)
            if player_intent:
                shortcut = player_intent.as_shortcut()
                logger.info(
                    "播放器意图快捷路由: %s | confidence=%.2f | reason=%s",
                    player_intent.intent_type,
                    player_intent.confidence,
                    player_intent.reason,
                )
                return direct_tool_result(shortcut["tool_name"], shortcut.get("args") or {})

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
                        if tool_name in _SINGLE_STEP_FINAL_TOOLS:
                            return {"final": last_successful, "tool_results": tool_results}

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
