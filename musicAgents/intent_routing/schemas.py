from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class IntentType(StrEnum):
    CURRENT_TRACK = "current_track"
    PAUSE = "pause"
    RESUME = "resume"
    NEXT_TRACK = "next_track"
    PREVIOUS_TRACK = "previous_track"
    PLAY_LIKED_SONGS = "play_liked_songs"
    PLAY_RECOMMENDED_SONGS = "play_recommended_songs"
    PLAY_PLAYLIST = "play_playlist"
    PLAY_SONG_SEARCH = "play_song_search"
    PLAY_SCENE_SONGS = "play_scene_songs"


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict[str, Any] = field(default_factory=dict)

    def as_shortcut(self) -> dict[str, Any]:
        return {"tool_name": self.name, "args": dict(self.args)}


@dataclass(frozen=True)
class PlayerIntent:
    intent_type: IntentType
    confidence: float
    tool_call: ToolCall
    source_text: str
    normalized_text: str
    reason: str

    def as_shortcut(self) -> dict[str, Any]:
        return self.tool_call.as_shortcut()
