from __future__ import annotations

import re
from typing import Any

from musicAgents.intent_routing.patterns import (
    CONTROL_RULES,
    CURRENT_TRACK_RULE,
    LIKED_PATTERN,
    NEW_MUSIC_PATTERN,
    PLAY_VERB_PATTERN,
    PLAYLIST_PATTERN,
    RANK_PATTERN,
    RECOMMENDED_PATTERN,
    RESUME_PATTERN,
    SCENE_PATTERN,
    SCENE_TOKENS,
)
from musicAgents.intent_routing.schemas import IntentType, PlayerIntent, ToolCall


_CHINESE_DIGITS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}

_SCENE_ALIASES = {
    "高兴": "开心",
    "愉快": "开心",
    "快乐": "开心",
    "郁闷": "忧郁",
    "难过": "伤感",
    "emo": "伤感",
    "安静": "放松",
    "助眠": "睡前",
    "深夜": "夜晚",
    "晚上": "夜晚",
    "雨天": "下雨",
}

_RANK_FRAGMENT = r"第[一二两三四五六七八九十\d]+(?:个|首|张|条)?"
_COMMON_PREFIXES = (
    "小听",
    "请",
    "帮我",
    "给我",
    "麻烦",
    "麻烦你",
    "我想要",
    "我想",
    "我要",
    "想",
)
_PLAY_PREFIXES = (
    "播放一下",
    "播放",
    "放一下",
    "放一首",
    "放一个",
    "放",
    "想听",
    "听一下",
    "听听",
    "听",
    "来点",
    "来首",
    "开始放",
)
_CONTENT_SUFFIXES = (
    "里面的歌",
    "里面",
    "里的歌",
    "里的",
    "听的歌",
    "的歌曲",
    "的音乐",
    "的歌",
    "歌曲",
    "音乐",
    "这首歌",
    "首歌",
    "一下",
)
_PUNCTUATION = " ，。！？!?,.;；：:"


