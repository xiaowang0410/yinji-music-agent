# -*- coding: utf-8 -*-

import json
import logging
import re
from datetime import datetime
from functools import lru_cache
from typing import Any

from musicAgents.core.utils import get_llm

logger = logging.getLogger("musicAgents.output_check")

system_prompt = (
    "你是音迹中的智能音乐助手小听的输出整理助手。"
    "小听由小汪开发。请根据工具执行结果生成自然、准确、友好的中文回复。"
    "不要编造事实，不要暴露内部字段、工具名或 JSON 结构。"
    "不要暴漏歌曲id、歌曲ID、音乐id、音乐ID、排行榜id、排行榜ID。"
    "如果结果里有明确失败原因，保留失败原因"
)

_DIRECT_LINK_TOOLS = {"song_url_v1", "song_download_url_v1"}
_SILENT_PLAYER_ACTIONS = {
    "player_pause",
    "player_resume",
    "player_next_track",
    "player_previous_track",
}

_SONG_ID_KEYS = (
    "id",
    "song_id",
    "songId",
    "歌曲id",
    "歌曲ID",
    "音乐id",
    "音乐ID",
    "歌曲编号",
)
_SONG_NAME_KEYS = (
    "name",
    "歌曲名字",
    "歌曲名称",
    "歌名",
    "标题",
)
_SONG_ARTIST_KEYS = (
    "artist",
    "artists",
    "歌手",
    "artist_name",
    "artistName",
)
_SONG_ALBUM_KEYS = (
    "album",
    "专辑",
    "专辑名字",
    "专辑名称",
)
_SONG_COVER_KEYS = (
    "cover_url",
    "coverUrl",
    "picUrl",
    "image",
    "cover",
    "封面",
    "封面url",
    "封面URL",
    "图片url",
    "图片URL",
    "歌曲封面",
    "专辑封面",
)
_SONG_DURATION_KEYS = (
    "duration_ms",
    "durationMs",
    "duration",
    "时长",
)
_LIKED_SONGS_LIST_KEYS = (
    "songs",
    "歌曲列表",
    "歌曲",
    "点赞歌曲",
    "我喜欢的音乐",
    "每日推荐歌曲",
    "私人FM歌曲",
)

_PLAYLIST_ID_KEYS = (
    "id",
    "playlist_id",
    "playlistId",
    "歌单id",
    "歌单ID",
    "排行榜id",
    "排行榜ID",
)
_PLAYLIST_NAME_KEYS = (
    "name",
    "歌单名字",
    "歌单名称",
    "标题",
)
_PLAYLIST_COVER_KEYS = (
    "cover_url",
    "coverUrl",
    "picUrl",
    "coverImgUrl",
    "coverImageUrl",
    "image",
    "封面url",
    "封面URL",
    "歌单封面",
)
_PLAYLIST_DESCRIPTION_KEYS = (
    "description",
    "描述",
    "简介",
    "copywriter",
)
_PLAYLIST_TRACK_COUNT_KEYS = (
    "trackCount",
    "track_count",
    "songCount",
    "歌曲数量",
    "歌曲数",
)
_PLAYLIST_PLAY_COUNT_KEYS = (
    "playCount",
    "playcount",
    "play_count",
    "播放量",
)
_PLAYLIST_LIST_KEYS = (
    "playlists",
    "每日推荐歌单",
    "歌单列表",
    "歌单",
    "推荐歌单",
    "排行榜",
)

_ALBUM_ID_KEYS = (
    "id",
    "album_id",
    "albumId",
    "专辑id",
    "专辑ID",
)
_ALBUM_NAME_KEYS = (
    "name",
    "title",
    "专辑名字",
    "专辑名称",
)
_ALBUM_ARTIST_KEYS = (
    "artist",
    "artists",
    "歌手",
    "artist_name",
    "artistName",
)
_ALBUM_COVER_KEYS = (
    "cover_url",
    "coverUrl",
    "picUrl",
    "blurPicUrl",
    "cover",
    "image",
    "专辑封面",
)
_ALBUM_SIZE_KEYS = (
    "size",
    "songCount",
    "trackCount",
    "track_count",
    "歌曲数量",
    "歌曲数",
)
_ALBUM_PUBLISH_KEYS = (
    "publish_time",
    "publishTime",
    "publish_date",
    "publishDate",
    "发布时间",
)
_ALBUM_LIST_KEYS = (
    "albums",
    "专辑列表",
    "专辑",
)

