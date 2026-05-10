import json
import os
import queue
import re
import requests
import sys
import threading
import time
from queue import Empty
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel

_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from .agent_store import Conversation, Message, store

router = APIRouter()
_SONG_ENDPOINT_LOCK = threading.RLock()
_MEMORY_SUMMARY_LOCKS: dict[str, threading.Lock] = {}
_MEMORY_SUMMARY_LOCKS_GUARD = threading.Lock()

DEFAULT_CONVERSATION_TITLE = "和小听聊聊"

STAGE_CATALOG = [
    {
        "key": "intent_detection",
        "label": "理解需求",
        "description": "分析你的问题并识别需要的能力",
    },
    {
        "key": "tool_execution",
        "label": "执行工具",
        "description": "调用后端工具和服务获取真实数据",
    },
    {
        "key": "output_polish_decide",
        "label": "整理结果",
        "description": "判断直接返回还是继续润色输出",
    },
    {
        "key": "output_return_raw",
        "label": "直接返回",
        "description": "结果已足够清晰，直接同步输出",
    },
    {
        "key": "output_polishing",
        "label": "流式生成",
        "description": "把最终回答按增量流式输出到前端",
    },
]
STAGE_META_BY_KEY = {item["key"]: item for item in STAGE_CATALOG}


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    client_context: Optional[Dict[str, Any]] = None


class CreateConversationRequest(BaseModel):
    title: Optional[str] = None


class UpdateConversationRequest(BaseModel):
    title: str


def _default_title_from_message(message: str) -> str:
    text = (message or "").strip()
    if not text:
        return DEFAULT_CONVERSATION_TITLE
    return text[:20]


def _compact_payload_for_history(payload: Any) -> Optional[dict]:
    if not isinstance(payload, dict):
        return None

    kind = str(payload.get("kind") or "").strip()
    title = str(payload.get("title") or "").strip()
    summary = str(payload.get("summary") or "").strip()
    total = payload.get("total")
    raw_items = payload.get("items")
    items = raw_items if isinstance(raw_items, list) else []

    if kind == "song_list":
        compact_items = []
        for item in items[:5]:
            if not isinstance(item, dict):
                continue
            compact_items.append(
                {
                    "id": str(item.get("id") or "").strip(),
                    "name": str(item.get("name") or "").strip(),
                    "artist": str(item.get("artist") or "").strip(),
                    "album": str(item.get("album") or "").strip(),
                }
            )
        return {
            "kind": kind,
            "title": title,
            "summary": summary,
            "total": total,
            "items": compact_items,
        }

    if kind == "playlist_list":
        compact_items = []
        for item in items[:5]:
            if not isinstance(item, dict):
                continue
            compact_items.append(
                {
                    "id": str(item.get("id") or "").strip(),
                    "name": str(item.get("name") or "").strip(),
                    "track_count": item.get("track_count"),
                }
            )
        return {
            "kind": kind,
            "title": title,
            "summary": summary,
            "total": total,
            "items": compact_items,
        }

    if kind == "album_list":
        compact_items = []
        for item in items[:5]:
            if not isinstance(item, dict):
                continue
            compact_items.append(
                {
                    "id": str(item.get("id") or "").strip(),
                    "name": str(item.get("name") or "").strip(),
                    "artist": str(item.get("artist") or "").strip(),
                    "publish_time": str(item.get("publish_time") or "").strip(),
                }
            )
        return {
            "kind": kind,
            "title": title,
            "summary": summary,
            "total": total,
            "items": compact_items,
        }

    if kind == "contact_list":
        compact_items = []
        for item in items[:5]:
            if not isinstance(item, dict):
                continue
            compact_items.append(
                {
                    "id": str(item.get("id") or "").strip(),
                    "name": str(item.get("name") or "").strip(),
                    "remarkName": str(item.get("remarkName") or "").strip(),
                }
            )
        return {
            "kind": kind,
            "title": title,
            "summary": summary,
            "total": total,
            "items": compact_items,
        }

    return None


def _build_active_entities(history: List[dict]) -> dict:
    active_entities: dict[str, dict] = {}
    entity_key_by_kind = {
        "song_list": "song",
        "playlist_list": "playlist",
        "album_list": "album",
        "contact_list": "user",
    }

    for item in reversed(history):
        if item.get("role") != "assistant":
            continue
        payload = _compact_payload_for_history(item.get("payload"))
        if not payload:
            continue

        entity_key = entity_key_by_kind.get(str(payload.get("kind") or "").strip())
        if not entity_key or entity_key in active_entities:
            continue

        entities = payload.get("items")
        if not isinstance(entities, list) or not entities:
            continue

        active_entities[entity_key] = {
            "kind": payload.get("kind"),
            "title": payload.get("title"),
            "summary": payload.get("summary"),
            "total": payload.get("total"),
            "items": entities,
        }

    return active_entities


