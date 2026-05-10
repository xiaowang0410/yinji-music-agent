import unittest

from musicAgents.intent_routing import IntentType, route_player_intent
from musicAgents.intent_routing.player_router import (
    chinese_rank_to_int,
    clean_playlist_query,
    clean_song_query,
    extract_rank,
)


class PlayerIntentRoutingTest(unittest.TestCase):
    def assert_tool_call(self, text: str, tool_name: str, args: dict | None = None):
        intent = route_player_intent(text)
        self.assertIsNotNone(intent, text)
        self.assertEqual(tool_name, intent.tool_call.name)
        if args is not None:
            self.assertEqual(args, intent.tool_call.args)
        return intent

    def test_rank_parsing(self):
        self.assertEqual(1, chinese_rank_to_int("一"))
        self.assertEqual(2, chinese_rank_to_int("两"))
        self.assertEqual(10, chinese_rank_to_int("十"))
        self.assertEqual(12, chinese_rank_to_int("十二"))
        self.assertEqual(20, chinese_rank_to_int("二十"))
        self.assertEqual(23, chinese_rank_to_int("二十三"))
        self.assertEqual(3, extract_rank("播放第三首起风了"))

    def test_query_cleaning(self):
        self.assertEqual("起风了", clean_song_query("我想听起风了"))
        self.assertEqual("周杰伦", clean_playlist_query("播放周杰伦歌单"))

    def test_player_controls(self):
        self.assert_tool_call("暂停", "player_pause", {})
        self.assert_tool_call("下一首", "player_next_track", {})
        self.assert_tool_call("上一首", "player_previous_track", {})
        self.assert_tool_call("当前播放的是啥", "player_current_track", {})
        self.assert_tool_call("继续播放", "player_resume", {})

    def test_liked_and_recommended_songs(self):
        self.assert_tool_call("播放我点赞的歌曲", "player_play_liked_songs", {})
        self.assert_tool_call("播放今日推荐", "player_play_recommended_songs", {})

    def test_song_search(self):
        intent = self.assert_tool_call(
            "播放起风了",
            "player_play_song_search",
            {"keywords": "起风了", "rank": 1},
        )
        self.assertEqual(IntentType.PLAY_SONG_SEARCH, intent.intent_type)

        self.assert_tool_call(
            "我想听起风了",
            "player_play_song_search",
            {"keywords": "起风了", "rank": 1},
        )

    def test_scene_music(self):
        intent = self.assert_tool_call(
            "播放适合下雨天听的歌",
            "player_play_mood",
            {"mood": "下雨", "rank": 1},
        )
        self.assertEqual(IntentType.PLAY_SCENE_SONGS, intent.intent_type)

        self.assert_tool_call(
            "来点开心的歌",
            "player_play_mood",
            {"mood": "开心", "rank": 1},
        )

    def test_playlist(self):
        self.assert_tool_call(
            "播放周杰伦歌单",
            "player_play_playlist",
            {"keywords": "周杰伦", "rank": 1},
        )

    def test_plain_resume_does_not_become_song_search(self):
        self.assert_tool_call("播放", "player_resume", {})


if __name__ == "__main__":
    unittest.main()