_SONG_CARD_CONFIG = {
    "recommend_songs": {
        "title": "今日推荐歌曲",
        "keys": ("每日推荐歌曲", "songs", "歌曲列表", "歌曲"),
        "unit": "首歌",
    },
    "personal_fm": {
        "title": "私人 FM",
        "keys": ("私人FM歌曲", "songs", "歌曲列表", "歌曲"),
        "unit": "首歌",
    },
    "top_song": {
        "title": "新歌速递",
        "keys": ("songs", "歌曲列表", "歌曲"),
        "unit": "首歌",
    },
    "personalized_newsong": {
        "title": "个性化推荐新歌",
        "keys": ("个性化推荐新歌", "推荐新音乐", "songs", "歌曲列表", "歌曲"),
        "unit": "首歌",
    },
    "search_song_candidates": {
        "title": "歌曲搜索结果",
        "keys": ("songs", "歌曲列表", "歌曲"),
        "unit": "首歌",
    },
    "search_scene_songs": {
        "title": "场景歌曲推荐",
        "keys": ("songs", "歌曲列表", "歌曲"),
        "unit": "首歌",
    },
}

_PLAYLIST_CARD_CONFIG = {
    "recommend_resource": {
        "title": "每日推荐歌单",
        "keys": ("每日推荐歌单", "recommend", "playlists", "歌单列表", "歌单"),
        "unit": "个歌单",
    },
    "personalized": {
        "title": "个性化推荐歌单",
        "keys": ("个性化推荐歌单", "推荐歌单", "playlists", "歌单列表", "歌单"),
        "unit": "个歌单",
    },
    "top_playlist": {
        "title": "热门歌单",
        "keys": _PLAYLIST_LIST_KEYS,
        "unit": "个歌单",
    },
    "top_playlist_highquality": {
        "title": "精品歌单",
        "keys": _PLAYLIST_LIST_KEYS,
        "unit": "个歌单",
    },
    "toplist": {
        "title": "热门榜单",
        "keys": ("排行榜", "playlists", "歌单列表", "歌单"),
        "unit": "个榜单",
    },
}