def _compact_client_context(client_context: Optional[dict]) -> Optional[dict]:
    if not isinstance(client_context, dict):
        return None

    player = client_context.get("player")
    if not isinstance(player, dict):
        player = client_context

    current_track = player.get("current_track")
    normalized_track = None
    if isinstance(current_track, dict):
        normalized_track = {
            "id": str(current_track.get("id") or "").strip(),
            "name": str(current_track.get("name") or "").strip(),
            "artist": str(current_track.get("artist") or "").strip(),
            "album": str(current_track.get("album") or "").strip(),
        }

    queue = player.get("queue")
    normalized_queue = []
    if isinstance(queue, list):
        for item in queue[:20]:
            if not isinstance(item, dict):
                continue
            normalized_queue.append(
                {
                    "id": str(item.get("id") or "").strip(),
                    "name": str(item.get("name") or "").strip(),
                    "artist": str(item.get("artist") or "").strip(),
                }
            )

    compact = {
        "player": {
            "has_active_track": bool(player.get("has_active_track")),
            "is_playing": bool(player.get("is_playing")),
            "status_text": str(player.get("status_text") or "").strip(),
            "current_time_seconds": player.get("current_time_seconds") or 0,
            "duration_seconds": player.get("duration_seconds") or 0,
            "current_track": normalized_track,
            "queue_size": player.get("queue_size") or len(normalized_queue),
            "queue": normalized_queue,
        }
    }

    capabilities = client_context.get("capabilities")
    if isinstance(capabilities, list):
        compact["capabilities"] = [str(item).strip() for item in capabilities[:20] if str(item or "").strip()]

    return compact


def _build_agent_input(
    memory_summary: str,
    history: List[dict],
    user_message: str,
    client_context: Optional[dict] = None,
) -> str:
    parts: List[str] = []
    memory = (memory_summary or "").strip()
    if memory:
        parts.extend(["【记忆摘要】", memory, ""])
    if history:
        parts.append("【对话历史】")
        for item in history[-20:]:
            role = "用户" if item["role"] == "user" else "助手"
            parts.append(f"{role}: {item['content']}")
            payload = _compact_payload_for_history(item.get("payload"))
            if payload:
                parts.append(
                    "ASSISTANT_PAYLOAD: "
                    + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                )
        parts.append("")
    active_entities = _build_active_entities(history)
    if active_entities:
        parts.append(
            "[ACTIVE_ENTITIES] "
            + json.dumps(active_entities, ensure_ascii=False, separators=(",", ":"))
        )
        parts.append("")
    compact_context = _compact_client_context(client_context)
    if compact_context:
        parts.append(
            "[PLAYER_STATE] "
            + json.dumps(compact_context, ensure_ascii=False, separators=(",", ":"))
        )
        parts.append("")
    parts.extend(["【当前用户问题】", user_message])
    return "\n".join(parts).strip()


def _update_memory_summary(prev_summary: str, last_user: str, last_assistant: str) -> str:
    from musicAgents.core.utils import get_llm

    llm = get_llm(model=None, task="polish")
    prompt = (
        "你是对话记忆整理助手。请把对话中对后续有用的长期信息整理成一段简短纯文本摘要。\n"
        "要求：\n"
        "1. 只保留用户偏好、常用对象、约束条件、已确认事实等长期有价值的信息。\n"
        "2. 不要包含任何 ID 或纯数字编号。\n"
        "3. 不要使用 Markdown，也不要使用表情符号。\n"
        "4. 控制在 150 字以内。\n\n"
        f"已有摘要：{(prev_summary or '').strip()}\n\n"
        f"最新一轮用户：{(last_user or '').strip()}\n"
        f"最新一轮助手：{(last_assistant or '').strip()}\n\n"
        "输出：更新后的摘要（纯文本）"
    )
    result = llm.invoke(prompt)
    content = result.content if hasattr(result, "content") else str(result)
    return (content or "").strip()


def _get_memory_summary_lock(conversation_id: str) -> threading.Lock:
    with _MEMORY_SUMMARY_LOCKS_GUARD:
        lock = _MEMORY_SUMMARY_LOCKS.get(conversation_id)
        if lock is None:
            lock = threading.Lock()
            _MEMORY_SUMMARY_LOCKS[conversation_id] = lock
        return lock


def _schedule_memory_summary_refresh(conversation_id: str, last_user: str, last_assistant: str) -> None:
    if not str(conversation_id or "").strip():
        return

    def worker() -> None:
        lock = _get_memory_summary_lock(conversation_id)
        with lock:
            try:
                current_conv = store.get_conversation(conversation_id)
                if not current_conv:
                    return
                new_summary = _update_memory_summary(
                    current_conv.memory_summary,
                    last_user,
                    last_assistant,
                )
                if new_summary:
                    store.update_memory_summary(conversation_id, new_summary)
            except Exception:
                pass

    threading.Thread(
        target=worker,
        name=f"memory-summary-{conversation_id[:8]}",
        daemon=True,
    ).start()


def _serialize_conversation(conv: Conversation) -> dict:
    return {
        "id": conv.id,
        "title": conv.title,
        "updated_at": conv.updated_at,
        "memory_summary": conv.memory_summary,
    }


def _join_artist_names(value: Any) -> str:
    if isinstance(value, list):
        names: List[str] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if name:
                names.append(name)
        return " / ".join(names)
    return str(value or "").strip()