def normalize_command_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def chinese_rank_to_int(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text in _CHINESE_DIGITS:
        return _CHINESE_DIGITS[text]
    if len(text) == 2 and text.startswith("十") and text[1] in _CHINESE_DIGITS:
        return 10 + _CHINESE_DIGITS[text[1]]
    if len(text) == 2 and text.endswith("十") and text[0] in _CHINESE_DIGITS:
        return _CHINESE_DIGITS[text[0]] * 10
    if len(text) == 3 and text[1] == "十" and text[0] in _CHINESE_DIGITS and text[2] in _CHINESE_DIGITS:
        return _CHINESE_DIGITS[text[0]] * 10 + _CHINESE_DIGITS[text[2]]
    return None


def extract_rank(text: str) -> int:
    normalized = normalize_command_text(text)
    match = RANK_PATTERN.search(normalized)
    if not match:
        return 1
    rank = chinese_rank_to_int(match.group(1))
    return rank if isinstance(rank, int) and rank > 0 else 1


def _strip_known_prefixes(value: str, prefixes: tuple[str, ...]) -> str:
    current = value.strip(_PUNCTUATION)
    changed = True
    while changed:
        changed = False
        for prefix in sorted(prefixes, key=len, reverse=True):
            if current.startswith(prefix):
                current = current[len(prefix) :].strip(_PUNCTUATION)
                changed = True
                break
    return current


def _strip_known_suffixes(value: str, suffixes: tuple[str, ...]) -> str:
    current = value.strip(_PUNCTUATION)
    changed = True
    while changed:
        changed = False
        for suffix in sorted(suffixes, key=len, reverse=True):
            if current.endswith(suffix) and len(current) > len(suffix):
                current = current[: -len(suffix)].strip(_PUNCTUATION)
                changed = True
                break
    return current


def _clean_common_query(text: str) -> str:
    value = str(text or "").strip()
    value = re.sub(_RANK_FRAGMENT, "", value)
    value = _strip_known_prefixes(value, _COMMON_PREFIXES)
    value = _strip_known_prefixes(value, _PLAY_PREFIXES)
    value = _strip_known_suffixes(value, _CONTENT_SUFFIXES)
    value = re.sub(r"\s+", " ", value)
    return value.strip(_PUNCTUATION)


def clean_playlist_query(text: str) -> str:
    value = _clean_common_query(text)
    value = _strip_known_suffixes(value, ("歌单",))
    return value or _clean_common_query(text)


def clean_song_query(text: str) -> str:
    return _clean_common_query(text)


def extract_scene_keyword(text: str) -> str:
    normalized = normalize_command_text(text)
    for token in SCENE_TOKENS:
        if token in normalized:
            return _SCENE_ALIASES.get(token, token)
    return clean_playlist_query(text) or "推荐"


def _make_intent(
    intent_type: IntentType,
    tool_name: str,
    args: dict[str, Any],
    *,
    confidence: float,
    source_text: str,
    normalized_text: str,
    reason: str,
) -> PlayerIntent:
    return PlayerIntent(
        intent_type=intent_type,
        confidence=confidence,
        tool_call=ToolCall(tool_name, args),
        source_text=source_text,
        normalized_text=normalized_text,
        reason=reason,
    )


def route_player_intent(
    current_question: str,
    rewritten_query: str = "",
    *,
    min_confidence: float = 0.85,
) -> PlayerIntent | None:
    text = (current_question or rewritten_query or "").strip()
    normalized = normalize_command_text(text)
    if not normalized:
        return None

    if CURRENT_TRACK_RULE.pattern.fullmatch(normalized):
        return _make_intent(
            CURRENT_TRACK_RULE.intent_type,
            CURRENT_TRACK_RULE.tool_name,
            {},
            confidence=CURRENT_TRACK_RULE.confidence,
            source_text=text,
            normalized_text=normalized,
            reason=CURRENT_TRACK_RULE.reason,
        )

    for rule in CONTROL_RULES:
        if rule.matches(normalized):
            return _make_intent(
                rule.intent_type,
                rule.tool_name,
                {},
                confidence=rule.confidence,
                source_text=text,
                normalized_text=normalized,
                reason=rule.reason,
            )

    wants_new_music = bool(NEW_MUSIC_PATTERN.search(normalized))
    if not wants_new_music and RESUME_PATTERN.fullmatch(normalized):
        return _make_intent(
            IntentType.RESUME,
            "player_resume",
            {},
            confidence=0.97,
            source_text=text,
            normalized_text=normalized,
            reason="resume command without new music target",
        )

    has_play_verb = bool(PLAY_VERB_PATTERN.search(normalized))
    if not has_play_verb:
        return None

    rank = extract_rank(text)

    if LIKED_PATTERN.search(normalized):
        return _make_intent(
            IntentType.PLAY_LIKED_SONGS,
            "player_play_liked_songs",
            {},
            confidence=0.96,
            source_text=text,
            normalized_text=normalized,
            reason="play liked songs command",
        )

    if RECOMMENDED_PATTERN.search(normalized):
        return _make_intent(
            IntentType.PLAY_RECOMMENDED_SONGS,
            "player_play_recommended_songs",
            {},
            confidence=0.95,
            source_text=text,
            normalized_text=normalized,
            reason="play daily recommended songs command",
        )

    if SCENE_PATTERN.search(normalized):
        return _make_intent(
            IntentType.PLAY_SCENE_SONGS,
            "player_play_mood",
            {"mood": extract_scene_keyword(text), "rank": rank},
            confidence=0.92,
            source_text=text,
            normalized_text=normalized,
            reason="scene or mood music command",
        )

    if PLAYLIST_PATTERN.search(normalized):
        query = clean_playlist_query(text)
        if query:
            intent = _make_intent(
                IntentType.PLAY_PLAYLIST,
                "player_play_playlist",
                {"keywords": query, "rank": rank},
                confidence=0.9,
                source_text=text,
                normalized_text=normalized,
                reason="playlist playback command",
            )
            return intent if intent.confidence >= min_confidence else None

    query = clean_song_query(text)
    if query:
        intent = _make_intent(
            IntentType.PLAY_SONG_SEARCH,
            "player_play_song_search",
            {"keywords": query, "rank": rank},
            confidence=0.88,
            source_text=text,
            normalized_text=normalized,
            reason="song search playback command",
        )
        return intent if intent.confidence >= min_confidence else None

    return None