def _safe_dumps(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return str(obj)


def _extract_final(tool_result: Any) -> dict[str, Any] | None:
    if not isinstance(tool_result, dict):
        return None
    final = tool_result.get("final")
    return final if isinstance(final, dict) else None


def _extract_final_tool_name(tool_result: Any) -> str:
    final = _extract_final(tool_result)
    if not final:
        return ""
    return str(final.get("tool_name", "")).strip()


def _extract_final_result(tool_result: Any) -> Any:
    final = _extract_final(tool_result)
    if not final:
        return None
    return final.get("result")


def _first_value(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def _pick_first_list(result: Any, keys: tuple[str, ...]) -> list[Any]:
    if not isinstance(result, dict):
        return []
    for key in keys:
        value = result.get(key)
        if isinstance(value, list) and value:
            return value
    return []


def _extract_total_hint(result: Any) -> Any:
    if not isinstance(result, dict):
        return None
    return _first_value(result, "total", "count", "size")


def _normalize_artist_text(value: Any) -> str:
    if isinstance(value, list):
        names: list[str] = []
        for item in value:
            if isinstance(item, dict):
                name = str(_first_value(item, "name", "歌手") or "").strip()
            else:
                name = str(item or "").strip()
            if name:
                names.append(name)
        return ", ".join(names)
    if isinstance(value, dict):
        return str(_first_value(value, "name", "歌手") or "").strip()
    return str(value or "").strip()


def _normalize_album_text(value: Any) -> str:
    if isinstance(value, dict):
        return str(_first_value(value, "name", "title", "专辑名字", "专辑名称") or "").strip()
    return str(value or "").strip()


def _normalize_cover_text(value: Any) -> str:
    if isinstance(value, dict):
        return str(_first_value(value, "picUrl", "coverUrl", "cover_url", "url") or "").strip()
    return str(value or "").strip()


def _normalize_duration_ms(value: Any) -> Any:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        text = str(value or "").strip()
        return text or None
    return numeric if numeric > 0 else None


def _format_publish_time_text(value: Any) -> str:
    if value in (None, ""):
        return ""

    text = str(value).strip()
    if not text:
        return ""

    try:
        numeric = int(text)
    except (TypeError, ValueError):
        return text

    if numeric <= 0:
        return ""

    timestamp_seconds = numeric / 1000 if numeric > 10**11 else numeric
    try:
        return datetime.fromtimestamp(timestamp_seconds).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return text


def _normalize_song_card_item(item: Any, index: int) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    song_id = str(_first_value(item, *_SONG_ID_KEYS) or "").strip()
    name = str(_first_value(item, *_SONG_NAME_KEYS) or "").strip()
    if not song_id or not name:
        return None

    artist = _normalize_artist_text(_first_value(item, *_SONG_ARTIST_KEYS))
    album = _normalize_album_text(_first_value(item, *_SONG_ALBUM_KEYS))
    cover_url = _normalize_cover_text(_first_value(item, *_SONG_COVER_KEYS))
    if not cover_url:
        cover_url = _normalize_cover_text(_first_value(item, *_SONG_ALBUM_KEYS))

    return {
        "id": song_id,
        "rank": index,
        "name": name,
        "artist": artist,
        "album": album,
        "cover_url": cover_url,
        "duration_ms": _normalize_duration_ms(_first_value(item, *_SONG_DURATION_KEYS)),
        "play_url": f"/agent/songs/{song_id}/play?level=jymaster&prefer=stream&mode=redirect",
    }


def _normalize_playlist_card_item(item: Any, index: int) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    playlist_id = str(_first_value(item, *_PLAYLIST_ID_KEYS) or "").strip()
    name = str(_first_value(item, *_PLAYLIST_NAME_KEYS) or "").strip()
    if not playlist_id or not name:
        return None

    return {
        "id": playlist_id,
        "rank": index,
        "name": name,
        "cover_url": str(_first_value(item, *_PLAYLIST_COVER_KEYS) or "").strip(),
        "description": str(_first_value(item, *_PLAYLIST_DESCRIPTION_KEYS) or "").strip(),
        "track_count": _first_value(item, *_PLAYLIST_TRACK_COUNT_KEYS),
        "play_count": _first_value(item, *_PLAYLIST_PLAY_COUNT_KEYS),
    }


def _normalize_album_card_item(item: Any, index: int) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    album_id = str(_first_value(item, *_ALBUM_ID_KEYS) or "").strip()
    name = str(_first_value(item, *_ALBUM_NAME_KEYS) or "").strip()
    if not album_id or not name:
        return None

    artist = _normalize_artist_text(_first_value(item, *_ALBUM_ARTIST_KEYS))
    publish_time = _format_publish_time_text(_first_value(item, *_ALBUM_PUBLISH_KEYS))
    description = " · ".join(part for part in (artist, publish_time) if part)

    return {
        "id": album_id,
        "rank": index,
        "name": name,
        "artist": artist,
        "cover_url": _normalize_cover_text(_first_value(item, *_ALBUM_COVER_KEYS)),
        "publish_time": publish_time,
        "size": _first_value(item, *_ALBUM_SIZE_KEYS),
        "description": description,
    }


def _build_song_list_rich_content(
    result: Any,
    *,
    title: str,
    keys: tuple[str, ...] = _LIKED_SONGS_LIST_KEYS,
    total_hint: Any = None,
    summary: str | None = None,
    unit: str = "首歌",
) -> dict[str, Any] | None:
    raw_songs = _pick_first_list(result, keys)
    if not raw_songs:
        return None

    items: list[dict[str, Any]] = []
    for index, item in enumerate(raw_songs, start=1):
        normalized_item = _normalize_song_card_item(item, index)
        if normalized_item:
            items.append(normalized_item)

    if not items:
        return None

    try:
        total = int(total_hint)
    except (TypeError, ValueError):
        total = len(items)

    return {
        "kind": "song_list",
        "title": str(title or "").strip(),
        "summary": str(summary or "").strip() or f"共 {total} {unit}",
        "total": total,
        "items": items,
    }


def _build_playlist_list_rich_content(
    result: Any,
    *,
    title: str,
    keys: tuple[str, ...] = _PLAYLIST_LIST_KEYS,
    total_hint: Any = None,
    summary: str | None = None,
    unit: str = "个歌单",
) -> dict[str, Any] | None:
    raw_items = _pick_first_list(result, keys)
    if not raw_items:
        return None

    items: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items, start=1):
        normalized_item = _normalize_playlist_card_item(item, index)
        if normalized_item:
            items.append(normalized_item)

    if not items:
        return None

    try:
        total = int(total_hint)
    except (TypeError, ValueError):
        total = len(items)

    return {
        "kind": "playlist_list",
        "title": str(title or "").strip(),
        "summary": str(summary or "").strip() or f"共 {total} {unit}",
        "total": total,
        "items": items,
    }


def _build_album_list_rich_content(
    result: Any,
    *,
    title: str,
    keys: tuple[str, ...] = _ALBUM_LIST_KEYS,
    total_hint: Any = None,
    summary: str | None = None,
    unit: str = "张专辑",
) -> dict[str, Any] | None:
    raw_items = _pick_first_list(result, keys)
    if not raw_items:
        return None

    items: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items, start=1):
        normalized_item = _normalize_album_card_item(item, index)
        if normalized_item:
            items.append(normalized_item)

    if not items:
        return None

    try:
        total = int(total_hint)
    except (TypeError, ValueError):
        total = len(items)

    return {
        "kind": "album_list",
        "title": str(title or "").strip(),
        "summary": str(summary or "").strip() or f"共 {total} {unit}",
        "total": total,
        "items": items,
    }