def _normalize_playlist_song_item(track: Any, index: int) -> Optional[dict]:
    if not isinstance(track, dict):
        return None

    song_id = str(track.get("id") or "").strip()
    name = str(track.get("name") or "").strip()
    if not song_id or not name:
        return None

    album = track.get("al") if isinstance(track.get("al"), dict) else {}
    return {
        "id": song_id,
        "rank": index,
        "name": name,
        "artist": _join_artist_names(track.get("ar") or track.get("artists") or []),
        "album": str(album.get("name") or "").strip(),
        "cover_url": str(album.get("picUrl") or "").strip(),
        "duration_ms": track.get("dt"),
        "play_url": f"/agent/songs/{song_id}/play?level=jymaster&prefer=stream&mode=redirect",
    }


def _first_nonempty_value(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def _normalize_tool_song_item(track: Any, index: int, *, source: str = "") -> Optional[dict]:
    if not isinstance(track, dict):
        return None

    song_id = str(_first_nonempty_value(track, "id", "歌曲id", "song_id", "songId") or "").strip()
    name = str(_first_nonempty_value(track, "name", "歌曲名字", "title") or "").strip()
    if not song_id or not name:
        return None

    artist = _join_artist_names(
        _first_nonempty_value(track, "artist", "歌手", "artists", "ar", "artist_name", "artistName") or ""
    )
    album = str(_first_nonempty_value(track, "album", "专辑名字", "album_name", "albumName") or "").strip()
    cover_url = str(_first_nonempty_value(track, "cover_url", "封面url", "coverUrl", "picUrl") or "").strip()
    duration_ms = _first_nonempty_value(track, "duration_ms", "时长", "duration", "durationMs", "dt")

    try:
        normalized_duration = int(duration_ms) if duration_ms not in (None, "") else 0
    except (TypeError, ValueError):
        normalized_duration = 0

    return {
        "id": song_id,
        "rank": index,
        "name": name,
        "artist": artist,
        "album": album,
        "cover_url": cover_url,
        "duration_ms": normalized_duration,
        "play_url": f"/agent/songs/{song_id}/play?level=jymaster&prefer=stream&mode=redirect",
        "source": source,
    }


def _extract_tool_song_items(result: Any) -> list[dict[str, Any]]:
    if not isinstance(result, dict):
        return []

    for key in ("songs", "推荐新音乐", "每日推荐歌曲"):
        value = result.get(key)
        if isinstance(value, list) and value:
            return value
    return []


def _dedupe_song_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        song_id = str(item.get("id") or "").strip()
        if not song_id or song_id in seen:
            continue
        seen.add(song_id)
        deduped.append(item)
    return deduped


def _build_heart_mode_queue(
    liked_items: list[dict[str, Any]],
    personalized_items: list[dict[str, Any]],
    *,
    total_limit: int,
) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    liked_index = 0
    personalized_index = 0

    while len(queue) < total_limit and (liked_index < len(liked_items) or personalized_index < len(personalized_items)):
        for source_items, source_name in (
            (liked_items, "liked"),
            (personalized_items, "personalized"),
            (liked_items, "liked"),
        ):
            source_index = liked_index if source_name == "liked" else personalized_index
            if source_index >= len(source_items) or len(queue) >= total_limit:
                continue

            song = dict(source_items[source_index])
            song["source"] = source_name
            queue.append(song)

            if source_name == "liked":
                liked_index += 1
            else:
                personalized_index += 1

    return _dedupe_song_items(queue)


def _normalize_playlist_header(playlist_id: str, playlist: Any, songs_count: int) -> dict:
    data = playlist if isinstance(playlist, dict) else {}
    track_count = data.get("trackCount")
    try:
        total_tracks = int(track_count)
    except (TypeError, ValueError):
        total_tracks = songs_count

    return {
        "id": str(data.get("id") or playlist_id).strip(),
        "name": str(data.get("name") or "").strip(),
        "description": str(data.get("description") or "").strip(),
        "cover_url": str(data.get("coverImgUrl") or data.get("picUrl") or "").strip(),
        "track_count": total_tracks,
        "play_count": data.get("playCount"),
    }


def _serialize_message(msg: Message) -> dict:
    return {
        "id": msg.id,
        "conversation_id": msg.conversation_id,
        "role": msg.role,
        "content": msg.content,
        "created_at": msg.created_at,
        "payload": msg.payload,
    }


def _first_profile_value(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _normalize_user_profile(raw_profile: Any) -> dict:
    if not isinstance(raw_profile, dict):
        return {
            "user_id": "",
            "nickname": "",
            "avatar_url": "",
            "signature": "",
            "level": 0,
            "source": "netease",
        }

    nested_profile = raw_profile.get("profile") if isinstance(raw_profile.get("profile"), dict) else {}
    return {
        "user_id": _first_profile_value(
            raw_profile.get("user_id"),
            raw_profile.get("userId"),
            nested_profile.get("user_id"),
            nested_profile.get("userId"),
        ),
        "nickname": _first_profile_value(
            raw_profile.get("nickname"),
            nested_profile.get("nickname"),
        ),
        "avatar_url": _first_profile_value(
            raw_profile.get("avatar_url"),
            raw_profile.get("avatarUrl"),
            raw_profile.get("avatar"),
            nested_profile.get("avatar_url"),
            nested_profile.get("avatarUrl"),
            nested_profile.get("avatar"),
        ),
        "signature": _first_profile_value(
            raw_profile.get("signature"),
            nested_profile.get("signature"),
        ),
        "level": raw_profile.get("level") or nested_profile.get("level") or 0,
        "source": "netease",
    }


def _extract_song_play_url(result: Any) -> str:
    payload = result
    if isinstance(payload, dict):
        payload = payload.get("data") or payload.get("下载地址") or payload
    if isinstance(payload, list):
        payload = next((item for item in payload if isinstance(item, dict)), None)
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("url") or payload.get("播放地址") or payload.get("下载地址") or "").strip()




def _proxy_remote_audio_stream(url: str, *, range_header: Optional[str] = None) -> StreamingResponse:
    request_headers = {}
    if range_header:
        request_headers["Range"] = range_header

    try:
        upstream = requests.get(url, headers=request_headers, stream=True, timeout=(10, 300))
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail="song_play_temporarily_unavailable") from exc

    if upstream.status_code >= 400:
        upstream.close()
        raise HTTPException(status_code=502, detail="song_play_temporarily_unavailable")

    media_type = str(upstream.headers.get("Content-Type") or "audio/mpeg").strip() or "audio/mpeg"
    response_headers = {"Cache-Control": "no-cache"}
    for key in ("Content-Length", "Content-Range", "Accept-Ranges", "ETag", "Last-Modified"):
        value = str(upstream.headers.get(key) or "").strip()
        if value:
            response_headers[key] = value

    def _iter_audio():
        try:
            for chunk in upstream.iter_content(chunk_size=64 * 1024):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    return StreamingResponse(
        _iter_audio(),
        status_code=upstream.status_code,
        media_type=media_type,
        headers=response_headers,
    )
