from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Pattern

from musicAgents.intent_routing.schemas import IntentType


def compile_pattern(value: str) -> Pattern[str]:
    return re.compile(value)


PLAY_VERBS = ("播放", "放", "听", "来点", "来首", "开始放", "想听")
SCENE_TOKENS = (
    "开心",
    "快乐",
    "高兴",
    "愉快",
    "忧郁",
    "郁闷",
    "难过",
    "伤感",
    "emo",
    "治愈",
    "放松",
    "安静",
    "热血",
    "睡前",
    "助眠",
    "工作",
    "学习",
    "运动",
    "通勤",
    "清晨",
    "夜晚",
    "深夜",
    "晚上",
    "孤独",
    "浪漫",
    "下雨",
    "雨天",
    "阴天",
    "晴天",
    "黄昏",
    "午后",
)
NEW_MUSIC_TOKENS = (
    "点赞",
    "喜欢",
    "收藏",
    "推荐",
    "歌单",
    "歌曲",
    "音乐",
    *SCENE_TOKENS,
)


@dataclass(frozen=True)
class PlayerIntentRule:
    intent_type: IntentType
    tool_name: str
    pattern: Pattern[str]
    confidence: float
    reason: str

    def matches(self, normalized_text: str) -> bool:
        return bool(self.pattern.search(normalized_text))


CURRENT_TRACK_RULE = PlayerIntentRule(
    intent_type=IntentType.CURRENT_TRACK,
    tool_name="player_current_track",
    pattern=compile_pattern(
        r"^((当前|现在)(播放|放着|正在放|在播)(的)?(歌曲|歌|音乐)?(是啥|是什么|哪首|叫什么)?"
        r"|(播放|放着|正在放|在播)(的)?(歌曲|歌|音乐)?(是啥|是什么|哪首|叫什么))$"
    ),
    confidence=0.98,
    reason="current track query",
)

CONTROL_RULES = (
    PlayerIntentRule(
        intent_type=IntentType.PAUSE,
        tool_name="player_pause",
        pattern=compile_pattern(r"暂停|停一下|先停|停止播放|别放了|安静一下"),
        confidence=0.99,
        reason="pause command",
    ),
    PlayerIntentRule(
        intent_type=IntentType.NEXT_TRACK,
        tool_name="player_next_track",
        pattern=compile_pattern(r"下一首|下首|切歌|换一首"),
        confidence=0.99,
        reason="next track command",
    ),
    PlayerIntentRule(
        intent_type=IntentType.PREVIOUS_TRACK,
        tool_name="player_previous_track",
        pattern=compile_pattern(r"上一首|上首|前一首"),
        confidence=0.99,
        reason="previous track command",
    ),
)

RESUME_PATTERN = compile_pattern(r"^(继续播放|继续放|开始播放|播放吧|接着放|恢复播放|播放|开始|继续)$")
PLAY_VERB_PATTERN = compile_pattern(r"(播放|放|听|来点|来首|想听|开始放)")
LIKED_PATTERN = compile_pattern(r"(点赞|喜欢|收藏)")
RECOMMENDED_PATTERN = compile_pattern(r"(每日推荐|今日推荐)")
PLAYLIST_PATTERN = compile_pattern(r"歌单")
SCENE_PATTERN = compile_pattern("|".join(re.escape(token) for token in SCENE_TOKENS))
NEW_MUSIC_PATTERN = compile_pattern("|".join(re.escape(token) for token in NEW_MUSIC_TOKENS))
RANK_PATTERN = compile_pattern(r"第([一二两三四五六七八九十\d]+)(?:个|首|张|条)?")