def _build_contact_list_rich_content(
    result: Any,
    *,
    title: str,
    summary: str | None = None,
    list_key: str = "mutual_follows",
    unit: str = "位好友",
) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None

    raw_items = result.get(list_key) or []
    if not isinstance(raw_items, list) or not raw_items:
        return None

    items: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            continue
        contact_id = str(_first_value(item, "id", "userId", "user_id") or "").strip()
        name = str(_first_value(item, "name", "nickname", "follow_name") or "").strip()
        if not contact_id or not name:
            continue
        items.append(
            {
                "id": contact_id,
                "rank": index,
                "name": name,
                "remarkName": str(_first_value(item, "remarkName", "remark_name") or "").strip(),
                "avatarUrl": str(_first_value(item, "avatarUrl", "avatar_url") or "").strip(),
                "signature": str(_first_value(item, "signature") or "").strip(),
            }
        )

    if not items:
        return None

    try:
        total = int(_extract_total_hint(result))
    except (TypeError, ValueError):
        total = len(items)

    return {
        "kind": "contact_list",
        "title": str(title or "").strip(),
        "summary": str(summary or "").strip() or f"共 {total} {unit}",
        "total": total,
        "items": items,
    }


def _build_liked_songs_rich_content(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None

    total_raw = _first_value(result, "total", "count")
    try:
        total = int(total_raw)
    except (TypeError, ValueError):
        total = None

    raw_count = len(_pick_first_list(result, _LIKED_SONGS_LIST_KEYS))
    resolved_total = total if isinstance(total, int) and total > 0 else raw_count
    return _build_song_list_rich_content(
        result,
        title=str(result.get("title") or "我喜欢的歌曲").strip() or "我喜欢的歌曲",
        summary=str(result.get("summary") or f"共 {resolved_total} 首喜欢的歌曲").strip(),
        total_hint=total,
        keys=_LIKED_SONGS_LIST_KEYS,
        unit="首歌",
    )


def _build_search_rich_content(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None

    if isinstance(result.get("songs"), list) and result.get("songs"):
        return _build_song_list_rich_content(
            result,
            title="搜索结果",
            total_hint=_extract_total_hint(result),
            keys=("songs",),
            unit="首歌",
        )

    if isinstance(result.get("albums"), list) and result.get("albums"):
        return _build_album_list_rich_content(
            result,
            title="搜索结果",
            total_hint=_extract_total_hint(result),
            keys=("albums",),
            unit="张专辑",
        )

    if isinstance(result.get("playlists"), list) and result.get("playlists"):
        return _build_playlist_list_rich_content(
            result,
            title="搜索结果",
            total_hint=_extract_total_hint(result),
            keys=("playlists",),
            unit="个歌单",
        )

    return None


def _normalize_url_payload(result: Any) -> dict[str, Any] | None:
    payload = result
    if isinstance(payload, dict):
        payload = payload.get("下载地址") or payload.get("播放地址") or payload.get("data") or payload

    if isinstance(payload, list):
        payload = next((item for item in payload if isinstance(item, dict)), None)

    if not isinstance(payload, dict):
        return None

    url = _first_value(payload, "下载地址", "播放地址", "url")
    if not url:
        return None

    return {
        "url": str(url).strip(),
        "level": _first_value(payload, "音质等级", "level"),
        "type": _first_value(payload, "扩展名", "type"),
        "bitrate": _first_value(payload, "比特率", "br"),
        "size": _first_value(payload, "文件大小", "size"),
        "sample_rate": _first_value(payload, "采样率", "sr"),
        "duration": _first_value(payload, "时长", "time"),
    }


def _format_bitrate(value: Any) -> str | None:
    try:
        bitrate = int(value)
    except (TypeError, ValueError):
        text = str(value or "").strip()
        return text or None

    if bitrate <= 0:
        return None
    if bitrate >= 1000:
        return f"{bitrate // 1000} kbps"
    return f"{bitrate} bps"


def _format_size(value: Any) -> str | None:
    try:
        size = float(value)
    except (TypeError, ValueError):
        text = str(value or "").strip()
        return text or None

    if size <= 0:
        return None

    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    if index == 0:
        return f"{int(size)} {units[index]}"
    return f"{size:.2f} {units[index]}"


def _format_sample_rate(value: Any) -> str | None:
    try:
        sample_rate = int(value)
    except (TypeError, ValueError):
        text = str(value or "").strip()
        return text or None

    if sample_rate <= 0:
        return None
    if sample_rate >= 1000:
        return f"{sample_rate / 1000:.1f} kHz"
    return f"{sample_rate} Hz"


def _format_duration(value: Any) -> str | None:
    try:
        milliseconds = int(value)
    except (TypeError, ValueError):
        text = str(value or "").strip()
        return text or None

    if milliseconds <= 0:
        return None

    total_seconds = milliseconds // 1000
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}小时{minutes}分{seconds}秒"
    if minutes > 0:
        return f"{minutes}分{seconds}秒"
    return f"{seconds}秒"


def _format_song_link(tool_name: str, result: Any) -> str | None:
    payload = _normalize_url_payload(result)
    if not payload:
        return None

    lines = [
        "已获取到下载链接：" if tool_name == "song_download_url_v1" else "已获取到播放链接：",
        payload["url"],
    ]

    details = []
    level = str(payload.get("level") or "").strip()
    file_type = str(payload.get("type") or "").strip()
    bitrate = _format_bitrate(payload.get("bitrate"))
    size = _format_size(payload.get("size"))
    sample_rate = _format_sample_rate(payload.get("sample_rate"))
    duration = _format_duration(payload.get("duration"))

    if level:
        details.append(f"音质：{level}")
    if file_type:
        details.append(f"格式：{file_type}")
    if bitrate:
        details.append(f"比特率：{bitrate}")
    if size:
        details.append(f"文件大小：{size}")
    if sample_rate:
        details.append(f"采样率：{sample_rate}")
    if duration:
        details.append(f"时长：{duration}")

    if details:
        lines.append("")
        lines.extend(details)

    return "\n".join(lines)


def format_structured_output(tool_result) -> str | None:
    tool_name = _extract_final_tool_name(tool_result)
    result = _extract_final_result(tool_result)

    if tool_name in _SILENT_PLAYER_ACTIONS:
        return ""

    if isinstance(result, dict) and result.get("kind") in {"client_action", "player_tool_result"}:
        message = str(result.get("message") or "").strip()
        return message or None

    if tool_name in _DIRECT_LINK_TOOLS:
        return _format_song_link(tool_name, result)

    if isinstance(result, str):
        text = result.strip()
        return text or None

    return None


def _extract_direct_final_text(tool_result: Any) -> str:
    if not isinstance(tool_result, dict):
        return ""
    final = tool_result.get("final")
    if isinstance(final, str):
        return final.strip()
    return ""


def extract_rich_content(tool_result) -> dict[str, Any] | None:
    tool_name = _extract_final_tool_name(tool_result)
    result = _extract_final_result(tool_result)

    if isinstance(result, dict) and result.get("kind") == "player_tool_result":
        source = str(result.get("rich_content_source") or "").strip()
        content = result.get("content")
        if source == "liked_songs":
            return _build_liked_songs_rich_content(content)
        song_config = _SONG_CARD_CONFIG.get(source)
        if song_config:
            return _build_song_list_rich_content(
                content,
                title=song_config["title"],
                total_hint=_extract_total_hint(content),
                keys=song_config["keys"],
                unit=song_config["unit"],
            )
        if source == "search":
            return _build_search_rich_content(content)

    if tool_name == "liked_songs":
        return _build_liked_songs_rich_content(result)

    song_config = _SONG_CARD_CONFIG.get(tool_name)
    if song_config:
        return _build_song_list_rich_content(
            result,
            title=song_config["title"],
            total_hint=_extract_total_hint(result),
            keys=song_config["keys"],
            unit=song_config["unit"],
        )

    playlist_config = _PLAYLIST_CARD_CONFIG.get(tool_name)
    if playlist_config:
        return _build_playlist_list_rich_content(
            result,
            title=playlist_config["title"],
            total_hint=_extract_total_hint(result),
            keys=playlist_config["keys"],
            unit=playlist_config["unit"],
        )

    if tool_name == "search":
        return _build_search_rich_content(result)

    if tool_name == "get_mutual_follow_list":
        return _build_contact_list_rich_content(
            result,
            title="互相关注好友",
            list_key="mutual_follows",
            unit="位好友",
        )

    return None


def extract_client_action(tool_result) -> dict[str, Any] | None:
    result = _extract_final_result(tool_result)
    if not isinstance(result, dict):
        return None

    candidate = result.get("client_action") if isinstance(result.get("client_action"), dict) else result
    if (
        isinstance(candidate, dict)
        and candidate.get("kind") == "client_action"
        and (candidate.get("type") or candidate.get("action"))
    ):
        legacy_action = candidate.get("action") if isinstance(candidate.get("action"), dict) else {}
        action_name = str(legacy_action.get("action") or "").strip()
        payload = candidate.get("payload")
        if not isinstance(payload, dict):
            payload = legacy_action.get("payload") if isinstance(legacy_action.get("payload"), dict) else {}
        return {
            "kind": "client_action",
            "version": str(candidate.get("version") or "1.0"),
            "id": str(candidate.get("id") or "").strip(),
            "type": str(candidate.get("type") or "").strip(),
            "status": str(candidate.get("status") or "ready").strip(),
            "action": action_name,
            "payload": payload,
            "message": str(candidate.get("message") or result.get("message") or "").strip(),
            "requires_confirmation": bool(candidate.get("requires_confirmation")),
            "error": candidate.get("error"),
            "success": bool(candidate.get("success", True)),
        }

    action = result.get("action")
    if not isinstance(action, dict):
        return None

    action_name = str(action.get("action") or "").strip()
    if not action_name:
        return None

    payload = action.get("payload")
    return {
        "action": action_name,
        "payload": payload if isinstance(payload, dict) else {},
        "message": str(result.get("message") or "").strip(),
    }


def _looks_like_failure_text(text: str | None) -> bool:
    txt = str(text or "").strip().lower()
    if not txt:
        return False

    markers = (
        "[失败]",
        "失败",
        "错误",
        "异常",
        "出错",
        "未找到",
        "timeout",
        "timed out",
        "connection reset",
        "connection aborted",
        "request failed",
        "proxyerror",
        "maximum call stack size exceeded",
        "failed to register environment variables",
    )
    return any(marker in txt for marker in markers)


def _looks_like_structured_text(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    return value.startswith("{") or value.startswith("[") or "tool_name" in value or "'result':" in value


def _brief_from_rich_content(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None

    kind = str(payload.get("kind") or "").strip()
    title = str(payload.get("title") or "").strip("：:。 \n")
    total = payload.get("total")

    if title:
        return f"已为你整理出{title}。"

    if kind == "song_list":
        return f"已为你整理出歌曲列表，共 {total or 0} 首。"
    if kind == "playlist_list":
        return f"已为你整理出歌单列表，共 {total or 0} 个。"
    if kind == "album_list":
        return f"已为你整理出专辑列表，共 {total or 0} 张。"
    if kind == "contact_list":
        return f"已为你整理出联系人列表，共 {total or 0} 位。"
    return None


def _fallback_output(tool_result) -> str:
    direct_output = format_structured_output(tool_result)
    if direct_output:
        return direct_output

    raw_text = _extract_raw_result(tool_result).strip()
    if raw_text:
        return raw_text

    result = _extract_final_result(tool_result)

    rich_content = extract_rich_content(tool_result)
    brief = _brief_from_rich_content(rich_content)
    if brief:
        return brief

    return _safe_dumps(result if result is not None else tool_result)


@lru_cache(maxsize=4)
def _polisher_llm(model: str):
    return get_llm(model=model or None, timeout=40, task="polish")


def should_polish_response(raw_text: str | None, tool_result) -> bool:
    tool_name = _extract_final_tool_name(tool_result)
    result = _extract_final_result(tool_result)
    direct_final_text = _extract_direct_final_text(tool_result)
    text = str(raw_text or "").strip()

    if tool_name in _DIRECT_LINK_TOOLS and format_structured_output(tool_result):
        return False

    if tool_name in _SILENT_PLAYER_ACTIONS:
        return False

    if isinstance(result, dict) and result.get("kind") in {"client_action", "player_tool_result"}:
        return False

    if _looks_like_failure_text(text):
        return False

    if direct_final_text:
        if not text:
            return False
        return _looks_like_structured_text(text)

    if isinstance(result, str):
        if not text:
            return True
        return _looks_like_structured_text(text)

    return True


def polish_with_guard(tool_result, *, model: str = "qwen-plus") -> str:
    direct_output = format_structured_output(tool_result)
    if direct_output:
        return direct_output

    llm = _polisher_llm(model)
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"工具执行结果：{_safe_dumps(tool_result)}\n\n"
                "请生成一个自然、友好的纯文本中文回答。"
            ),
        },
    ]
    try:
        response = llm.invoke(messages)
        return response.content if hasattr(response, "content") else str(response)
    except Exception:
        logger.exception("Polisher call failed, fallback to simplified output")
        return _fallback_output(tool_result)


def polish_with_guard_stream(tool_result, *, model: str = "qwen-plus"):
    direct_output = format_structured_output(tool_result)
    if direct_output:
        yield direct_output
        return

    llm = _polisher_llm(model)
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"工具执行结果：{_safe_dumps(tool_result)}\n\n"
                "请生成一个自然、友好的纯文本中文回答。"
            ),
        },
    ]

    def _chunk_text(chunk) -> str:
        content = getattr(chunk, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "".join(parts)
        if content is None:
            return str(chunk)
        return str(content)

    try:
        piece_count = 0
        meaningful_len = 0
        for chunk in llm.stream(messages):
            piece = _chunk_text(chunk)
            piece = str(piece or "")
            if not piece:
                continue
            piece_count += 1
            meaningful_len += len(piece.strip())
            yield piece
        if piece_count >= 2 and meaningful_len >= 8:
            return
    except Exception:
        logger.exception("Polisher stream failed, fallback to simplified output")

    fallback = _fallback_output(tool_result)
    if fallback:
        yield fallback