_LYRIC_TIMESTAMP_RE = re.compile(r"\[(\d{1,3}(?::\d{1,2}){1,2}(?:[.,]\d{1,3})?)\]")
_LYRIC_META_RE = re.compile(r"^\[[A-Za-z]+:.*\]$")
_LYRIC_CREDIT_RE = re.compile(
    r"^(作词|作曲|编曲|制作人|製作人|执行制作|執行製作|配唱|和声编写|和聲編寫|合声编写|合聲編寫|吉他|吉他手|贝斯|貝斯|鼓|混音|母带|母帶|录音|錄音|监制|監製|词|詞|曲)[：:\s]",
)


def _cjk_count(value: str) -> int:
    count = 0
    for ch in str(value or ""):
        if 0x4E00 <= ord(ch) <= 0x9FFF:
            count += 1
    return count


def _normalize_lyric_text(value: Optional[str]) -> str:
    text = str(value or "")
    if not text:
        return ""

    try:
        repaired = text.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text

    if _cjk_count(repaired) >= _cjk_count(text):
        return repaired
    return text


def _parse_lrc_timestamp(value: str) -> Optional[float]:
    raw = str(value or "").strip()
    if not raw:
        return None

    parts = raw.split(":")
    if len(parts) not in (2, 3):
        return None

    try:
        seconds = float(parts[-1].replace(",", "."))
        minutes = int(parts[-2])
        hours = int(parts[-3]) if len(parts) == 3 else 0
    except ValueError:
        return None

    return (hours * 3600) + (minutes * 60) + seconds


def _parse_song_lyrics(raw_lyric: Optional[str]) -> List[dict]:
    text = _normalize_lyric_text(raw_lyric).replace("\r\n", "\n")
    if not text.strip():
        return []

    timed_lines: List[dict] = []
    plain_lines: List[dict] = []

    for raw_line in text.split("\n"):
        line = raw_line.strip().lstrip("\ufeff")
        if not line:
            continue

        matches = list(_LYRIC_TIMESTAMP_RE.finditer(line))
        lyric_text = _LYRIC_TIMESTAMP_RE.sub("", line).strip()

        if _LYRIC_CREDIT_RE.match(lyric_text):
            continue

        if matches:
            if not lyric_text:
                continue
            for match in matches:
                timestamp = _parse_lrc_timestamp(match.group(1))
                if timestamp is None:
                    continue
                timed_lines.append({"time": timestamp, "text": lyric_text})
            continue

        if _LYRIC_META_RE.fullmatch(line):
            continue

        plain_lines.append({"time": None, "text": lyric_text or line})

    if timed_lines:
        timed_lines.sort(key=lambda item: item["time"])
        return timed_lines

    return plain_lines


def _make_progress_steps() -> List[dict]:
    return [
        {
            "key": item["key"],
            "label": item["label"],
            "description": item["description"],
            "status": "pending",
        }
        for item in STAGE_CATALOG
    ]


def _set_current_stage(steps: List[dict], stage_key: str) -> dict:
    current = None
    found = False
    for step in steps:
        if step["key"] == stage_key:
            step["status"] = "in_progress"
            current = step
            found = True
            continue
        if not found and step["status"] == "in_progress":
            step["status"] = "completed"
        if found and step["status"] != "completed":
            step["status"] = "pending"

    for step in steps:
        if step["key"] == stage_key:
            current = step
            break

    if current is None:
        meta = STAGE_META_BY_KEY.get(stage_key, {"label": stage_key, "description": ""})
        current = {
            "key": stage_key,
            "label": meta["label"],
            "description": meta["description"],
            "status": "in_progress",
        }
        steps.append(current)
    return current


def _finish_progress(steps: List[dict], success: bool) -> None:
    for step in steps:
        if step["status"] == "in_progress":
            step["status"] = "completed" if success else "failed"


def _iter_stream_chunks(text: str):
    value = str(text or "")
    if not value:
        return

    def _iter_plain_chunks(plain_text: str):
        if not plain_text:
            return
        # Preserve already-small model deltas to keep true token streaming responsive.
        if len(plain_text) <= 16:
            yield plain_text
            return

        soft_limit = 24
        hard_limit = 48
        split_chars = {
            "\n",
            "。",
            "，",
            "！",
            "？",
            "；",
            "：",
            ",",
            ".",
            "!",
            "?",
            ";",
            ":",
        }
        buf: list[str] = []
        for ch in plain_text:
            buf.append(ch)
            current = "".join(buf)
            if ch == "\n":
                yield current
                buf = []
                continue
            if len(current) >= hard_limit:
                yield current
                buf = []
                continue
            if len(current) >= soft_limit and ch in split_chars:
                yield current
                buf = []
        if buf:
            yield "".join(buf)

    url_re = re.compile(r"https?://[^\s<]+")
    last = 0
    for match in url_re.finditer(value):
        prefix = value[last:match.start()]
        yield from _iter_plain_chunks(prefix)
        url = match.group(0)
        if url:
            yield url
        last = match.end()

    suffix = value[last:]
    yield from _iter_plain_chunks(suffix)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


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
    "song_play_temporarily_unavailable",
    "song_lyrics_temporarily_unavailable",
)


def _looks_like_internal_failure(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    return any(marker in text for marker in _INTERNAL_ERROR_MARKERS)


def _safe_error_message(value: Any, *, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    if _looks_like_internal_failure(text):
        return fallback
    return text


def _safe_progress_description(
    value: Any,
    *,
    fallback: str = "后端服务刚刚出错了，本次处理已中断。",
) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if _looks_like_internal_failure(text):
        return fallback
    return text


@router.post("/agent/chat")
def agent_chat(request: ChatRequest):
    try:
        from musicAgents.main import run_three_layer_agent

        conv_id = request.conversation_id
        if not conv_id:
            conv_id = str(uuid4())
            store.create_conversation(conv_id, _default_title_from_message(request.message))

        conv = store.get_conversation(conv_id)
        if not conv:
            raise HTTPException(status_code=404, detail="conversation_not_found")

        if (conv.title or "").strip() == DEFAULT_CONVERSATION_TITLE:
            updated = store.update_conversation_title(conv_id, _default_title_from_message(request.message))
            if updated:
                conv = updated

        history = [
            {"role": m.role, "content": m.content, "payload": m.payload}
            for m in store.list_messages(conv_id, limit=200, offset=0)
        ]
        store.append_message(str(uuid4()), conv_id, "user", request.message)
        agent_input = _build_agent_input(conv.memory_summary, history, request.message, request.client_context)
        assistant_payload = None
        client_action = None

        def on_agent_event(payload: dict):
            nonlocal assistant_payload, client_action
            event_name = str(payload.get("event") or "").strip()
            if event_name == "rich_content":
                assistant_payload = payload.get("payload")
            if event_name == "client_action":
                client_action = payload.get("payload")

        reply_text = run_three_layer_agent(agent_input, event_cb=on_agent_event)
        reply_text = reply_text if isinstance(reply_text, str) else str(reply_text)
        store.append_message(str(uuid4()), conv_id, "assistant", reply_text, payload=assistant_payload)

        try:
            new_summary = _update_memory_summary(conv.memory_summary, request.message, reply_text)
            if new_summary:
                store.update_memory_summary(conv_id, new_summary)
        except Exception:
            pass

        return {
            "success": True,
            "reply": reply_text,
            "conversation_id": conv_id,
            "payload": assistant_payload,
            "client_action": client_action,
        }
    except HTTPException:
        raise
    except BaseException as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit, GeneratorExit)):
            raise
        import traceback

        traceback.print_exc()
        message = _safe_error_message(
            exc,
            fallback="抱歉，处理请求时出了一点问题，请稍后再试。",
        )
        return {"success": False, "reply": message}


@router.post("/agent/chat/stream")
def agent_chat_stream(request: ChatRequest):
    q: "queue.Queue[tuple[str, dict] | None]" = queue.Queue()

    def emit(event_name: str, **payload):
        q.put((event_name, payload))

    def worker():
        request_started_at = time.perf_counter()
        progress_steps = _make_progress_steps()
        tool_states: Dict[str, dict] = {}
        run_metrics: dict[str, Any] = {
            "elapsed_ms": 0,
            "stages": [],
            "reflection": None,
            "provider": None,
            "models": {},
        }

        def push_progress(stage_key: Optional[str], *, label: Optional[str] = None, description: Optional[str] = None):
            current_step = None
            if stage_key:
                current_step = _set_current_stage(progress_steps, stage_key)
            emit(
                "progress",
                current_stage=stage_key,
                current_stage_label=label or (current_step["label"] if current_step else ""),
                current_stage_description=_safe_progress_description(
                    description or (current_step["description"] if current_step else "")
                ),
                steps=progress_steps,
                tools=list(tool_states.values()),
                metrics=run_metrics,
            )

        try:
            from musicAgents.main import run_three_layer_agent

            conv_id = request.conversation_id
            if not conv_id:
                conv_id = str(uuid4())
                store.create_conversation(conv_id, _default_title_from_message(request.message))

            conv = store.get_conversation(conv_id)
            if not conv:
                emit("error", message="conversation_not_found")
                q.put(None)
                return

            if (conv.title or "").strip() == DEFAULT_CONVERSATION_TITLE:
                updated = store.update_conversation_title(conv_id, _default_title_from_message(request.message))
                if updated:
                    conv = updated

            assistant_message_id = str(uuid4())
            assistant_started = False
            streamed_any = False
            assistant_payload = None

            emit("meta", conversation_id=conv_id, conversation=_serialize_conversation(conv))
            push_progress(None, label="等待开始", description="后端已接收请求，准备进入处理流程")

            history = [
                {"role": m.role, "content": m.content, "payload": m.payload}
                for m in store.list_messages(conv_id, limit=200, offset=0)
            ]
            user_msg = store.append_message(str(uuid4()), conv_id, "user", request.message)
            emit("message", message=_serialize_message(user_msg))
            agent_input = _build_agent_input(conv.memory_summary, history, request.message, request.client_context)

            def ensure_assistant_started():
                nonlocal assistant_started
                if assistant_started:
                    return
                assistant_started = True
                emit(
                    "message_start",
                    message={
                        "id": assistant_message_id,
                        "conversation_id": conv_id,
                        "role": "assistant",
                        "content": "",
                        "created_at": None,
                    },
                )

            def on_token(tok: str):
                nonlocal streamed_any
                text = str(tok or "")
                if not text:
                    return
                ensure_assistant_started()
                for piece in _iter_stream_chunks(text):
                    if not piece:
                        continue
                    streamed_any = True
                    emit("delta", text=piece, message_id=assistant_message_id)

            def on_agent_event(payload: dict):
                nonlocal assistant_payload
                event_name = str(payload.get("event") or "").strip()
                if not event_name:
                    return
                if event_name == "stage":
                    stage_key = str(payload.get("stage") or "").strip()
                    if stage_key:
                        push_progress(stage_key)
                    return
                if event_name == "run_started":
                    run_metrics["provider"] = payload.get("provider")
                    run_metrics["models"] = {
                        "intent": payload.get("intent_model"),
                        "tool": payload.get("tool_model"),
                        "polish": payload.get("polish_model"),
                    }
                    emit("agent_run", **run_metrics)
                    return
                if event_name == "thought":
                    emit(
                        "thought",
                        kind=payload.get("kind") or "thought",
                        text=payload.get("text") or "",
                        elapsed_ms=payload.get("elapsed_ms"),
                        confidence=payload.get("confidence"),
                        need_retry=payload.get("need_retry"),
                    )
                    return
                if event_name == "stage_timing":
                    run_metrics["elapsed_ms"] = payload.get("elapsed_ms") or run_metrics.get("elapsed_ms") or 0
                    run_metrics["stages"].append(
                        {
                            "stage": payload.get("stage"),
                            "label": payload.get("label"),
                            "elapsed_ms": payload.get("elapsed_ms"),
                            "use_polish": payload.get("use_polish"),
                        }
                    )
                    emit("metrics", metrics=run_metrics)
                    return
                if event_name == "reflection":
                    run_metrics["reflection"] = {
                        "confidence": payload.get("confidence"),
                        "summary": payload.get("summary"),
                        "need_retry": bool(payload.get("need_retry")),
                        "next_action": payload.get("next_action"),
                    }
                    emit("reflection", **run_metrics["reflection"])
                    return
                if event_name == "intent":
                    emit(
                        "intent",
                        rewritten_prompt=payload.get("rewritten_prompt"),
                        suggested_tools=payload.get("suggested_tools") or [],
                    )
                    return
                if event_name == "tools_preload":
                    emit("tools_preload", suggested_tools=payload.get("suggested_tools") or [])
                    return
                if event_name in {"tool_start", "tool_end"}:
                    tool_name = str(payload.get("tool_name") or "").strip() or "unknown_tool"
                    state = tool_states.get(tool_name) or {
                        "tool_name": tool_name,
                        "status": "pending",
                        "args": None,
                    }
                    if event_name == "tool_start":
                        state["status"] = "running"
                        state["args"] = payload.get("args")
                    else:
                        state["status"] = "success" if payload.get("success") else "failed"
                    tool_states[tool_name] = state
                    push_progress("tool_execution")
                    return
                if event_name == "polish":
                    emit("polish", use_polish=bool(payload.get("use_polish")))
                    return
                if event_name == "rich_content":
                    assistant_payload = payload.get("payload")
                    ensure_assistant_started()
                    emit("rich_content", message_id=assistant_message_id, payload=assistant_payload)
                    return
                if event_name == "client_action":
                    ensure_assistant_started()
                    emit("client_action", message_id=assistant_message_id, payload=payload.get("payload") or {})
                    return
                if event_name == "done":
                    success = bool(payload.get("success"))
                    run_metrics["elapsed_ms"] = payload.get("elapsed_ms") or int(
                        (time.perf_counter() - request_started_at) * 1000
                    )
                    _finish_progress(progress_steps, success)
                    emit(
                        "progress",
                        current_stage="done" if success else "failed",
                        current_stage_label="已完成" if success else "执行失败",
                        current_stage_description="后端处理结束",
                        steps=progress_steps,
                        tools=list(tool_states.values()),
                    )

            reply_text = run_three_layer_agent(
                agent_input,
                event_cb=on_agent_event,
                token_cb=on_token,
            )
            reply_text = reply_text if isinstance(reply_text, str) else str(reply_text)
            ensure_assistant_started()
            if not streamed_any and reply_text:
                for piece in _iter_stream_chunks(reply_text):
                    if not piece:
                        continue
                    emit("delta", text=piece, message_id=assistant_message_id)
            emit("final", text=reply_text, message_id=assistant_message_id)

            assistant_msg = store.append_message(assistant_message_id, conv_id, "assistant", reply_text, payload=assistant_payload)
            emit("message_commit", message=_serialize_message(assistant_msg))
            emit("done", success=True, metrics=run_metrics)
            _schedule_memory_summary_refresh(conv_id, request.message, reply_text)
        except Exception as exc:
            safe_error_message = _safe_error_message(
                exc,
                fallback="后端服务刚刚出错了，请稍后再试。",
            )
            _finish_progress(progress_steps, False)
            emit(
                "progress",
                current_stage="failed",
                current_stage_label="执行失败",
                current_stage_description=_safe_progress_description(exc),
                steps=progress_steps,
                tools=list(tool_states.values()),
            )
            emit("error", message=safe_error_message)
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def gen():
        while True:
            try:
                item = q.get(timeout=5)
            except Empty:
                yield ": ping\n\n"
                continue
            if item is None:
                break
            event_name, payload = item
            yield _sse(event_name, payload)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/agent/conversations")
def create_conversation(request: CreateConversationRequest):
    conv_id = str(uuid4())
    title = (request.title or "").strip() or DEFAULT_CONVERSATION_TITLE
    conv = store.create_conversation(conv_id, title)
    return {"success": True, "conversation": _serialize_conversation(conv)}


@router.get("/agent/conversations")
def list_conversations(limit: int = 50, offset: int = 0):
    conversations = store.list_conversations(limit=limit, offset=offset)
    return {"success": True, "conversations": [_serialize_conversation(item) for item in conversations]}


@router.patch("/agent/conversations/{conversation_id}")
def update_conversation(conversation_id: str, request: UpdateConversationRequest):
    conv = store.update_conversation_title(conversation_id, request.title)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    return {"success": True, "conversation": _serialize_conversation(conv)}


@router.delete("/agent/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    ok = store.delete_conversation(conversation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    return {"success": True}


@router.get("/agent/conversations/{conversation_id}/messages")
def get_conversation_messages(conversation_id: str, limit: int = 200, offset: int = 0):
    conv = store.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation_not_found")
    messages = store.list_messages(conversation_id, limit=limit, offset=offset)
    return {
        "success": True,
        "conversation": _serialize_conversation(conv),
        "messages": [_serialize_message(item) for item in messages],
        "memory_summary": conv.memory_summary,
    }


@router.get("/agent/user/profile")
def get_user_profile():
    try:
        with _SONG_ENDPOINT_LOCK:
            from tools.MusicTools.musicTools import user_detail

            raw_profile = user_detail.invoke({}) if hasattr(user_detail, "invoke") else user_detail()

        if isinstance(raw_profile, str):
            return {
                "success": False,
                "profile": _normalize_user_profile({}),
                "message": raw_profile,
            }

        return {
            "success": True,
            "profile": _normalize_user_profile(raw_profile),
        }
    except HTTPException:
        raise
    except Exception as exc:
        return {
            "success": False,
            "profile": _normalize_user_profile({}),
            "message": "user_profile_temporarily_unavailable",
        }


@router.get("/agent/songs/{song_id}/play")
def get_song_play_redirect(
    request: Request,
    song_id: str,
    level: str = "jymaster",
    prefer: str = "stream",
    mode: str = "redirect",
):
    try:
        with _SONG_ENDPOINT_LOCK:
            from tools.MusicTools.musicTools import song_download_url_v1, song_url_v1

            print("song play redirect =========================")
            print(song_id)
            # The NCM `/song/url/v1` path is intermittently crashing the whole
            # backend process with "Maximum call stack size exceeded" for some
            # real user requests. Use the download-url endpoint first because it
            # has been the most stable source for browser playback.
            resolver_order = (song_download_url_v1, song_url_v1)

            song_url = ""
            for resolver in resolver_order:
                result = resolver.invoke({"id": song_id, "level": level})
                song_url = _extract_song_play_url(result)
                if song_url:
                    break

        if not song_url:
            raise HTTPException(status_code=502, detail="song_play_temporarily_unavailable")

        # Long-lived audio proxy streaming is unstable in the current runtime
        # and can crash the backend process after playback has already started.
        # Always redirect the browser directly to the signed upstream media URL
        # so the backend is no longer part of the hot audio path.
        return RedirectResponse(url=song_url, status_code=307)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="song_play_temporarily_unavailable") from exc

@router.get("/agent/songs/{song_id}/lyrics")
def get_song_lyrics(song_id: str):
    try:
        with _SONG_ENDPOINT_LOCK:
            from tools.MusicTools.musicTools import song_lyrics

            raw_lyric = song_lyrics.invoke({"song_id": song_id})
            if raw_lyric is None:
                raw_lyric = ""
            if not isinstance(raw_lyric, str):
                raw_lyric = str(raw_lyric)
            raw_lyric = _normalize_lyric_text(raw_lyric)
            if (
                _looks_like_internal_failure(raw_lyric)
                or raw_lyric.strip().startswith("??????????????????")
                or "?????????" in raw_lyric
            ):
                raise HTTPException(
                    status_code=502,
                    detail="暂时获取不到这首歌的歌词，请稍后再试。",
                )

            lines = _parse_song_lyrics(raw_lyric)
            return {
                "success": True,
                "song_id": song_id,
                "raw_lyric": raw_lyric,
                "lines": lines,
                "timed": any(item.get("time") is not None for item in lines),
            }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="暂时获取不到这首歌的歌词，请稍后再试。",
        ) from exc


@router.get("/agent/player/heart-mode")
def get_heart_mode_queue(liked_limit: int = 24, personalized_limit: int = 12, total_limit: int = 36):
    safe_liked_limit = max(1, min(int(24 if liked_limit is None else liked_limit), 80))
    safe_personalized_limit = max(0, min(int(12 if personalized_limit is None else personalized_limit), 40))
    safe_total_limit = max(1, min(int(36 if total_limit is None else total_limit), 120))

    liked_items: list[dict[str, Any]] = []
    personalized_items: list[dict[str, Any]] = []

    try:
        with _SONG_ENDPOINT_LOCK:
            from tools.MusicTools.musicTools import _load_cached_liked_songs, liked_songs, personalized_newsong

            cached_liked_items = _load_cached_liked_songs()
            liked_items = [
                normalized
                for index, item in enumerate(cached_liked_items[:safe_liked_limit], start=1)
                if (normalized := _normalize_tool_song_item(item, index, source="liked"))
            ]

            if len(liked_items) < safe_liked_limit:
                liked_result = liked_songs.invoke({})
                liked_source_items = _extract_tool_song_items(liked_result)
                liked_items = [
                    normalized
                    for index, item in enumerate(liked_source_items[:safe_liked_limit], start=1)
                    if (normalized := _normalize_tool_song_item(item, index, source="liked"))
                ]

            if safe_personalized_limit > 0:
                personalized_result = personalized_newsong.invoke({"limit": safe_personalized_limit})
                personalized_source_items = _extract_tool_song_items(personalized_result)
                personalized_items = [
                    normalized
                    for index, item in enumerate(personalized_source_items[:safe_personalized_limit], start=1)
                    if (normalized := _normalize_tool_song_item(item, index, source="personalized"))
                ]
    except Exception as exc:
        raise HTTPException(status_code=424, detail="暂时无法生成心动模式歌曲，请稍后再试。") from exc

    liked_items = _dedupe_song_items(liked_items)
    liked_item_ids = {str(song.get("id") or "").strip() for song in liked_items}
    personalized_items = [
        item for item in _dedupe_song_items(personalized_items)
        if str(item.get("id") or "").strip() not in liked_item_ids
    ]
    queue = _build_heart_mode_queue(liked_items, personalized_items, total_limit=safe_total_limit)

    if not queue:
        raise HTTPException(status_code=404, detail="当前还拿不到可播放的心动模式歌曲。")

    return {
        "success": True,
        "mode": "heart",
        "title": "心动模式",
        "summary": f"已为你准备 {len(queue)} 首心动模式歌曲",
        "songs": queue,
        "source_breakdown": {
            "liked": len(liked_items),
            "personalized": len(personalized_items),
        },
    }


@router.get("/agent/playlists/{playlist_id}/tracks")
def get_playlist_tracks(playlist_id: str, limit: int = 100, offset: int = 0):
    try:
        safe_limit = max(1, min(int(limit), 300))
    except (TypeError, ValueError):
        safe_limit = 100
    try:
        safe_offset = max(0, int(offset))
    except (TypeError, ValueError):
        safe_offset = 0

    try:
        with _SONG_ENDPOINT_LOCK:
            from tools.MusicTools.musicTools import api, cookie

            playlist_detail_response = api.playlist_detail(id=playlist_id, cookie=cookie)
            playlist_tracks_response = api.playlist_track_all(id=playlist_id, limit=safe_limit, offset=safe_offset)

        if not playlist_detail_response or playlist_detail_response.status != 200:
            raise HTTPException(status_code=502, detail="playlist_detail_temporarily_unavailable")
        if not playlist_tracks_response or playlist_tracks_response.status != 200:
            raise HTTPException(status_code=502, detail="playlist_tracks_temporarily_unavailable")

        playlist_body = playlist_detail_response.body or {}
        tracks_body = playlist_tracks_response.body or {}
        playlist = playlist_body.get("playlist") or {}
        raw_songs = tracks_body.get("songs") or []

        songs: List[dict] = []
        for index, raw_track in enumerate(raw_songs, start=1):
            normalized = _normalize_playlist_song_item(raw_track, index)
            if normalized:
                songs.append(normalized)

        return {
            "success": True,
            "playlist": _normalize_playlist_header(playlist_id, playlist, len(songs)),
            "songs": songs,
            "total": len(songs),
            "offset": safe_offset,
            "limit": safe_limit,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="playlist_tracks_temporarily_unavailable") from exc
