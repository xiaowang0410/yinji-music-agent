import functools
import json
import re
import threading
from datetime import time
from typing import Any



from tools.MusicTools.node_ncm_client import NeteaseCloudMusicApi
from langchain_core.tools import tool
from mpmath import limit
from tools.MusicTools import music_config
from tools.MusicTools.music_config import param_info, playlist_tags, artist_list_params, song_url_v1_params
from tools.MusicTools.ncm_env import get_ncm_process_env
from tools.MusicTools.user_account import Music_account

user_id = None
user_name = None
cookie = {}

# 确保api不为None
api = None
if False:
    print("[警告] 警告：无法初始化网易云音乐API")

# 导入WebSearch工具
import requests


_INTERNAL_API_ERROR_MARKERS = (
    "access violation",
    "maximum call stack",
    "failed to register environment variables",
    "error during request setup",
    "anonymous registration",
    "not a function",
    "[err]",
    "url using bad/illegal format",
)


def _looks_like_internal_api_failure(exc: Any) -> bool:
    text = str(exc or "").strip().lower()
    if not text:
        return False
    return any(marker in text for marker in _INTERNAL_API_ERROR_MARKERS)


def _friendly_tool_failure(message: str, exc: Any = None) -> str:
    if exc is not None:
        print(f"[失败] 详细异常: {exc}")
    return str(message or "").strip() or "请求失败，请稍后再试"


def _safe_response_status(response: Any) -> int | None:
    try:
        status = getattr(response, "status", None)
        return int(status) if status is not None else None
    except Exception as e:
        print(f"[失败] 获取响应状态失败: {e}")
        return None


def _safe_response_body(response: Any) -> dict[str, Any]:
    try:
        body = getattr(response, "body", {})
        return body if isinstance(body, dict) else {}
    except Exception as e:
        print(f"响应解析失败，使用默认值 {e}")
        return {}


_NCM_API_LOCK = threading.RLock()


class _LockedMusicApiProxy:
    """Serialize access to the native NCM client to avoid concurrent corruption."""

    def __init__(self, api_instance: Any):
        self._api = api_instance

    def __getattr__(self, name: str):
        target = getattr(self._api, name)
        if not callable(target):
            return target

        @functools.wraps(target)
        def _locked_call(*args, **kwargs):
            with _NCM_API_LOCK:
                return getattr(self._api, name)(*args, **kwargs)

        return _locked_call


def _wrap_music_api(api_instance: Any):
    if api_instance is None or isinstance(api_instance, _LockedMusicApiProxy):
        return api_instance
    return _LockedMusicApiProxy(api_instance)


api = _wrap_music_api(api)


def _unwrap_music_api(api_instance: Any):
    return getattr(api_instance, "_api", api_instance)


def _destroy_music_api(api_instance: Any) -> None:
    raw_api = _unwrap_music_api(api_instance)
    destroy = getattr(raw_api, "destroy", None)
    if not callable(destroy):
        return
    try:
        with _NCM_API_LOCK:
            destroy()
    except Exception as exc:
        print(f"[失败] 释放音乐会话失败: {exc}")


def _open_music_session(*, force_refresh_env: bool = False):
    session_api, session_user_id, session_user_name, session_cookie = Music_account(
        force_refresh_env=force_refresh_env
    )
    return _wrap_music_api(session_api), session_user_id, session_user_name, session_cookie


def _open_music_api_only(*, force_refresh_env: bool = False):
    try:
        session_api = NeteaseCloudMusicApi(env=get_ncm_process_env(force_refresh=force_refresh_env))
        session_cookie = music_config.get_music_cookie()
        if session_cookie:
            session_api.set_cookie(session_cookie)
        else:
            music_config.warn_missing_music_cookie()
        return _wrap_music_api(session_api), session_cookie
    except Exception as exc:
        print(f"[失败] 初始化歌曲播放会话失败: {exc}")
        return None, None


_GLOBAL_SESSION_STATE_LOCK = threading.RLock()
_GLOBAL_SESSION_API = None


def _ensure_global_music_session(*, force_refresh: bool = False):
    global _GLOBAL_SESSION_API, user_id, user_name, cookie

    with _GLOBAL_SESSION_STATE_LOCK:
        if not force_refresh and _GLOBAL_SESSION_API is not None:
            return _GLOBAL_SESSION_API, user_id, user_name, cookie

        session_api, session_user_id, session_user_name, session_cookie = _open_music_session(
            force_refresh_env=force_refresh
        )
        session_api = _wrap_music_api(session_api)

        if session_api is not None:
            _GLOBAL_SESSION_API = session_api
            user_id = session_user_id
            user_name = session_user_name
            cookie = session_cookie or {}
            return _GLOBAL_SESSION_API, user_id, user_name, cookie

        if force_refresh:
            _GLOBAL_SESSION_API = None
            user_id = None
            user_name = None
            cookie = {}

        return _GLOBAL_SESSION_API, user_id, user_name, cookie


class _LazyGlobalMusicApiProxy:
    def __getattr__(self, name: str):
        session_api, _, _, _ = _ensure_global_music_session()
        if session_api is None:
            raise RuntimeError("music_api_unavailable")
        return getattr(session_api, name)


api = _LazyGlobalMusicApiProxy()


def _response_error_text(response: Any) -> str:
    body = _safe_response_body(response)
    if not body:
        return ""
    parts = []
    for key in ("message", "msg", "error", "detail"):
        value = str(body.get(key) or "").strip()
        if value:
            parts.append(value)
    return " | ".join(parts)


def _should_retry_ncm_response(response: Any) -> bool:
    if response is None:
        return True

    status = _safe_response_status(response)
    if status == 200:
        return False
    if status is None or status >= 500:
        return True
    return _looks_like_internal_api_failure(_response_error_text(response))


def _join_artist_names(artists: Any) -> str:
    if not isinstance(artists, list):
        return ""
    return " / ".join(
        [str(item.get("name") or "").strip() for item in artists if isinstance(item, dict) and item.get("name")]
    ).strip()


def _extract_song_album_name(song: Any) -> str:
    if not isinstance(song, dict):
        return ""
    album = song.get("al")
    if not isinstance(album, dict):
        album = song.get("album")
    if not isinstance(album, dict):
        return ""
    return str(album.get("name") or "").strip()


def _extract_song_cover_url(song: Any) -> str:
    if not isinstance(song, dict):
        return ""
    album = song.get("al")
    if not isinstance(album, dict):
        album = song.get("album")
    if isinstance(album, dict):
        for key in ("picUrl", "blurPicUrl"):
            value = str(album.get(key) or "").strip()
            if value:
                return value
    return str(song.get("picUrl") or "").strip()


def _extract_playlist_cover_url(playlist: Any) -> str:
    if not isinstance(playlist, dict):
        return ""
    for key in ("coverImgUrl", "picUrl", "coverImageUrl", "backgroundCoverUrl"):
        value = str(playlist.get(key) or "").strip()
        if value:
            return value
    return ""


def _build_liked_songs_result(
    songs: list[dict[str, Any]],
    summary_prefix: str = "成功获取点赞歌曲",
) -> dict[str, Any] | str:
    total = len(songs)
    if total <= 0:
        return "暂无点赞歌曲"

    preview_count = min(total, 12)
    preview = [f"{s['name']} - {s['artist']}".strip(" -") for s in songs[:preview_count]]
    summary = f"{summary_prefix}（共{total}首）"
    if preview_count:
        summary += f"，先展示前{preview_count}首"

    return {
        "title": "我帮你把点赞歌曲整理好了",
        "summary": summary,
        "total": total,
        "songs": songs,
        "preview": preview,
    }



@tool(description="获取某首歌歌的歌词")
def song_lyrics(song_id:str)-> str | None:
    """
    :param song_id: str
    :return: 歌词 str
    """
    print(f"正在获取歌曲:{song_id}的歌词...")
    fallback_message = "暂时获取不到这首歌的歌词，请稍后再试"

    for attempt in range(2):
        session_api = None
        try:
            with _NCM_API_LOCK:
                session_api, _ = _open_music_api_only(force_refresh_env=attempt > 0)
                if session_api is None:
                    continue
                response = session_api.lyric(id=song_id)

            if _should_retry_ncm_response(response) and attempt == 0:
                continue

            response_status = _safe_response_status(response)
            response_body = _safe_response_body(response)
            if response_status == 200:
                print(f"已获取歌曲:{song_id}的歌词...")
                lyric_data = response_body.get("lrc", {})
                if isinstance(lyric_data, dict):
                    return str(lyric_data.get("lyric") or "")
                return ""
        except Exception as e:
            print(f"[失败]获取歌词失败 : {e}")
            if attempt == 0 and _looks_like_internal_api_failure(e):
                continue
            return _friendly_tool_failure(fallback_message, e)
        finally:
            _destroy_music_api(session_api)

    return _friendly_tool_failure(fallback_message)
        


@tool(description="传入搜索关键词可以搜索该音乐 type=1 / 专辑 type=10/ 歌手歌手, type=100 / 歌单 type=1000/ 用户 type=1000,参数：keywords: 搜索关键词,type: 搜索类型")
def search(keywords,type=1,limit=20):
    """
        type: 搜索类型；默认为 1 即单曲 , 取值意义 : 1: 单曲, 10: 专辑, 100: 歌手, 1000:
        歌单, 1002: 用户, 1004: MV, 1006: 歌词, 1009: 电台, 1014: 视频, 1018:综合, 2000:声音(搜索声音返回字段格式会不一样)
        接口地址 : /search 或者 /cloudsearch(更全)
        调用例子 : /search?keywords=海阔天空 /cloudsearch?keywords=海阔天空
    :param keywords:
    :return:
    """
    try:
        print("正在搜索...")
        try:
            resolved_limit = int(limit)
        except (TypeError, ValueError):
            resolved_limit = 20
        if resolved_limit <= 0:
            resolved_limit = 20
        resolved_limit = min(resolved_limit, 50)

        resolved_type = 1
        try:
            resolved_type = int(type)
        except (TypeError, ValueError):
            raw_type = str(type or "").strip().lower()
            type_aliases = {
                "song": 1,
                "songs": 1,
                "music": 1,
                "single": 1,
                "album": 10,
                "albums": 10,
                "artist": 100,
                "artists": 100,
                "singer": 100,
                "playlist": 1000,
                "playlists": 1000,
                "user": 1002,
                "users": 1002,
                "mv": 1004,
                "mvs": 1004,
                "lyric": 1006,
                "lyrics": 1006,
                "radio": 1009,
                "dj": 1009,
                "video": 1014,
                "videos": 1014,
                "all": 1018,
                "voice": 2000,
                "sound": 2000,
            }
            mapped_type = type_aliases.get(raw_type)
            if mapped_type is not None:
                resolved_type = mapped_type
            else:
                query_text = str(keywords or "").strip().lower()
                if re.search(r"专辑|album", query_text, flags=re.IGNORECASE):
                    resolved_type = 10
                elif re.search(r"歌单|playlist|播放列表|榜单|排行榜", query_text, flags=re.IGNORECASE):
                    resolved_type = 1000
                elif re.search(r"歌手|艺人|artist|singer", query_text, flags=re.IGNORECASE):
                    resolved_type = 100
                elif re.search(r"用户|user|主页", query_text, flags=re.IGNORECASE):
                    resolved_type = 1002
                elif re.search(r"歌词|lyric", query_text, flags=re.IGNORECASE):
                    resolved_type = 1006
                elif re.search(r"电台|radio|\bdj\b|播客", query_text, flags=re.IGNORECASE):
                    resolved_type = 1009

        query_text = str(keywords or "").strip().lower()
        if resolved_type == 1:
            if any(token in query_text for token in ("album", "专辑")):
                resolved_type = 10
            elif any(token in query_text for token in ("playlist", "歌单", "播放列表", "榜单", "排行榜")):
                resolved_type = 1000
            elif any(token in query_text for token in ("artist", "singer", "歌手", "艺人")):
                resolved_type = 100
            elif any(token in query_text for token in ("user", "用户", "主页")):
                resolved_type = 1002
            elif any(token in query_text for token in ("lyric", "歌词")):
                resolved_type = 1006
            elif any(token in query_text for token in ("radio", "dj", "电台", "播客")):
                resolved_type = 1009

        if resolved_type <= 0:
            resolved_type = 1

        response = api.search(keywords=keywords, type=resolved_type, limit=resolved_limit)
        if response.status == 200:
            print("已搜索...")

            print(f"[成功] 搜索完成: {keywords}")

            body = response.body
            simplified_result = {}
            detail_cover_map = {}

            if 'result' in body and 'songs' in body['result']:
                try:
                    search_song_ids = [
                        str(song.get('id') or '').strip()
                        for song in body['result']['songs'][:resolved_limit]
                        if isinstance(song, dict) and song.get('id')
                    ]
                    if search_song_ids:
                        detail_response = api.song_detail(ids=",".join(search_song_ids))
                        if detail_response and detail_response.status == 200:
                            for detail_song in detail_response.body.get('songs', []) or []:
                                if not isinstance(detail_song, dict):
                                    continue
                                detail_song_id = str(detail_song.get('id') or '').strip()
                                if not detail_song_id:
                                    continue
                                detail_cover_map[detail_song_id] = _extract_song_cover_url(detail_song)
                except Exception as detail_error:
                    print(f"[璀﹀憡] 鎼滅储缁撴灉灏侀潰琛ュ叏澶辫触: {detail_error}")

            if 'result' in body and 'songs' in body['result']:
                simplified_songs = []
                for song in body['result']['songs'][:resolved_limit]:
                    artists = song.get('artists')
                    if not isinstance(artists, list):
                        artists = song.get('ar', [])

                    album = song.get('album')
                    if not isinstance(album, dict):
                        album = song.get('al', {})

                    simplified_song = {
                        'id': song.get('id'),
                        'name': song.get('name'),
                        'artist': _join_artist_names(artists),
                        'artists': [{'id': a.get('id'), 'name': a.get('name')} for a in artists if isinstance(a, dict)],
                        'album': {
                            'id': album.get('id'),
                            'name': album.get('name'),
                            'picUrl': album.get('picUrl') or detail_cover_map.get(str(song.get('id') or '').strip(), ''),
                        },
                        'cover_url': _extract_song_cover_url(song) or detail_cover_map.get(str(song.get('id') or '').strip(), ''),
                        'duration': song.get('duration', song.get('dt')),
                    }
                    simplified_songs.append(simplified_song)
                simplified_result['songs'] = simplified_songs

            if 'result' in body and 'albums' in body['result']:
                simplified_albums = []
                for album in body['result']['albums'][:min(resolved_limit, 20)]:
                    artists = album.get('artists')
                    if not isinstance(artists, list):
                        artist = album.get('artist')
                        if isinstance(artist, dict):
                            artists = [artist]
                        elif isinstance(artist, list):
                            artists = artist
                        else:
                            artists = []

                    simplified_album = {
                        'id': album.get('id'),
                        'name': album.get('name'),
                        'artist': _join_artist_names(artists),
                        'artists': [{'id': a.get('id'), 'name': a.get('name')} for a in artists if isinstance(a, dict)],
                        'cover_url': album.get('picUrl') or album.get('blurPicUrl') or '',
                        'publishTime': album.get('publishTime'),
                        'size': album.get('size'),
                    }
                    simplified_albums.append(simplified_album)
                simplified_result['albums'] = simplified_albums

            if 'result' in body and 'playlists' in body['result']:
                simplified_playlists = []
                for playlist in body['result']['playlists'][:min(resolved_limit, 20)]:
                    simplified_playlist = {
                        'id': playlist.get('id'),
                        'name': playlist.get('name'),
                        'creator': playlist.get('creator', {}).get('nickname', ''),
                        'trackCount': playlist.get('trackCount')
                    }
                    simplified_playlists.append(simplified_playlist)
                simplified_result['playlists'] = simplified_playlists

            if 'result' in body and 'artists' in body['result']:
                simplified_artists = []
                for artist in body['result']['artists'][:min(resolved_limit, 20)]:
                    simplified_artist = {
                        'id': artist.get('id'),
                        'name': artist.get('name'),
                        'picUrl': artist.get('picUrl')
                    }
                    simplified_artists.append(simplified_artist)
                simplified_result['artists'] = simplified_artists

            return simplified_result

    except Exception as e:
        print(f"[失败] 搜索时出错: {e}")
        return {"错误": f"搜索时出错: {str(e)}"}

@tool(description="默认搜索关键词")
def search_default():
    """
    默认搜索关键词
    说明 : 调用此接口 , 可获取默认搜索关键词
    """
    try:
        print("正在获取默认搜索关键词")
        response = api.search_default()
        if response.status == 200:
            print("已获取默认搜索关键词")

            default_keyword = response.body.get('data', {}).get('showKeyword', '')
            if default_keyword:
                print(f"[成功] 默认搜索关键词: {default_keyword}")

            return {'default_keyword': default_keyword}
    except Exception as e:
        print(f"[失败] 获取默认搜索关键词时出错: {e}")
        return {"错误": f"获取默认搜索关键词时出错: {str(e)}"}


@tool(description="获取热门搜索列表，只能获取10首")
def search_hot():
    """
    获取热搜列表(简略只能获取10首)
    """
    try:
        print("正在获取热搜列表")
        response = api.search_hot()
        if response.status == 200:
            print("已获取热搜列表")

            hot_items = response.body.get('result', {}).get('hots', [])
            if hot_items:
                print(f"[成功] 已获取热门搜索关键词，共{len(hot_items)}条")

            simplified_hot = []
            for item in hot_items:
                simplified_item = {
                    'keyword': item.get('first', ''),
                    'score': item.get('second', 0)
                }
                simplified_hot.append(simplified_item)

            return {'hot_keywords': simplified_hot}
    except Exception as e:
        print(f"[失败] 获取热搜列表时出错: {e}")
        return {"错误": f"获取热搜列表时出错: {str(e)}"}

@tool(description="获取热搜列表（详细）")
def search_hot_detail():
    """
    获取热搜列表（详细）
    """
    try:
        print("正在获取热搜列表（详细）")
        response = api.search_hot_detail()
        if response.status == 200:
            print("已获取热搜列表（详细）")

            print("[成功] 详细热门搜索关键词已获取，共20条")

            hot_details = response.body.get('data', [])
            simplified_hot = []
            for item in hot_details:
                simplified_item = {
                    'keyword': item.get('searchWord', ''),
                    'score': item.get('score', 0),
                    'content': item.get('content', '')
                }
                simplified_hot.append(simplified_item)

            return {'hot_details': simplified_hot}
    except Exception as e:
        print(f"[失败] 获取热搜列表（详细）时出错: {e}")
        return {"错误": f"获取热搜列表（详细）时出错: {str(e)}"}



@tool(description=f"获取网易云对应id歌曲的详情信息\n{param_info}")
def song_details(song_id:str)-> None | list[Any] | str:
    try:
        print("正在获取歌曲详细信息")
        response = api.song_detail(ids=song_id)
        if response.status == 200:
            print("已获取歌曲详细信息")


            # 优化返回结果，只保留关键信息
            songs = response.body.get('songs', [])
            simplified_songs = []
            for song in songs:
                simplified_song = {
                    'id': song.get('id'),
                    'name': song.get('name'),
                    'artists': [{'id': a.get('id'), 'name': a.get('name')} for a in song.get('ar', [])],
                    'album': {'id': song.get('al', {}).get('id'), 'name': song.get('al', {}).get('name'), 'picUrl': song.get('al', {}).get('picUrl')},
                    'duration': song.get('dt'),
                    'publishTime': song.get('publishTime')
                }
                simplified_songs.append(simplified_song)
            
            return simplified_songs
    except Exception as e:
        print(f"[失败] 获取歌曲详情时出错: {e}")
        return f"获取歌曲详情时出错: {e}"




@tool(description="获取搜索建议选  参数 : keywords : 关键词 可选参数 : type : 如果传 'mobile' 则返回移动端数")
def search_suggest(keywords:str, type:str=None ):
    """
        搜索建议
        说明 : 调用此接口 , 传入搜索关键词可获得搜索建议 , 搜索结果同时包含单曲 , 歌手 , 歌单信息
        必选参数 : keywords : 关键词
        可选参数 : type : 如果传 'mobile' 则返回移动端数据
    """
    try:
        print("正在获取搜索建议")
        response = api.search_suggest(keywords=keywords,type=type )
        if response.status == 200:
            print("已获取搜索建议")
            
            # 优化返回结果，只保留关键信息
            result = response.body.get('result', {})
            simplified_result = {}
            
            # 处理歌曲结果
            if 'songs' in result:
                simplified_songs = []
                for song in result['songs'][:5]:  # 只保留前5首
                    simplified_song = {
                        'id': song.get('id'),
                        'name': song.get('name'),
                        'artists': [{'id': a.get('id'), 'name': a.get('name')} for a in song.get('artists', [])],
                        'album': {'id': song.get('album', {}).get('id'), 'name': song.get('album', {}).get('name')},
                        'duration': song.get('duration')
                    }
                    simplified_songs.append(simplified_song)
                simplified_result['songs'] = simplified_songs
            
            # 处理歌手结果
            if 'artists' in result:
                simplified_artists = []
                for artist in result['artists'][:3]:  # 只保留前3个
                    simplified_artist = {
                        'id': artist.get('id'),
                        'name': artist.get('name'),
                        'picUrl': artist.get('picUrl')
                    }
                    simplified_artists.append(simplified_artist)
                simplified_result['artists'] = simplified_artists
            
            # 处理专辑结果
            if 'albums' in result:
                simplified_albums = []
                for album in result['albums'][:3]:  # 只保留前3个
                    simplified_album = {
                        'id': album.get('id'),
                        'name': album.get('name'),
                        'artist': album.get('artist', {}).get('name'),
                        'publishTime': album.get('publishTime'),
                        'picId': album.get('picId')
                    }
                    simplified_albums.append(simplified_album)
                simplified_result['albums'] = simplified_albums
            
            return simplified_result
    except Exception as e:
        print(f"[失败] 获取搜索建议时出错: {e}")
        return {"错误": f"获取搜索建议时出错: {str(e)}"}

@tool(description="获取多重匹配 必选参数 : keywords : 关键词  传入搜索关键词可获得搜索结果")
def search_multimatch(keywords:str):
    try:
        print("正在获取多重匹配")
        response = api.search_multimatch(keywords=keywords )
        if response.status == 200:
            print("已获取多重匹配")
            
            # 优化返回结果，只保留关键信息
            result = response.body.get('result', {})
            simplified_result = {}
            
            # 处理歌手结果
            if 'artist' in result:
                simplified_artists = []
                for artist in result['artist'][:3]:  # 只保留前3个
                    simplified_artist = {
                        'id': artist.get('id'),
                        'name': artist.get('name'),
                        'picUrl': artist.get('picUrl'),
                        'albumSize': artist.get('albumSize'),
                        'musicSize': artist.get('musicSize')
                    }
                    simplified_artists.append(simplified_artist)
                simplified_result['artists'] = simplified_artists
            
            # 处理专辑结果
            if 'album' in result:
                simplified_albums = []
                for album in result['album'][:3]:  # 只保留前3个
                    simplified_album = {
                        'id': album.get('id'),
                        'name': album.get('name'),
                        'artist': album.get('artist', {}).get('name'),
                        'publishTime': album.get('publishTime'),
                        'picUrl': album.get('picUrl'),
                        'size': album.get('size')
                    }
                    simplified_albums.append(simplified_album)
                simplified_result['albums'] = simplified_albums
            
            # 处理歌曲结果
            if 'songs' in result:
                simplified_songs = []
                for song in result['songs'][:5]:  # 只保留前5首
                    simplified_song = {
                        'id': song.get('id'),
                        'name': song.get('name'),
                        'artists': [{'id': a.get('id'), 'name': a.get('name')} for a in song.get('ar', [])],
                        'album': {'id': song.get('al', {}).get('id'), 'name': song.get('al', {}).get('name')},
                        'duration': song.get('dt')
                    }
                    simplified_songs.append(simplified_song)
                simplified_result['songs'] = simplified_songs
            
            return simplified_result
    except Exception as e:
        print(f"[失败] 获取多重匹配时出错: {e}")
        return {"错误": f"获取多重匹配时出错: {str(e)}"}

@tool(description="获取我点赞的歌")
def liked_songs():
    """
    获取网易云我点赞的歌曲
:return: 结构化的歌曲列表
    """
    try:
        # 1. 获取点赞歌曲ID
        liked_response = api.likelist(uid=user_id )
        if liked_response.status != 200:
            return f"获取失败：{liked_response.body.get('message', '未知错误')}"

        liked_song_ids = liked_response.body.get('ids', [])
        if not liked_song_ids:
            return "暂无点赞歌曲"

        # 2. 批量获取歌曲详情
        ids_str = ','.join(map(str, liked_song_ids))
        detail_response = api.song_detail(ids=ids_str )
        songs = detail_response.body.get('songs', [])

        liked_songs_list = []
        for song in songs:
            song_id = song["id"]
            song_name = song["name"]
            duration = song.get("dt", 0)
            publish_time = song.get("publishTime", 0)
            album = song.get("al", {}) or {}
            album_name = album.get("name", "")
            cover_url = album.get("picUrl", "")

            # 多歌手处理
            artists = song.get("ar", [])
            artist_name = ', '.join([a["name"] for a in artists])
            artist_id = artists[0]["id"] if artists else 0

            # 添加到返回列表
            liked_songs_list.append({
                'id': song_id,
                'name': song_name,
                'artist': artist_name,
                'album': album_name,
                'cover_url': cover_url,
                'duration_ms': duration,
                'publish_time': publish_time,
            })



        total = len(liked_songs_list)
        preview_count = min(total, 12)
        preview = [f"{s['name']} - {s['artist']}" for s in liked_songs_list[:preview_count]]
        summary = f"成功获取点赞歌曲（共{total}首）"
        if preview_count:
            summary += f"，先展示前{preview_count}首"

        return {
            "title": "我帮你把点赞歌曲整理好了",
            "summary": summary,
            "total": total,
            "songs": liked_songs_list,
            "preview": preview,
        }

    except Exception as e:
        return f"获取点赞歌曲出错：{str(e)}"





def user_detail()-> str | dict[str | Any, Any]:
    try:
        session_api, current_uid, _, _ = _ensure_global_music_session()
        if session_api is None:
            return "[警告] 网易云音乐API未初始化"
        if current_uid is None:
            return "[警告] 用户未登录"
        user_detail_response = session_api.user_detail(uid=current_uid)
        if user_detail_response.status == 200:
            print("已获取用户信息")
            # 优化返回结果，只保留关键信息
            body = user_detail_response.body
            profile = body.get('profile', {})
            simplified_user_info = {
                'userId': profile.get('userId'),
                'nickname': profile.get('nickname'),
                'signature': profile.get('signature'),
                'gender': profile.get('gender'),
                'birthday': profile.get('birthday'),
                'province': profile.get('province'),
                'city': profile.get('city'),
                'followeds': profile.get('followeds'),
                'follows': profile.get('follows'),
                'playlistCount': profile.get('playlistCount'),
                'eventCount': profile.get('eventCount'),
                'level': body.get('level', 0)
            }
            return simplified_user_info
        else:
            return f"[失败] 获取失败: {user_detail_response.body.get('message', '未知错误')}"
    except Exception as e:
        print(f"[失败] 获取用户信息时出错: {e}")
        return f"[失败] 获取用户信息失败: {str(e)}"

@tool(description="获取用户歌单，收藏，mv, dj 数量")
def user_subcount():
    try:
        user_subcount_response = api.user_subcount()
        if user_subcount_response.status == 200:
            print("已获取用户信息 , 歌单，收藏，mv, dj 数量信息")
            

            
            return user_subcount_response.body
    except Exception as e:
        print(f"[失败] 获取用户信息 , 歌单，收藏，mv, dj 数量时出错: {e}")
        return {"错误": f"获取用户信息 , 歌单，收藏，mv, dj 数量时出错: {str(e)}"}

@tool(description="获取用户等级信息,包含当前登录天数,听歌次数,下一等级需要的登录天数和听歌次数,当前等级进度")
def user_level():
    try:
        user_level_response = api.user_level()
        if user_level_response.status == 200:
            print("已获取用户等级信息")
            return user_level_response.body
    except Exception as e:
        print(f"[失败] 获取用户等级信息时出错: {e}")
        return {"错误": f"获取用户等级信息时出错: {str(e)}"}

@tool(description="获取用户绑定信息")
def user_binding():
    try:
        user_binding_response = api.user_binding(uid=user_id )
        if user_binding_response.status == 200:
            print("已获取用户绑定信息")
            
            # 优化返回结果，只保留关键信息，移除敏感的token信息
            body = user_binding_response.body
            bindings = body.get('bindings', [])
            simplified_bindings = []
            
            for binding in bindings:
                binding_type = binding.get('type', 0)
                binding_name = ""
                if binding_type == 1:
                    binding_name = "手机号"
                elif binding_type == 5:
                    binding_name = "微信"
                elif binding_type == 6:
                    binding_name = "QQ"
                elif binding_type == 7:
                    binding_name = "微博"
                else:
                    binding_name = f"类型{binding_type}"
                
                simplified_binding = {
                    'type': binding_type,
                    'type_name': binding_name,
                    'bindingTime': binding.get('bindingTime'),
                    'expired': binding.get('expired')
                }
                simplified_bindings.append(simplified_binding)
            
            return {'bindings': simplified_bindings}
    except Exception as e:
        print(f"[失败] 获取用户绑定信息时出错: {e}")
        return {"错误": f"获取用户绑定信息时出错: {str(e)}"}


@tool(description="更新用户信息, 更改的传入，其余为None,gender: 性别 0:保密 1:男性 2:女性  birthday: 出生日期,  时间戳 unix timestamp,   nickname: 用户昵称 province: 省份id, city: 城市id, signature：用户签名, :return: 新的用户信息")
def user_update(gender=None,birthday=None,nickname=None,province=None,city=None,signature=None):


    try:
        # 先获取当前用户信息
        print("正在获取当前用户信息...")
        user_detail_response = api.user_detail(uid=user_id)
        print(user_detail_response.body)
        if user_detail_response.status == 200:
            profile = user_detail_response.body.get('profile', {})

            current_gender = profile.get('gender', 0)
            current_birthday = profile.get('birthday', 0)
            current_nickname = profile.get('nickname', '')
            current_province = profile.get('province', 0)
            current_city = profile.get('city', 0)
            current_signature = profile.get('signature', '')

            print(f"当前用户信息: gender={current_gender}, birthday={current_birthday}, nickname={current_nickname}, province={current_province}, city={current_city}, signature={current_signature}")
            final_gender = gender if gender is not None else current_gender
            final_birthday = birthday if birthday is not None else current_birthday
            final_nickname = nickname if nickname is not None else current_nickname
            final_province = province if province is not None else current_province
            final_city = city if city is not None else current_city
            final_signature = signature if signature is not None else current_signature

            print(f"更改后的信息: gender={final_gender}, birthday={final_birthday}, nickname={final_nickname}, province={final_province}, city={final_city}, signature={final_signature}")

            print("正在更新用户信息...")
            user_update_response = api.user_update(
                gender=final_gender,
                birthday=final_birthday,
                nickname=final_nickname,
                province=final_province,
                city=final_city,
                signature=final_signature,
                cookie=cookie
            )
            if user_update_response.status == 200:
                print("[成功] 用户信息已更新")
                return user_update_response.body
            else:
                return f"更新失败: {user_update_response.body.get('message', '未知错误')}"
        else:
            return "获取当前用户信息失败"
    except Exception as e:
        print(f"[失败] 更新用户信息时出错: {e}")
        return f"更新失败: {str(e)}"


@tool(description="私信和通知接口,调用此工具，可获取私信和通知数量信息")
def pl_count():
    try:
        pl_count_response = api.pl_count()
        if pl_count_response.status == 200:
            print("已获取用户私信和通知数量信息")
            
            # 优化返回结果，只保留关键信息
            body = pl_count_response.body
            simplified_result = {
                'notice': body.get('notice', 0),
                'msg': body.get('msg', 0),
                'comment': body.get('comment', 0),
                'totalComment': body.get('totalComment', 0),
                'pushMsg': body.get('pushMsg', ''),
                'event': body.get('event', 0),
                'newProgramCount': body.get('newProgramCount', 0)
            }
            return simplified_result
    except Exception as e:
        print(f"[失败] 获取用户私信和通知数量信息时出错: {e}")
        return {"错误": f"获取用户私信和通知数量信息时出错: {str(e)}"}

@tool(description="获取私信内容，可选参数: limit: 返回数量, offset: 偏移数量")
def get_private_messages(limit=30, offset=0):
    """
    获取私信内容
    可选参数: limit: 返回数量, offset: 偏移数量
    """
    try:
        print("正在获取私信内容...")
        response = api.msg_private( limit=limit, offset=offset)
        if response.status == 200:
            print("[成功] 已获取私信内容")
            return response.body
        else:
            return f"获取私信内容失败: {response.body.get('message', '未知错误')}"
    except Exception as e:
        print(f"[失败] 获取私信内容时出错: {e}")
        return f"获取私信内容失败: {str(e)}"

@tool(description="获取通知内容，可选参数: limit: 返回数量")
def get_notices(limit=30):
    """
    获取通知内容
    可选参数: limit: 返回数量
    """
    try:
        print("正在获取通知内容...")
        response = api.msg_notices( limit=limit)
        if response.status == 200:
            print("[成功] 已获取通知内容")
            return response.body
        else:
            return f"获取通知内容失败: {response.body.get('message', '未知错误')}"
    except Exception as e:
        print(f"[失败] 获取通知内容时出错: {e}")
        return f"获取通知内容失败: {str(e)}"



@tool(description="获取用户歌单")
def user_playlist():
    try:
        user_playlist_response = api.user_playlist(uid=user_id )
        if user_playlist_response.status == 200:
            print("已获取用户歌单")

            # 简化返回给模型的数据，只保留核心字段，减少 token 消耗和模型处理时间
            simplified_playlists = []
            for pl in user_playlist_response.body.get('playlist', []):
                simplified_playlists.append({
                    "id": pl.get("id"),
                    "name": pl.get("name"),
                    "trackCount": pl.get("trackCount"),
                    "playCount": pl.get("playCount"),
                    "description": pl.get("description")
                })
            
            return {
                "count": len(simplified_playlists),
                "playlists": simplified_playlists
            }
    except Exception as e:
        print(f"[失败] 获取用户歌单时出错: {e}")
        return {"错误": f"获取用户歌单时出错: {str(e)}"}




@tool(description="必选参数 id:歌单id,必选参数desc:新的歌单描述")
def playlist_desc_update(id, desc: str):
    print("使用playlist_desc_update工具=================")

    try:
        playlist_desc_update_response = api.playlist_desc_update(id=id, desc=desc, cookie=cookie)
        print(playlist_desc_update_response.status)
        if playlist_desc_update_response.status == 200:
            print("[成功] 已更新网易云歌单描述")
            return f"[成功] 歌单ID {id} 描述修改成功！新描述：{desc}"
        else:
            return f"[失败] 网易云接口更新失败：{playlist_desc_update_response.body}"

    except Exception as e:
        print(f"[失败] 更新歌单描述时出错: {e}")
        return f"[失败] 修改失败：{str(e)}"

@tool(description="更新用户歌单名称 必选参数 id:歌单id,必选参数name:歌单名称")
def playlist_name_update(id: str, name: str):
    """先获取歌单id,在进行歌单名称更新"""
    try:
        # 1. 调用网易云接口更新歌单名称
        playlist_name_update_response = api.playlist_name_update(id=id, name=name, cookie=cookie)

        if playlist_name_update_response.status == 200:
            print(f"[成功] 网易云歌单 {id} 名称已更新")
            return f"[成功] 歌单ID {id} 名称修改成功！新名称：{name}"
    except Exception as e:
        print(f"[失败] 更新歌单名称失败: {e}")
        return f"[失败] 修改失败：{str(e)}"



@tool(description="新建歌单。必选参数 name：歌单名。可选参数 privacy：只能填 no 或 yes，代表是否为隐私歌单。type：歌单类型，默认NORMAL")
def playlist_create(name, privacy="no", type="NORMAL"):
    """
    新建歌单
    :param name: 歌单名
    :param privacy: 是否隐私歌单，是/否
    :param type: 歌单类型
    """
    # 强制转换
    privacy_ = 10 if privacy == "no" else 0
    try:
        print("正在创建歌单...")
        playlist_create_response = api.playlist_create(name=name, privacy=privacy_, type=type )

        if playlist_create_response.status == 200:
            data = playlist_create_response.body
            return f'成功创建歌单{name}'
    except Exception as e:
        print(f"[失败] 新建歌单时出错: {e}")
        return f"[失败] 新建歌单失败：{str(e)}"

@tool(description="获取待删除歌单的全部id,再进行删除 必选参数 : id : 歌单 id,可多个,用逗号隔开 例如：5013464397,5013427772")
def playlist_delete(id):
    try:
        print(f"正在删除歌单，歌单id为{id}")
        playlist_delete_response = api.playlist_delete(id=id,cookie=cookie)

        if playlist_delete_response.status == 200:
            print(f"[成功] 网易云端已删除歌单 id: {id}")

    except Exception as e:
        print(f"[失败] 删除歌单时出错: {e}")
        return f"[失败] 删除歌单失败：{str(e)}"




@tool(description="更新用户歌单标签，必选参数：id（歌单id），tags（标签，只能使用网页端支持的标准标签）")
def playlist_tags_update(id, tags):
    """
    更新用户歌单标签
    必选参数：id（歌单id），tags（标签，只能使用网页端支持的标准标签）
    网页端支持的标签包括：
    华语、欧美、日语、韩语、粤语、
    流行、摇滚、民谣、电子、舞曲、说唱、轻音乐、爵士、乡村、R&B/Soul、古典、民族、英伦、金属、朋克、蓝调、雷鬼、世界音乐、拉丁、New Age、古风、后摇、Bossa Nova、
    清晨、夜晚、学习、工作、午休、下午茶、地铁、驾车、运动、旅行、散步、酒吧、
    怀旧、清新、浪漫、伤感、治愈、放松、孤独、感动、兴奋、快乐、安静、思念、
    综艺、影视原声、ACG、儿童、校园、游戏、70后、80后、90后、网络歌曲、KTV、经典、翻唱、吉他、钢琴、器乐、榜单、00后
    """
    # 定义网页端支持的标签列表
    supported_tags = [
        "华语", "欧美", "日语", "韩语", "粤语",
        "流行", "摇滚", "民谣", "电子", "舞曲", "说唱", "轻音乐", "爵士", "乡村", "R&B/Soul", "古典", "民族", "英伦", "金属", "朋克", "蓝调", "雷鬼", "世界音乐", "拉丁", "New Age", "古风", "后摇", "Bossa Nova",
        "清晨", "夜晚", "学习", "工作", "午休", "下午茶", "地铁", "驾车", "运动", "旅行", "散步", "酒吧",
        "怀旧", "清新", "浪漫", "伤感", "治愈", "放松", "孤独", "感动", "兴奋", "快乐", "安静", "思念",
        "综艺", "影视原声", "ACG", "儿童", "校园", "游戏", "70后", "80后", "90后", "网络歌曲", "KTV", "经典", "翻唱", "吉他", "钢琴", "器乐", "榜单", "00后"
    ]
    
    try:
        # 处理标签参数
        if isinstance(tags, list):
            # 如果是列表，取第一个元素
            tag = tags[0]
        else:
            tag = tags
        
        # 检查标签是否在支持的列表中
        if tag in supported_tags:
            # 标签在支持的列表中，直接使用
            final_tag = tag
        else:
            # 标签不在支持的列表中，尝试找到相近的标签
            # 简单的相近标签映射
            similar_tags = {
                "青春": "校园",
                "怀念": "怀旧",
                "忧郁": "孤独",
                "伤心": "伤感",
                "开心": "快乐",
                "安静": "安静",
                "放松": "放松"
            }
            
            if tag in similar_tags:
                # 找到相近的标签
                final_tag = similar_tags[tag]
                print(f"标签 '{tag}' 不在支持的列表中，使用相近标签 '{final_tag}'")
            else:
                # 没有找到相近的标签
                return f"标签 '{tag}' 不在支持的列表中，请选择其他标签。支持的标签包括：{', '.join(supported_tags)}"
        
        # 获取歌单详情，获取当前标签
        print("正在获取歌单详情...")
        playlist_detail_response = api.playlist_detail(id=id )
        if playlist_detail_response.status == 200:
            playlist = playlist_detail_response.body.get('playlist', {})
            current_tags = playlist.get('tags', [])
            
            # 检查新标签是否已经存在
            if final_tag not in current_tags:
                # 添加新标签到当前标签列表
                new_tags = current_tags + [final_tag]
                # 限制标签数量（网易云音乐最多支持10个标签）
                if len(new_tags) > 10:
                    new_tags = new_tags[-10:]
                
                # 将标签列表转换为逗号分隔的字符串
                tags_string = ','.join(new_tags)
                # 调用API更新标签
                playlist_tags_update_response = api.playlist_tags_update(id=id, tags=tags_string,cookie=cookie )
                if playlist_tags_update_response.status == 200:
                    print(f"已为用户歌单id为{id}添加标签 '{final_tag}'")
                    return f"已成功为歌单添加标签 '{final_tag}'，当前标签：{', '.join(new_tags)}"
            else:
                return f"歌单已经包含标签 '{final_tag}'"
        else:
            return "获取歌单详情失败"
    except Exception as e:
        print(f"[失败] 更新用户歌单标签时出错: {e}")
        return f"更新歌单标签失败: {str(e)}"


@tool(description="更新用户歌单顺序 必选参数 :ids: 歌单 id 列表，或者传入 playlist_name: 歌单名称, position: 目标位置(从1开始)")
def playlist_order_update(ids: list = None, playlist_name: str = None, position: int = 1):
    """
     更新用户歌单顺序
     有两种使用方式:
     1. 传入ids: 歌单id列表，直接按此顺序更新
     2. 传入playlist_name: 歌单名称, position: 目标位置(从1开始)，自动将该歌单移动到指定位置
    :return:
    """
    try:
        # 如果传入了playlist_name，则需要重新排列歌单顺序
        if playlist_name:
            # 获取用户所有歌单
            user_playlist_response = api.user_playlist(uid=user_id)
            if user_playlist_response.status != 200:
                return "[失败] 获取用户歌单失败"
            
            playlists = user_playlist_response.body.get('playlist', [])
            if not playlists:
                return "[失败] 用户没有歌单"
            
            # 找到目标歌单
            target_playlist = None
            for playlist in playlists:
                if str(playlist.get('id')) == playlist_name or playlist.get('name') == playlist_name:
                    target_playlist = playlist
                    break
            
            if not target_playlist:
                return f"[失败] 未找到歌单: {playlist_name}"
            
            # 构建新的歌单顺序列表
            target_id = str(target_playlist.get('id'))
            other_ids = [str(p.get('id')) for p in playlists if str(p.get('id')) != target_id]
            
            # 将目标歌单插入到指定位置
            position = max(1, min(position, len(playlists)))  # 确保位置在有效范围内
            new_order = other_ids[:position-1] + [target_id] + other_ids[position-1:]
            ids = new_order
        
        if not ids:
            return "[失败] 请提供歌单id列表或歌单名称"
        
        print(f"正在更新歌单顺序: {ids}")
        playlist_order_update_response = api.playlist_order_update(ids=ids,cookie=cookie )
        if playlist_order_update_response.status == 200:
            print("[成功] 已更新用户歌单顺序")
            return "[成功] 歌单顺序更新成功"
        else:
            return f"[失败] 更新失败: {playlist_order_update_response.body.get('message', '未知错误')}"
    except Exception as e:
        print(f"[失败] 更新歌单顺序时出错: {e}")
        return f"[失败] 更新失败: {str(e)}"





@tool(description="调整指定歌单的歌曲顺序，根据歌曲id顺序调整歌曲顺序，必选参数: pid: 歌单id, ids: 歌曲 id 列表")
def song_order_update(pid,ids: list):
    """
    调整歌曲顺序
    必选参数: pid: 歌单 id, ids: 歌曲 id 列表
    """
    try:
        print("正在调整歌曲顺序...")
        song_order_update_response = api.song_order_update(pid=pid, ids=ids ,cookie=cookie)
        if song_order_update_response.status == 200:
            print("已调整歌曲顺序")
            return song_order_update_response.body
    except Exception as e:
        print(f"[失败] 调整歌曲顺序时出错: {e}")
        return {"错误": f"调整歌曲顺序时出错: {str(e)}"}

@tool(description="添加歌曲到歌单，必选参数: pid: 歌单id或歌单名称, track_ids: 歌曲id列表")
def add_song_to_playlist(pid, track_ids: list):
    """
    添加歌曲到歌单
    必选参数: pid: 歌单id或歌单名称, track_ids: 歌曲id列表
    """
    try:
        # 首先尝试将pid作为歌单ID获取歌单信息
        playlist_response = api.playlist_detail(id=pid,cookie=cookie )
        if playlist_response.status != 200:
            # 如果获取失败，说明pid可能是歌单名称，尝试查找对应的歌单ID
            playlist_response = api.user_playlist(uid='4911105905' )
            if playlist_response.status == 200:
                playlists = playlist_response.body.get('playlist', [])
                for playlist in playlists:
                    if playlist.get('name') == pid:
                        pid = str(playlist.get('id'))
                        break
        
        print(f"正在添加歌曲到歌单 {pid}...")
        # 将歌曲ID列表转换为逗号分隔的字符串
        tracks_str = ','.join(track_ids)
        # 调用网易云接口添加歌曲
        response = api.playlist_tracks(op="add", pid=pid, tracks=tracks_str )
        if response.status == 200:
            print("[成功] 歌曲添加成功")
            return f"[成功] 歌曲已成功添加到歌单 {pid}"
        else:
            return f"[失败] 添加失败：{response.body.get('message', '未知错误')}"
    except Exception as e:
        print(f"[失败] 添加歌曲时出错: {e}")
        return f"[失败] 添加失败：{str(e)}"

@tool(description="从歌单删除歌曲，必选参数: pid: 歌单id或歌单名称, track_ids: 歌曲id列表")
def remove_song_from_playlist(pid, track_ids: list):
    """
    从歌单删除歌曲
    必选参数: pid: 歌单id或歌单名称, track_ids: 歌曲id列表
    """
    try:
        # 首先尝试将pid作为歌单ID获取歌单信息
        playlist_response = api.playlist_detail(id=pid )
        if playlist_response.status != 200:
            # 如果获取失败，说明pid可能是歌单名称，尝试查找对应的歌单ID
            playlist_response = api.user_playlist(uid=user_id)
            if playlist_response.status == 200:
                playlists = playlist_response.body.get('playlist', [])
                for playlist in playlists:
                    if playlist.get('name') == pid:
                        pid = str(playlist.get('id'))
                        break
        
        # 获取歌单详情，检查歌曲是否在歌单中
        playlist_response = api.playlist_detail(id=pid )
        if playlist_response.status == 200:
            playlist_data = playlist_response.body.get("playlist", {})
            track_ids_in_playlist = [str(track.get('id')) for track in playlist_data.get('tracks', [])]
            
            # 检查所有要删除的歌曲是否在歌单中
            songs_not_in_playlist = [track_id for track_id in track_ids if track_id not in track_ids_in_playlist]
            if songs_not_in_playlist:
                return f"[失败] 歌单中没有以下歌曲: {', '.join(songs_not_in_playlist)}"
        
        print(f"正在从歌单 {pid} 删除歌曲...")
        # 将歌曲ID列表转换为逗号分隔的字符串
        tracks_str = ','.join(track_ids)
        # 调用网易云接口删除歌曲
        response = api.playlist_tracks(op="del", pid=pid, tracks=tracks_str )
        if response.status == 200:
            print("[成功] 歌曲删除成功")
            return f"[成功] 歌曲已成功从歌单 {pid} 删除"
        else:
            return f"[失败] 删除失败：{response.body.get('message', '未知错误')}"
    except Exception as e:
        print(f"[失败] 删除歌曲时出错: {e}")
        return f"[失败] 删除失败：{str(e)}"

@tool(description="收藏/取消收藏歌曲，必选参数: id: 歌曲id, 可选参数: like: true 为收藏, false 为取消收藏，默认为true")
def song_like(id, like=True):
    """
    收藏/取消收藏歌曲
    必选参数: id: 歌曲id
    可选参数: like: true 为收藏, false 为取消收藏，默认为true
    """
    try:
        # 处理id参数，确保它是一个字符串形式的歌曲ID
        import json
        if isinstance(id, str):
            # 尝试解析JSON字符串
            try:
                id_obj = json.loads(id)
                if isinstance(id_obj, dict) and 'id' in id_obj:
                    id = str(id_obj['id'])
            except json.JSONDecodeError:
                # 如果不是JSON，直接使用
                pass
        
        # 处理字符串形式的like参数
        if isinstance(like, str):
            # 支持 'true', 'True', 'TRUE', 'false', 'False', 'FALSE'
            like_bool = like.lower() == 'true'
        else:
            like_bool = bool(like)
        
        # 确保传递给API的是字符串形式
        api_like_param = "true" if like_bool else "false"
        action = "收藏" if like_bool else "取消收藏"
        
        print(f"正在{action}歌曲 {id}...")
        print(f"传递给API的参数: like={api_like_param}")
        # 调用网易云接口收藏/取消收藏歌曲
        response = api.like(id=id, like=api_like_param )
        if response.status == 200:
            print(f"[成功] 已{action}歌曲")
            return "歌曲已成功" + action
        else:
            return action + "失败：" + str(response.body.get('message', '未知错误'))
    except Exception as e:
        print(f"[失败] 操作歌曲时出错: {e}")
        return "操作失败：" + str(e)

#-----------------------------------------------------------
##---------------------------------------------------

@tool(description="获取用户历史评论，可选参数: limit: 返回数量, time: 上一条数据的 time")
def user_comment_history(limit=None, time=None):
    """
    获取用户历史评论
    可选参数: limit: 返回数量, time: 上一条数据的 time
    """
    try:
        print("正在获取用户历史评论...")
        user_comment_history_response = api.user_comment_history(uid=user_id, limit=limit, time=time )
        if user_comment_history_response and user_comment_history_response.status == 200:
            print("已获取用户历史评论")
            
            # 优化返回结果，只保留关键信息
            body = user_comment_history_response.body
            if body:
                data = body.get('data', {})
                if not isinstance(data, dict):
                    data = {}
                if data:
                    comment_count = data.get('commentCount', 0)
                    has_more = data.get('hasMore', False)
                    comments = data.get('comments', [])
                    
                    simplified_comments = []
                    for comment in comments:
                        if comment:
                            # 提取歌曲信息
                            resource_info = comment.get('resourceInfo', '{}')
                            import json
                            try:
                                resource_data = json.loads(resource_info)
                            except json.JSONDecodeError:
                                resource_data = {}
                            
                            artist = resource_data.get('artist')
                            artist_name = artist.get('name', '') if artist else ''
                            
                            song_info = {
                                'id': resource_data.get('id'),
                                'name': resource_data.get('name'),
                                'artist': artist_name
                            }
                            
                            be_replied_user = comment.get('beRepliedUser')
                            be_replied_user_name = be_replied_user.get('nickname', '') if be_replied_user else ''
                            
                            simplified_comment = {
                                'commentId': comment.get('commentId'),
                                'content': comment.get('content'),
                                'time': comment.get('time'),
                                'likedCount': comment.get('likedCount'),
                                'song': song_info,
                                'beRepliedUser': be_replied_user_name
                            }
                            simplified_comments.append(simplified_comment)
                    
                    return {
                        'commentCount': comment_count,
                        'hasMore': has_more,
                        'comments': simplified_comments
                    }
                else:
                    return "数据部分为空"
            else:
                return "API 响应体为空"
        else:
            return f"获取用户历史评论失败: API 响应状态码 {user_comment_history_response.status if user_comment_history_response else 'None'}"
    except Exception as e:
        print(f"[失败] 获取用户历史评论时出错: {e}")
        return f"获取用户历史评论失败: {str(e)}"




@tool(description="获取用户电台")
def user_dj():
    """
    获取用户电台
    """
    try:
        print("正在获取用户电台...")
        user_dj_response = api.user_dj(uid=user_id )
        print(user_dj_response.body)
        if user_dj_response.status == 200:
            print("已获取用户电台")
            return user_dj_response.body
    except Exception as e:
        print(f"[失败] 获取用户电台时出错: {e}")

@tool(description="获取用户订阅的电台列表")
def dj_sublist():
    """
    获取用户订阅的电台列表
    """
    try:
        print("正在获取用户订阅的电台列表...")
        dj_sublist_response = api.dj_sublist()
        if dj_sublist_response and dj_sublist_response.status == 200:
            print("已获取用户订阅的电台列表")
            
            # 优化返回结果，只保留关键信息
            body = dj_sublist_response.body
            if body:
                count = body.get('count', 0)
                dj_radios = body.get('djRadios', [])
                
                simplified_radios = []
                for radio in dj_radios:
                    if radio:
                        simplified_radio = {
                            'id': radio.get('id'),
                            'name': radio.get('name'),
                            'desc': radio.get('desc'),
                            'picUrl': radio.get('picUrl'),
                            'programCount': radio.get('programCount'),
                            'subCount': radio.get('subCount'),
                            'category': radio.get('category'),
                            'dj': {
                                'id': radio.get('dj', {}).get('userId'),
                                'name': radio.get('dj', {}).get('nickname'),
                                'avatarUrl': radio.get('dj', {}).get('avatarUrl')
                            }
                        }
                        simplified_radios.append(simplified_radio)
                
                return {
                    'count': count,
                    'djRadios': simplified_radios
                }
            else:
                return "API 响应体为空"
        else:
            return f"获取用户订阅的电台列表失败: API 响应状态码 {dj_sublist_response.status if dj_sublist_response else 'None'}"
    except Exception as e:
        print(f"[失败] 获取用户订阅的电台列表时出错: {e}")
        return f"获取用户订阅的电台列表失败: {str(e)}"

@tool(description="获取用户关注列表 可选参数: limit: 返回数量, offset: 偏移数量")
def user_follows(limit=None, offset=None):
    """
    获取用户关注列表
    必选参数: uid: 用户 id
    可选参数: limit: 返回数量, offset: 偏移数量
    """
    try:
        print("正在获取用户关注列表...")
        user_follows_response = api.user_follows(uid=user_id, limit=limit, offset=offset )
        if user_follows_response and user_follows_response.status == 200:
            print("已获取用户关注列表")
            
            # 优化返回结果，只保留关键信息
            body = user_follows_response.body
            if body:
                follow = body.get('follow', [])
                # 检查 follow 是否为列表
                if isinstance(follow, list):
                    simplified_follows = []
                    for item in follow:
                        if item:
                            simplified_follow = {
                                'id': item.get('userId'),
                                'name': item.get('nickname'),
                                'avatarUrl': item.get('avatarUrl'),
                                'followTime': item.get('time')
                            }
                            simplified_follows.append(simplified_follow)
                    
                    return {
                        'count': len(simplified_follows),
                        'follows': simplified_follows
                    }
                else:
                    # 如果 follow 不是列表，可能是字典结构
                    count = follow.get('count', 0)
                    follows = follow.get('follows', [])
                    
                    simplified_follows = []
                    for item in follows:
                        if item:
                            simplified_follow = {
                                'id': item.get('userId'),
                                'name': item.get('nickname'),
                                'avatarUrl': item.get('avatarUrl'),
                                'followTime': item.get('time')
                            }
                            simplified_follows.append(simplified_follow)
                    
                    return {
                        'count': count,
                        'follows': simplified_follows
                    }
            else:
                return "API 响应体为空"

        else:
            return f"获取用户关注列表失败: API 响应状态码 {user_follows_response.status if user_follows_response else 'None'}"
    except Exception as e:
        print(f"[失败] 获取用户关注列表时出错: {e}")
        return f"获取用户关注列表失败: {str(e)}"



@tool(description="获取用户粉丝列表，必选参数: uid: 用户 id，可选参数: limit: 返回数量, offset: 偏移数量")
def user_followeds(limit=None, offset=None):
    """
    获取用户粉丝列表
    必选参数: uid: 用户 id
    可选参数: limit: 返回数量, offset: 偏移数量
    """
    try:
        print("正在获取用户粉丝列表...")
        user_followeds_response = api.user_followeds(uid=user_id, limit=limit, offset=offset )
        if user_followeds_response and user_followeds_response.status == 200:
            print("已获取用户粉丝列表")
            
            # 优化返回结果，只保留关键信息
            body = user_followeds_response.body
            if body:
                # 检查粉丝信息的位置
                if 'followeds' in body:
                    followeds = body.get('followeds', [])
                    count = len(followeds)
                elif 'follow' in body:
                    follow = body.get('follow', {})
                    count = follow.get('count', 0)
                    followeds = follow.get('followeds', [])
                else:
                    followeds = []
                    count = 0
                
                simplified_followeds = []
                for followed in followeds:
                    if followed:
                        simplified_followed = {
                            'id': followed.get('userId'),
                            'name': followed.get('nickname'),
                            'gender': followed.get('gender'),
                            'followTime': followed.get('time')
                        }
                        simplified_followeds.append(simplified_followed)
                
                return {
                    'count': count,
                    'followeds': simplified_followeds
                }
            else:
                return "API 响应体为空"
        else:
            return f"获取用户粉丝列表失败: API 响应状态码 {user_followeds_response.status if user_followeds_response else 'None'}"
    except Exception as e:
        print(f"[失败] 获取用户粉丝列表时出错: {e}")
        return f"获取用户粉丝列表失败: {str(e)}"


@tool(description="获取用户动态，必选参数: uid: 用户 id，可选参数: limit: 返回数量, lasttime: 返回数据的 lasttime")
def user_event(uid=user_id, limit=10, lasttime=None):
    """
    获取用户动态
    必选参数: uid: 用户 id
    可选参数: limit: 返回数量, lasttime: 返回数据的 lasttime
    """
    try:
        print("正在获取用户动态...")
        user_event_response = api.user_event(uid=uid, limit=limit, lasttime=lasttime )
        if user_event_response and user_event_response.status == 200:
            print("已获取用户动态")
            
            # 优化返回结果，只保留关键信息
            body = user_event_response.body
            if body:
                lasttime = body.get('lasttime', 0)
                events = body.get('events', [])
                
                simplified_events = []
                for event in events:
                    if event:
                        # 从 info.commentThread.resourceInfo 获取动态内容
                        dynamic_content = ''
                        info = event.get('info')
                        if info:
                            comment_thread = info.get('commentThread')
                            if comment_thread:
                                resource_info = comment_thread.get('resourceInfo')
                                if resource_info:
                                    dynamic_content = resource_info.get('name', '')
                        
                        # 从 json 字段中获取动态内容（如果上面没有）
                        if not dynamic_content:
                            event_json = event.get('json', '{}')
                            import json
                            try:
                                json_data = json.loads(event_json)
                                dynamic_content = json_data.get('msg', '')
                            except:
                                pass
                        
                        # 获取点赞数和评论数
                        liked_count = 0
                        comment_count = 0
                        info = event.get('info')
                        if info:
                            liked_count = info.get('likedCount', 0)
                            comment_count = info.get('commentCount', 0)
                        
                        simplified_event = {
                            'eventId': event.get('id'),
                            'content': dynamic_content,
                            'likedCount': liked_count,
                            'commentCount': comment_count
                        }
                        simplified_events.append(simplified_event)
                
                return {
                    'lasttime': lasttime,
                    'events': simplified_events
                }
            else:
                return "API 响应体为空"
    except Exception as e:
        print(f"[失败] 获取用户动态时出错: {e}")
        return f"获取用户动态失败: {str(e)}"




@tool(description="转发用户动态，必选参数: uid: 用户 id, evId: 动态 id, forwards: 转发的评论")
def event_forward(uid, evId, forwards):
    """
    转发用户动态
    必选参数: uid: 用户 id, evId: 动态 id, forwards: 转发的评论
    """
    try:
        print("正在转发用户动态...")
        event_forward_response = api.event_forward(uid=uid, evId=evId, forwards=forwards )
        if event_forward_response.status == 200:
            print("已转发用户动态")
            return "转发成功"
    except Exception as e:
        print(f"[失败] 转发用户动态时出错: {e}")

@tool(description="删除用户动态，必选参数: evId: 动态 id")
def event_del(evId):
    """
    删除用户动态
    必选参数: evId: 动态 id
    """
    try:
        print("正在删除用户动态...")
        event_del_response = api.event_del(evId=evId )
        if event_del_response.status == 200:
            print("已删除用户动态")
            return "已删除该动态"
    except Exception as e:
        print(f"[失败] 删除用户动态时出错: {e}")

@tool(description="分享文本、歌曲、歌单、mv、电台、电台节目到动态，必选参数: id: 资源 id，可选参数: type: 资源类型, msg: 内容")
def share_resource(id, type=None, msg=None):
    """
    分享文本、歌曲、歌单、mv、电台、电台节目到动态
    必选参数: id: 资源 id
    可选参数: type: 资源类型, msg: 内容
    """
    try:
        print("正在分享资源到动态...")
        share_resource_response = api.share_resource(id=id, type=type, msg=msg )
        if share_resource_response.status == 200:
            print("已分享资源到动态")
            return "已分享资源到动态"
    except Exception as e:
        print(f"[失败] 分享资源到动态时出错: {e}")



@tool(description="获取动态评论，必选参数: threadId: 动态 id")
def comment_event(threadId):
    """
    获取动态评论
    必选参数: threadId: 动态 id
    """
    try:
        print("正在获取动态评论...")
        comment_event_response = api.comment_event(threadId=threadId )
        if comment_event_response.status == 200:
            print("已获取动态评论")
            return comment_event_response.body
    except Exception as e:
        print(f"[失败] 获取动态评论时出错: {e}")




@tool(description="关注/取消关注用户， ids: 需要进行操作的用户的id列表, t: 关注为1或取消关注为其它")
def follow(ids:list, t: int):
    """
    先把要进行操作的用户的id全部放进ids里面，然后再进行操作
    关注/取消关注用户
    必选参数: ids: 需要进行操作的用户的id列表，不是姓名或歌曲名
    可选参数: t: 关注为1或取消关注为其它
    """
    print(ids, t)
    op="关注" if t==1 else "取消关注"
    try:
        results = []
        for id in ids:
            print(f"正在{op}用户 {id}...")
            follow_response = api.follow(id=id, t=t )
            if follow_response and follow_response.status == 200:
                print(f"已{op}用户")
                # 提取用户信息和状态
                body = follow_response.body
                user_info = body.get('user', {})
                user_name = user_info.get('nickname', f"用户 {id}")
                followed = user_info.get('followed', False)
                
                # 确定操作状态
                if t == 1:
                    if followed:
                        status = "关注成功"
                    else:
                        status = "已经关注"
                else:
                    if not followed:
                        status = "取消关注成功"
                    else:
                        status = "未关注"
                
                results.append({
                    'userId': id,
                    'userName': user_name,
                    'success': True,
                    'operation': op,
                    'status': status,
                    'followed': followed
                })
            else:
                results.append({
                    'userId': id,
                    'userName': f"用户 {id}",
                    'success': False,
                    'operation': op,
                    'status': "操作失败",
                    'message': f"操作失败: {follow_response.status if follow_response else '未知错误'}"
                })
        
        # 汇总结果
        all_success = all(result['success'] for result in results)
        return {
            'success': all_success,
            'operation': op,
            'results': results
        }
    except Exception as e:
        print(f"[失败] {op}用户时出错: {e}")
        return {
            'success': False,
            'operation': op,
            'message': f"操作失败: {str(e)}"
        }


@tool(description="获取用户播放记录，必选参数: uid: 用户 id，可选参数: type: type=1 时只返回 weekData, type=0 时返回 allData")
def user_record( type=1):
    """
    获取用户播放记录
    可选参数: type: type=1 时只返回 weekData, type=0 时返回 allData
    """
    try:
        print("正在获取用户播放记录...")
        user_record_response = api.user_record(uid=user_id, type=type )
        if user_record_response and user_record_response.status == 200:
            print("已获取用户播放记录")
            
            # 优化返回结果，只保留关键信息
            body = user_record_response.body
            if body:
                simplified_data = {}
                
                # 处理 allData
                if 'allData' in body:
                    all_data = body.get('allData', [])
                    simplified_all_data = []
                    for item in all_data:
                        if item and 'song' in item:
                            song = item.get('song', {})
                            song_id = song.get('id')
                            song_name = song.get('name', '')
                            
                            # 提取歌手信息
                            artists = song.get('ar', [])
                            artist_names = [artist.get('name', '') for artist in artists if artist]
                            artists_str = ' / '.join(artist_names)
                            
                            simplified_all_data.append({
                                'id': song_id,
                                'name': song_name,
                                'artists': artists_str
                            })
                    simplified_data['allData'] = simplified_all_data
                
                # 处理 weekData
                if 'weekData' in body:
                    week_data = body.get('weekData', [])
                    simplified_week_data = []
                    for item in week_data:
                        if item and 'song' in item:
                            song = item.get('song', {})
                            song_id = song.get('id')
                            song_name = song.get('name', '')
                            
                            # 提取歌手信息
                            artists = song.get('ar', [])
                            artist_names = [artist.get('name', '') for artist in artists if artist]
                            artists_str = ' / '.join(artist_names)
                            
                            simplified_week_data.append({
                                'id': song_id,
                                'name': song_name,
                                'artists': artists_str
                            })
                    simplified_data['weekData'] = simplified_week_data
                
                return simplified_data
            else:
                return "API 响应体为空"
    except Exception as e:
        print(f"[失败] 获取用户播放记录时出错: {e}")
        return f"获取用户播放记录失败: {str(e)}"

@tool(description="获取热门话题，可选参数: limit: 取出评论数量, offset: 偏移数量")
def hot_topic(limit=20, offset=0):
    """
    获取热门话题
    可选参数: limit: 取出评论数量, offset: 偏移数量
    """
    try:
        print("正在获取热门话题...")
        hot_topic_response = api.hot_topic(limit=limit, offset=offset )
        if hot_topic_response and hot_topic_response.status == 200:
            print("已获取热门话题")
            
            # 优化返回结果，只保留关键信息
            body = hot_topic_response.body
            if body:
                hot_topics = body.get('hot', [])
                simplified_topics = []
                for topic in hot_topics:
                    if topic:
                        simplified_topic = {
                            'id': topic.get('actId'),
                            'title': topic.get('title', ''),
                            'txt': topic.get('text', [])
                        }
                        simplified_topics.append(simplified_topic)
                return simplified_topics
            else:
                return "API 响应体为空"
    except Exception as e:
        print(f"[失败] 获取热门话题时出错: {e}")
        return f"获取热门话题失败: {str(e)}"
@tool(description="获取话题详情，可选参数: 可选参数: actids: 话题id的list")
def topic_detail(actids):
    """
    获取话题详情
    可选参数: actid: 话题id
    """
    try:
        print("正在获取话题详情...")
        results = []
        for actid in actids:
            topic_detail_response = api.topic_detail(actid=actid )
            if topic_detail_response and topic_detail_response.status == 200:
                print("已获取话题详情")
                
                # 优化返回结果，只保留关键信息
                body = topic_detail_response.body
                if body:
                    act = body.get('act', {})
                    if act:
                        simplified_act = {
                            'actId': act.get('actId'),
                            'title': act.get('title', ''),
                            'text': act.get('text', []),
                            'participateCount': act.get('participateCount', 0),
                            'startTime': act.get('startTime'),
                            'endTime': act.get('endTime')
                        }
                        results.append({
                            'act': simplified_act,
                            'needBeginNotify': body.get('needBeginNotify', False),
                            'code': body.get('code', 0)
                        })
        return results if results else "未获取到话题详情"
    except Exception as e:
        print(f"[失败] 获取话题详情时出错: {e}")
        return f"获取话题详情失败: {str(e)}"

@tool(description="获取话题详情热门动态，可选参数: actids: 话题id的list")
def topic_detail_event_hot(actids: list):
    """
    获取话题详情热门动态
    可选参数: actids: 话题id的集合
    """
    try:
        print("正在获取话题详情热门动态...")
        results = []
        for actid in actids:
            topic_detail_event_hot_response = api.topic_detail_event_hot(actid=actid )
            if topic_detail_event_hot_response and topic_detail_event_hot_response.status == 200:
                print("已获取话题详情热门动态")
                
                # 优化返回结果，只保留关键信息
                body = topic_detail_event_hot_response.body
                if body:
                    events = body.get('events', [])
                    simplified_events = []
                    for event in events:
                        if event:
                            # 提取核心信息
                            discuss_id = event.get('discussId')
                            act_name = event.get('actName', '')
                            
                            # 提取内容
                            content = ''
                            event_json = event.get('json', '{}')
                            import json
                            try:
                                json_data = json.loads(event_json)
                                content = json_data.get('msg', '')
                            except:
                                pass
                            
                            # 提取统计信息
                            info = event.get('info', {})
                            liked_count = info.get('likedCount', 0)
                            comment_count = info.get('commentCount', 0)
                            share_count = info.get('shareCount', 0)
                            
                            simplified_event = {
                                'id': discuss_id,
                                'actName': act_name,
                                'content': content,
                                'likedCount': liked_count,
                                'commentCount': comment_count,
                                'shareCount': share_count
                            }
                            simplified_events.append(simplified_event)
                    
                    results.append({
                        'events': simplified_events,
                        'code': body.get('code', 0)
                    })
        return results if results else "未获取到话题详情热门动态"
    except Exception as e:
        print(f"[失败] 获取话题详情热门动态时出错: {e}")
        return f"获取话题详情热门动态失败: {str(e)}"




@tool(description="心动模式/智能播放，必选参数:  pid: 歌单 id，song_id:歌曲id 可选参数: sid: 要开始播放的歌曲的 id")
def playmode_intelligence_list(pid, song_id, sid=None):
    """
    心动模式/智能播放
    必选参数:  pid: 歌单 id,song_id: 歌曲 id,
    可选参数: sid: 要开始播放的歌曲的 id
    """
    try:
        print("正在获取心动模式/智能播放列表...")
        print(pid,song_id)
        playmode_intelligence_list_response = api.playmode_intelligence_list(id=song_id, pid=pid, sid=sid )
        if playmode_intelligence_list_response.status == 200:
            print("已获取心动模式/智能播放列表")
            print(playmode_intelligence_list_response.body)
            return playmode_intelligence_list_response.body
    except Exception as e:
        print(f"[失败] 获取心动模式/智能播放列表时出错: {e}")






@tool(description="收藏/取消收藏歌手，可以先搜索歌手id 必选参数: id: 歌手 id, t: 1 为收藏,其他为取消收藏")
def artist_sub(id, t):
    """
    收藏/取消收藏歌手
    必选参数: id: 歌手 id, t: 1 为收藏,其他为取消收藏
    """
    action = "收藏" if t == "1" else "取消收藏"
    try:
        print(f"正在{action}歌手 {id}...")
        print(id,t)
        artist_sub_response = api.artist_sub(id=id, t=t )
        if artist_sub_response.status == 200:
            print(f"已{action}歌手")
            
            if t == "1":
                print("[成功] 歌手收藏成功")
            
            return artist_sub_response.body
    except Exception as e:
        print(f"[失败] {action}歌手时出错: {e}")


@tool(description="歌手热门的歌曲，必选参数: id: 歌手 id")
def artist_top_song(id):
    """
    歌手热门的歌曲，
    必选参数: id: 歌手 id

    """
    try:
        print(f"正在获取歌手 {id} 的热门歌曲...")
        artist_songs_response = api.artist_top_song(id=id )
        if artist_songs_response and artist_songs_response.status == 200:
            print("已获取歌手热门歌曲")
            # 优化返回结果，只保留关键信息
            body = artist_songs_response.body
            simplified_result = {
                'songs': [],
                'total': body.get('total', 0)
            }

            # 处理歌曲列表，只取前10首
            songs = body.get('songs', [])[:10]
            for song in songs:
                # 提取歌手信息
                artists = song.get('ar', [])
                artist_names = [a.get('name', '') for a in artists if a]
                artists_str = ' / '.join(artist_names)

                simplified_song = {
                    'id': song.get('id'),
                    'name': song.get('name'),
                    'artists': artists_str
                }
                simplified_result['songs'].append(simplified_song)

            return simplified_result
        else:
            return "获取歌手热门歌曲失败"
    except Exception as e:
        print(f"[失败] 获取歌手热门歌曲时出错: {e}")
        return f"获取歌手歌曲失败: {str(e)}"



@tool(description="歌手全部歌曲，必选参数: id: 歌手 id，可选参数: order: 排序方式, limit: 取出歌单数量, offset: 偏移数量")
def artist_songs(id, order=None, limit=None, offset=None):
    """
    歌手全部歌曲
    必选参数: id: 歌手 id 先获取歌手的id
    可选参数: order: 排序方式, limit: 取出歌单数量, offset: 偏移数量
    """
    try:
        print(f"正在获取歌手 {id} 的全部歌曲...")
        artist_songs_response = api.artist_songs(id=id, order=order, limit=limit, offset=offset )
        if artist_songs_response and artist_songs_response.status == 200:
            print("已获取歌手全部歌曲")
            # 优化返回结果，只保留关键信息
            body = artist_songs_response.body
            simplified_result = {
                'songs': [],
                'total': body.get('total', 0)
            }
            
            # 处理歌曲列表，只取前20首
            songs = body.get('songs', [])[:20]
            for song in songs:
                # 提取歌手信息
                artists = song.get('ar', [])
                artist_names = [a.get('name', '') for a in artists if a]
                artists_str = ' / '.join(artist_names)
                
                simplified_song = {
                    'id': song.get('id'),
                    'name': song.get('name'),
                    'artists': artists_str
                }
                simplified_result['songs'].append(simplified_song)
            
            return simplified_result
        else:
            return "获取歌手歌曲失败"
    except Exception as e:
        print(f"[失败] 获取歌手全部歌曲时出错: {e}")
        return f"获取歌手歌曲失败: {str(e)}"

@tool(description="收藏的歌手列表，可选参数: limit: 取出歌单数量, offset: 偏移数量")
def artist_sublist(limit=None, offset=None):
    """
    收藏的歌手列表
    可选参数: limit: 取出歌单数量, offset: 偏移数量
    """
    try:
        print("正在获取收藏的歌手列表...")
        artist_sublist_response = api.artist_sublist(limit=limit, offset=offset )
        if artist_sublist_response and artist_sublist_response.status == 200:
            print("已获取收藏的歌手列表")
            
            # 优化返回结果，只保留歌手id和名字
            body = artist_sublist_response.body
            if body:
                data = body.get('data', [])
                simplified_artists = []
                for artist in data:
                    if artist:
                        simplified_artist = {
                            'id': artist.get('id'),
                            'name': artist.get('name', '')
                        }
                        simplified_artists.append(simplified_artist)
                
                return {
                    'artists': simplified_artists,
                    'hasMore': body.get('hasMore', False),
                    'count': body.get('count', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取收藏的歌手列表失败"
    except Exception as e:
        print(f"[失败] 获取收藏的歌手列表时出错: {e}")
        return f"获取收藏的歌手列表失败: {str(e)}"






@tool(description="歌单分类")
def playlist_catlist():
    """
    歌单分类
    """
    try:
        print("正在获取歌单分类...")
        playlist_catlist_response = api.playlist_catlist()
        if playlist_catlist_response and playlist_catlist_response.status == 200:
            print("已获取歌单分类")
            
            # 优化返回结果，只保留name
            body = playlist_catlist_response.body
            if body:
                # 提取全部歌单名称
                all_name = body.get('all', {}).get('name', '')
                
                # 提取子分类名称
                sub_categories = body.get('sub', [])
                sub_names = [sub.get('name', '') for sub in sub_categories if sub]
                
                return {
                    'all': all_name,
                    'categories': sub_names,
                    'code': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取歌单分类失败"
    except Exception as e:
        print(f"[失败] 获取歌单分类时出错: {e}")
        return f"获取歌单分类失败: {str(e)}"

@tool(description="热门歌单分类")
def playlist_hot():
    """
    热门歌单分类
    """
    try:
        print("正在获取热门歌单分类...")
        playlist_hot_response = api.playlist_hot()
        if playlist_hot_response and playlist_hot_response.status == 200:
            print("已获取热门歌单分类")
            
            # 优化返回结果，只保留id和名字
            body = playlist_hot_response.body
            if body:
                tags = body.get('tags', [])
                simplified_tags = []
                for tag in tags:
                    if tag:
                        simplified_tag = {
                            'id': tag.get('id'),
                            'name': tag.get('name', '')
                        }
                        simplified_tags.append(simplified_tag)
                
                return {
                    'tags': simplified_tags,
                    'code': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取热门歌单分类失败"
    except Exception as e:
        print(f"[失败] 获取热门歌单分类时出错: {e}")
        return f"获取热门歌单分类失败: {str(e)}"

@tool(description="歌单 (网友精选碟)，可选参数: order: 排序方式, cat: 标签, limit: 返回数量, offset: 偏移数量")
def top_playlist(order=None, cat=None, limit=20, offset=None):
    """
    歌单 (网友精选碟)
    可选参数: order: 排序方式, cat: 标签, limit: 返回数量, offset: 偏移数量
    """
    try:
        print("正在获取网友精选碟歌单...")
        top_playlist_response = api.top_playlist(order=order, cat=cat, limit=limit, offset=offset )
        if top_playlist_response and top_playlist_response.status == 200:
            print("已获取网友精选碟歌单")
            
            # 优化返回结果，只保留id、name、tag、description
            body = top_playlist_response.body
            if body:
                playlists = body.get('playlists', [])
                simplified_playlists = []
                for playlist in playlists:
                    if playlist:
                        simplified_playlist = {
                            '歌单id': playlist.get('id'),
                            '歌单名字': playlist.get('name', ''),
                            '标签': playlist.get('tags', []),
                            '描述': playlist.get('description', ''),
                            '封面url': _extract_playlist_cover_url(playlist),
                            '歌曲数量': playlist.get('trackCount', 0),
                            '播放量': playlist.get('playCount', 0),
                        }
                        simplified_playlists.append(simplified_playlist)
                
                return {
                    'playlists': simplified_playlists,
                    'total': body.get('total', 0),
                    'code': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取网友精选碟歌单失败"
    except Exception as e:
        print(f"[失败] 获取网友精选碟歌单时出错: {e}")
        return f"获取网友精选碟歌单失败: {str(e)}"

@tool(description="精品歌单标签列表")
def playlist_highquality_tags():
    """
    精品歌单标签列表
    """
    try:
        print("正在获取精品歌单标签列表...")
        playlist_highquality_tags_response = api.playlist_highquality_tags()
        if playlist_highquality_tags_response.status == 200:
            print("已获取精品歌单标签列表")
            return playlist_highquality_tags_response.body
    except Exception as e:
        print(f"[失败] 获取精品歌单标签列表时出错: {e}")


@tool(description="获取精品歌单，可选参数: cat: 标签, limit: 返回数量, before: 分页参数")
def top_playlist_highquality(cat=None, limit=None, before=None):
    """
    获取精品歌单
    可选参数: cat: 标签, limit: 返回数量, before: 分页参数
    """
    try:
        print("正在获取精品歌单...")
        top_playlist_highquality_response = api.top_playlist_highquality(cat=cat, limit=limit, before=before )
        if top_playlist_highquality_response and top_playlist_highquality_response.status == 200:
            print("已获取精品歌单")
            
            # 优化返回结果，只保留id、name、tags
            body = top_playlist_highquality_response.body
            if body:
                playlists = body.get('playlists', [])
                simplified_playlists = []
                for playlist in playlists:
                    if playlist:
                        simplified_playlist = {
                            '歌单id': playlist.get('id'),
                            '歌单名字': playlist.get('name', ''),
                            '标签': playlist.get('tags', []),
                            '描述': playlist.get('description', ''),
                            '封面url': _extract_playlist_cover_url(playlist),
                            '歌曲数量': playlist.get('trackCount', 0),
                            '播放量': playlist.get('playCount', 0),
                        }
                        simplified_playlists.append(simplified_playlist)
                
                return {
                    'playlists': simplified_playlists,
                    'total': body.get('total', 0),
                    'code': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取精品歌单失败"
    except Exception as e:
        print(f"[失败] 获取精品歌单时出错: {e}")
        return f"获取精品歌单失败: {str(e)}"

@tool(description="相关歌单推荐，必选参数: id: 歌单 id")
def related_playlist(id):
    """
    相关歌单推荐
    必选参数: id: 歌单 id
    """
    try:
        print(f"正在获取歌单 {id} 的相关歌单...")
        related_playlist_response = api.related_playlist(id=id )
        if related_playlist_response and related_playlist_response.status == 200:
            print("已获取相关歌单")
            
            # 优化返回结果，只保留歌单id、name和创建者id、name
            body = related_playlist_response.body
            if body:
                playlists = body.get('playlists', [])
                simplified_playlists = []
                for playlist in playlists:
                    if playlist:
                        creator = playlist.get('creator', {})
                        simplified_playlist = {
                            'id': playlist.get('id'),
                            'name': playlist.get('name', ''),
                            'creator': {
                                'userId': creator.get('userId'),
                                'nickname': creator.get('nickname', '')
                            }
                        }
                        simplified_playlists.append(simplified_playlist)
                
                return {
                    'playlists': simplified_playlists,
                    'code': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取相关歌单失败"
    except Exception as e:
        print(f"[失败] 获取相关歌单时出错: {e}")
        return f"获取相关歌单失败: {str(e)}"



@tool(description="获取歌单所有歌曲，必选参数: id: 歌单 id，可选参数: limit: 返回数量, offset: 偏移数量")
def playlist_track_all(id, limit=None, offset=None):
    """
    获取歌单所有歌曲
    必选参数: id: 歌单 id
    可选参数: limit: 返回数量, offset: 偏移数量
    由于网易云接口限制，歌单详情只会提供 10 首歌，通过调用此接口，传入对应的歌单id，即可获得对应的所有歌曲
    """
    try:
        print(f"正在获取歌单 {id} 的所有歌曲...")
        playlist_track_all_response = api.playlist_track_all(id=id, limit=limit, offset=offset )
        if playlist_track_all_response.status == 200:
            print("已获取歌单所有歌曲")
            # 优化返回结果，只保留关键信息
            body = playlist_track_all_response.body
            simplified_result = {
                'tracks': [],
                'total': body.get('total', 0),
                'more': body.get('more', False)
            }
            
            # 处理歌曲列表
            tracks = body.get('songs', [])
            for track in tracks:
                simplified_track = {
                    'id': track.get('id'),
                    'name': track.get('name'),
                    'artists': [{'id': a.get('id'), 'name': a.get('name')} for a in track.get('ar', [])]
                }
                simplified_result['tracks'].append(simplified_track)
            
            return simplified_result
    except Exception as e:
        print(f"[失败] 获取我喜欢的歌曲时出错: {e}")
        return {"错误": f"获取我喜欢的歌曲时出错: {str(e)}"}

@tool(description="获取歌单动态，必选参数: id: 歌单 id")
def playlist_detail_dynamic(id):
    """
    获取歌单动态，必选参数: id: 歌单 id
    """
    try:
        print(f"正在获取歌单 {id} 的动态...")
        playlist_detail_dynamic_response = api.playlist_detail_dynamic(id=id )
        if playlist_detail_dynamic_response.status == 200:
            print("已获取歌单动态")
            # 优化返回结果，只保留关键信息
            body = playlist_detail_dynamic_response.body
            simplified_result = {
                'playlist': {
                    'id': body.get('playlist', {}).get('id'),
                    'name': body.get('playlist', {}).get('name'),
                    'coverImgUrl': body.get('playlist', {}).get('coverImgUrl'),
                    'trackCount': body.get('playlist', {}).get('trackCount'),
                    'playCount': body.get('playlist', {}).get('playCount'),
                    'description': body.get('playlist', {}).get('description'),
                    'creator': {
                        'id': body.get('playlist', {}).get('creator', {}).get('id'),
                        'name': body.get('playlist', {}).get('creator', {}).get('name')
                    }
                },
                'tracks': []
            }
            
            # 只保留前10首歌曲
            tracks = body.get('playlist', {}).get('tracks', [])
            for track in tracks[:10]:
                simplified_track = {
                    'id': track.get('id'),
                    'name': track.get('name'),
                    'artists': [{'id': a.get('id'), 'name': a.get('name')} for a in track.get('ar', [])],
                    'album': {'id': track.get('al', {}).get('id'), 'name': track.get('al', {}).get('name')}
                }
                simplified_result['tracks'].append(simplified_track)
            
            return simplified_result
    except Exception as e:
        print(f"[失败] 获取歌单动态时出错: {e}")


@tool(description="获取歌曲 URL，必选参数: id: 歌曲 id")
def song_url(id):
    """
    获取歌曲 URL
    必选参数: id: 歌曲 id
    取音乐 url
        说明 : 使用歌单详情接口后 , 能得到音乐 url,
        调用此接口, 传入的音乐 id( 可多个 , 用逗号隔开 ), 可以获取对应的音乐的 url,
        未登录状态或者非会员返回试听片段(返回字段包含被截取的正常歌曲的开始时间和结束时间)
    """
    try:
        print(f"正在获取歌曲 {id} 的 URL...")
        song_url_response = api.song_url(id=id )
        if song_url_response and song_url_response.status == 200:
            print("已获取歌曲 URL")
            
            # 优化返回结果，只保留id和url
            body = song_url_response.body
            if body:
                data = body.get('data', [])
                simplified_data = []
                for item in data:
                    if item:
                        simplified_item = {
                            'id': item.get('id'),
                            'url': item.get('url', '')
                        }
                        simplified_data.append(simplified_item)
                
                if simplified_data:
                    return {
                        'data': simplified_data,
                        'code': body.get('code', 0)
                    }
            else:
                return "API 响应体为空"
        else:
            return "获取歌曲 URL 失败"
    except Exception as e:
        print(f"[失败] 获取歌曲 URL时出错: {e}")
        return f"获取歌曲 URL 失败: {str(e)}"

@tool(description=f"获取音乐 url - 新版，必选参数: id: 音乐 id，level: 播放音质等级, 分为 standard => 标准,higher => 较高, exhigh=>极高,lossless=>无损, hires=>Hi-Res, jyeffect => 高清环绕声, sky => 沉浸环绕声, dolby => 杜比全景声, jymaster => 超清母带")
def song_url_v1( id, level="jymaster"):
    print(level)
    fallback_message = "暂时获取不到歌曲播放地址，请稍后再试"

    for attempt in range(2):
        session_api = None
        try:
            print(f"正在获取歌曲 {id} 的 URL...")
            with _NCM_API_LOCK:
                session_api, _ = _open_music_api_only(force_refresh_env=attempt > 0)
                if session_api is None:
                    continue
                song_url_v1_response = session_api.song_url_v1(id=id, level=level)

            if _should_retry_ncm_response(song_url_v1_response) and attempt == 0:
                continue

            response_status = _safe_response_status(song_url_v1_response)
            response_body = _safe_response_body(song_url_v1_response)
            if song_url_v1_response and response_status == 200:
                print("已获取歌曲 URL")

                body = response_body
                if body:
                    data = body.get('data', [])
                    if isinstance(data, dict):
                        data = [data]
                    simplified_data = []
                    for item in data:
                        if item:
                            simplified_item = {
                                'id': item.get('id'),
                                'level': item.get('level', ''),
                                'url': item.get('url', '')
                            }
                            simplified_data.append(simplified_item)

                    if simplified_data:
                        return {
                            'data': simplified_data,
                            'code': body.get('code', 0)
                        }
        except Exception as e:
            print(f"[失败] 获取歌曲 URL时出错: {e}")
            if attempt == 0 and _looks_like_internal_api_failure(e):
                continue
            return _friendly_tool_failure(fallback_message, e)
        finally:
            _destroy_music_api(session_api)

    return _friendly_tool_failure(fallback_message)







@tool(description="收藏/取消收藏歌单，必选参数: t: 类型,1:收藏,2:取消收藏, id: 歌单 id")
def playlist_subscribe(t, id):
    """
    收藏/取消收藏歌单
    必选参数: t: 类型,1:收藏,2:取消收藏, id: 歌单 id
    """

    try:

        playlist_subscribe_response = api.playlist_subscribe(t=t, id=id )
        if playlist_subscribe_response.status == 200:

            return "操作成功"
    except Exception as e:
        print(f"[失败]操作失败: {e}")

@tool(description="对歌单添加或删除歌曲，需要先获得歌单的id给pid，再获取歌曲id给tracks，必选参数: op: 增加单曲为 add, 删除为 del, pid: 歌单 id, tracks: 歌曲 id")
def playlist_tracks(op, pid, tracks):
    """
    对歌单添加或删除歌曲
    必选参数: op: 增加单曲为 add, 删除为 del, pid: 歌单 id, tracks: 歌曲 id
    """
    action = "添加" if op == "add" else "删除"
    try:
        print(f"正在{action}歌曲到歌单 {pid}...")
        playlist_tracks_response = api.playlist_tracks(op=op, pid=pid, tracks=tracks)
        if playlist_tracks_response and playlist_tracks_response.status == 200:
            # 注意：API 返回的 body 是一个包含 status, body, cookie 的字典
            response_body = playlist_tracks_response.body
            print(f"API 原始响应: {response_body}")
            
            # 提取实际的业务数据
            if isinstance(response_body, dict) and 'body' in response_body:
                body = response_body.get('body', {})
            else:
                body = response_body
            
            # 检查响应中的 code
            code = body.get('code', -1)
            if code == 200:
                # 提取关键信息
                result = {
                    'code': code,
                    'success': True,
                    'message': f"已{action}歌曲到歌单",
                    'coverImgUrl': body.get('coverImgUrl'),
                    'trackIds': body.get('trackIds'),
                    'count': body.get('count', 0),
                    'cloudCount': body.get('cloudCount', 0)
                }
                
                # 如果 count 为 0，可能添加失败
                if result['count'] == 0 and op == "add":
                    result['warning'] = "歌曲可能已存在于歌单中，或添加失败"
                
                print(f"[成功] {result['message']}")
                return result
            else:
                return {
                    'code': code,
                    'success': False,
                    'message': f"{action}歌曲失败，错误码: {code}"
                }
        else:
            return {
                'success': False,
                'message': f"{action}歌曲失败，HTTP状态码: {playlist_tracks_response.status if playlist_tracks_response else '无响应'}"
            }
    except Exception as e:
        print(f"[失败] {action}歌曲到歌单时出错: {e}")
        return {
            'success': False,
            'message': f"{action}歌曲时出错: {str(e)}"
        }


@tool(description="获取播放历史，可选参数: limit: 返回数量")
def get_play_history(limit=20):
    """
    获取播放历史
    可选参数: limit: 返回数量
    """
    try:
        print("正在获取播放历史...")
        # 从API获取播放历史
        user_record_response = api.user_record(uid=user_id, type=0 )
        if user_record_response.status == 200:
            data = user_record_response.body
            history = []
            
            # 处理所有播放记录
            if 'allData' in data:
                for item in data['allData'][:limit]:
                    song = item.get('song', {})
                    song_id = song.get('id')
                    song_name = song.get('name')
                    artists = song.get('artists', [])
                    artist_name = ', '.join([a.get('name') for a in artists])
                    
                    if song_id and song_name:
                        history.append({
                            "song_id": song_id,
                            "song_name": song_name,
                            "artist_name": artist_name,
                            "play_count": item.get('playCount', 0)
                        })
            
            if history:
                print(f"[成功] 已获取播放历史，共{len(history)}条")
                return history
            else:
                return "暂无播放历史"
        else:
            return "获取播放历史失败: API返回错误"
    except Exception as e:
        print(f"[失败] 获取播放历史时出错: {e}")
        return f"获取播放历史失败: {str(e)}"

@tool(description="获取评论历史，可选参数: limit: 返回数量")
def get_comment_history(limit=10):
    """
    获取评论历史
    可选参数: limit: 返回数量
    """
    try:
        print("正在获取评论历史...")
        # 从API获取评论历史
        response = api.user_comment_history(uid=user_id, limit=limit)
        if response and response.status == 200:

            data = response.body
            if data:
                # 检查响应结构
                if 'data' in data:
                    # 响应结构: {"code": 200, "data": {...}}
                    data = data.get('data', {})
                
                # 提取评论和相关信息
                comments = data.get('comments', [])
                total = data.get('commentCount', data.get('total', 0))
                hasMore = data.get('hasMore', False)
                
                if comments:
                    history = []
                    for comment in comments:
                        # 提取关键信息
                        resource_info_str = comment.get('resourceInfo', '{}')
                        import json
                        try:
                            resource_info = json.loads(resource_info_str)
                            song_name = resource_info.get('song', {}).get('name', '')
                        except:
                            song_name = ''
                        
                        simplified_comment = {
                            'content': comment.get('content', ''),
                            'time': comment.get('time'),
                            'likedCount': comment.get('likedCount', 0),
                            'songName': song_name
                        }
                        history.append(simplified_comment)
                    
                    print(f"[成功] 已获取评论历史，共{len(history)}条")
                    return {
                        'comments': history,
                        'total': total,
                        'hasMore': hasMore,
                        'code': 200
                    }
                else:
                    return {
                        'comments': [],
                        'total': total,
                        'hasMore': hasMore,
                        'code': 200
                    }
            else:
                return "API 响应体为空"
        else:
            return f"获取评论历史失败: {response.body.get('message', '未知错误') if response else '无响应'}"
    except Exception as e:
        print(f"[失败] 获取评论历史时出错: {e}")
        return f"获取评论历史失败: {str(e)}"

@tool(description="获取关注列表，可选参数: limit: 返回数量")
def get_follow_list(limit=10):
    """
    获取关注列表
    可选参数: limit: 返回数量
    """
    try:
        print("正在获取关注列表...")
        # 从API获取关注列表
        response = api.user_follows(uid=user_id, limit=limit, offset=0 )
        
        if response.status == 200:
            data = response.body
            follows = data.get('follow', [])
            
            # 处理关注列表
            follow_list = []
            for item in follows:
                follow_list.append({
                    "follow_id": item.get('userId'),
                    "follow_name": item.get('nickname'),
                })
            
            print(f"[成功] 已获取关注列表，共{len(follow_list)}条")
            return follow_list
        else:
            return "暂无关注记录"
    except Exception as e:
        print(f"[失败] 获取关注列表时出错: {e}")
        return f"获取关注列表失败: {str(e)}"


def _extract_follow_items_from_body(body: Any) -> list[dict[str, Any]]:
    if not isinstance(body, dict):
        return []

    follow = body.get("follow", [])
    if isinstance(follow, list):
        return [item for item in follow if isinstance(item, dict)]

    if isinstance(follow, dict):
        follows = follow.get("follows", [])
        if isinstance(follows, list):
            return [item for item in follows if isinstance(item, dict)]

    return []


def _extract_followed_items_from_body(body: Any) -> list[dict[str, Any]]:
    if not isinstance(body, dict):
        return []

    followeds = body.get("followeds", [])
    if isinstance(followeds, list):
        return [item for item in followeds if isinstance(item, dict)]

    follow = body.get("follow", {})
    if isinstance(follow, dict):
        nested_followeds = follow.get("followeds", [])
        if isinstance(nested_followeds, list):
            return [item for item in nested_followeds if isinstance(item, dict)]

    return []


def _pick_profile_value(*values: Any):
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return stripped
            continue
        return value
    return None


def _fetch_all_social_profiles(fetch_page, extractor, page_size: int = 100, max_pages: int = 100):
    collected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    offset = 0

    for _ in range(max_pages):
        response = fetch_page(page_size, offset)
        status = _safe_response_status(response)
        body = _safe_response_body(response)

        if status != 200:
            message = _response_error_text(response) or f"API 响应状态码 {status}"
            return False, message, []

        items = extractor(body)
        if not items:
            break

        added_count = 0
        for item in items:
            user_key = str(item.get("userId") or item.get("user_id") or item.get("id") or "").strip()
            if not user_key or user_key in seen_ids:
                continue
            seen_ids.add(user_key)
            collected.append(item)
            added_count += 1

        if len(items) < page_size or added_count == 0:
            break

        offset += len(items)

    return True, "", collected


@tool(description="获取当前账号的相互关注列表，可选参数: limit: 返回数量, offset: 偏移数量")
def get_mutual_follow_list(limit=20, offset=0):
    """
    获取当前账号的相互关注列表
    可选参数: limit: 返回数量, offset: 偏移数量
    """
    try:
        print("正在获取相互关注列表...")

        _, current_uid, _, _ = _ensure_global_music_session()
        if current_uid is None:
            return "获取相互关注列表失败: 当前用户未登录"

        try:
            resolved_limit = max(int(limit), 1) if limit is not None else None
            resolved_offset = max(int(offset), 0)
        except Exception:
            return "获取相互关注列表失败: limit 或 offset 参数格式不正确"

        follows_ok, follows_error, follows = _fetch_all_social_profiles(
            lambda page_size, page_offset: api.user_follows(uid=current_uid, limit=page_size, offset=page_offset),
            _extract_follow_items_from_body,
        )
        if not follows_ok:
            return f"获取相互关注列表失败: {follows_error}"

        followeds_ok, followeds_error, followeds = _fetch_all_social_profiles(
            lambda page_size, page_offset: api.user_followeds(uid=current_uid, limit=page_size, offset=page_offset),
            _extract_followed_items_from_body,
        )
        if not followeds_ok:
            return f"获取相互关注列表失败: {followeds_error}"

        follows_map = {
            str(item.get("userId") or item.get("user_id") or item.get("id")): item
            for item in follows
            if isinstance(item, dict) and (item.get("userId") or item.get("user_id") or item.get("id"))
        }
        followeds_map = {
            str(item.get("userId") or item.get("user_id") or item.get("id")): item
            for item in followeds
            if isinstance(item, dict) and (item.get("userId") or item.get("user_id") or item.get("id"))
        }

        mutual_users = []
        for uid, follow_item in follows_map.items():
            if uid not in followeds_map:
                continue

            followed_item = followeds_map[uid]
            follow_time = _pick_profile_value(follow_item.get("time"), follow_item.get("followTime"), 0) or 0
            followed_time = _pick_profile_value(followed_item.get("time"), followed_item.get("followTime"), 0) or 0

            mutual_users.append(
                {
                    "id": follow_item.get("userId") or followed_item.get("userId") or uid,
                    "name": _pick_profile_value(follow_item.get("nickname"), followed_item.get("nickname"), ""),
                    "avatarUrl": _pick_profile_value(follow_item.get("avatarUrl"), followed_item.get("avatarUrl"), ""),
                    "signature": _pick_profile_value(follow_item.get("signature"), followed_item.get("signature"), ""),
                    "gender": _pick_profile_value(follow_item.get("gender"), followed_item.get("gender")),
                    "remarkName": _pick_profile_value(follow_item.get("remarkName"), followed_item.get("remarkName"), ""),
                    "userType": _pick_profile_value(follow_item.get("userType"), followed_item.get("userType"), 0),
                    "authStatus": _pick_profile_value(follow_item.get("authStatus"), followed_item.get("authStatus"), 0),
                    "expertTags": _pick_profile_value(follow_item.get("expertTags"), followed_item.get("expertTags")),
                    "followTime": follow_time,
                    "followedTime": followed_time,
                    "mutual": True,
                }
            )

        mutual_users.sort(
            key=lambda item: max(int(item.get("followTime") or 0), int(item.get("followedTime") or 0)),
            reverse=True,
        )

        total = len(mutual_users)
        sliced_users = mutual_users[resolved_offset:]
        if resolved_limit is not None:
            sliced_users = sliced_users[:resolved_limit]

        print(f"[成功] 已获取相互关注列表，共 {total} 人")
        return {
            "count": total,
            "offset": resolved_offset,
            "limit": resolved_limit,
            "mutual_follows": sliced_users,
        }
    except Exception as e:
        print(f"[失败] 获取相互关注列表时出错: {e}")
        return f"获取相互关注列表失败: {str(e)}"



















@tool(description="新歌速递，必选参数: type: 地区类型id,对应以下:全部:0,华语:7,欧美:96,日本:8,韩国:16")
def top_song(type=7):
    try:
        print("正在获取新歌速递...")
        response = api.top_song(type=type, cookie=cookie)
        if response and response.status == 200:
            body = response.body

            if body:
                data = body.get('data', [])
                simplified_songs = []
                for song in data:
                    if song:
                        artists = song.get('artists', song.get('ar', []))
                        artists_str = _join_artist_names(artists)
                        simplified_song = {
                            '歌曲id': song.get('id'),
                            '歌曲名字': song.get('name', ''),
                            '歌手': artists_str,
                            '专辑名字': _extract_song_album_name(song),
                            '封面url': _extract_song_cover_url(song),
                            '时长': song.get('duration', 0),
                        }
                        simplified_songs.append(simplified_song)
                
                print("[成功] 新歌速递获取成功")
                return {
                    'songs': simplified_songs,
                    'code': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取新歌速递失败"
    except Exception as e:
        print(f"[失败] 获取新歌速递时出错: {e}")
        return f"获取新歌速递失败: {str(e)}"




# 评论相关接口
@tool(description="歌曲评论，必选参数: id: 音乐id，可选参数: limit: 取出评论数量,默认为20, offset: 偏移数量,用于分页, before: 分页参数,取上一页最后一项的time获取下一页数据")
def comment_music(id, limit=None, offset=None, before=None):
    try:
        print(f"正在获取歌曲 {id} 的评论...")
        response = api.comment_music(id=id, limit=limit, offset=offset, before=before, cookie=cookie)
        if response and response.status == 200:
            body = response.body
            if body:
                # 提取热门评论
                hot_comments = body.get('hotComments', [])
                # 提取普通评论
                comments = body.get('comments', [])
                
                # 简化热门评论
                simplified_hot_comments = []
                for comment in hot_comments:
                    if comment:
                        user = comment.get('user', {})
                        simplified_comment = {
                            '评论id': comment.get('commentId', ''),
                            '评论人': user.get('nickname', ''),
                            '评论内容': comment.get('content', '')
                        }
                        simplified_hot_comments.append(simplified_comment)
                
                # 简化普通评论
                simplified_comments = []
                for comment in comments:
                    if comment:
                        user = comment.get('user', {})
                        simplified_comment = {
                            '评论id': comment.get('commentId', ''),
                            '评论人': user.get('nickname', ''),
                            '评论内容': comment.get('content', '')
                        }
                        simplified_comments.append(simplified_comment)
                
                print("[成功] 歌曲评论获取成功")
                return {
                    '热门评论': simplified_hot_comments,
                    '评论': simplified_comments,
                    '总数': body.get('total', 0),
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取歌曲评论失败"
    except Exception as e:
        print(f"[失败] 获取歌曲评论时出错: {e}")
        return f"获取歌曲评论失败: {str(e)}"


@tool(description="专辑评论，必选参数: id: 专辑id，可选参数: limit: 取出评论数量,默认为20, offset: 偏移数量,用于分页, before: 分页参数,取上一页最后一项的time获取下一页数据")
def comment_album(id, limit=None, offset=None, before=None):
    try:
        print(f"正在获取专辑 {id} 的评论...")
        response = api.comment_album(id=id, limit=limit, offset=offset, before=before, cookie=cookie)
        if response and response.status == 200:
            body = response.body
            if body:
                # 提取热门评论
                hot_comments = body.get('hotComments', [])
                # 提取普通评论
                comments = body.get('comments', [])
                
                # 简化热门评论
                simplified_hot_comments = []
                for comment in hot_comments:
                    if comment:
                        user = comment.get('user', {})
                        simplified_comment = {
                            '评论id': comment.get('commentId', ''),
                            '评论人': user.get('nickname', ''),
                            '评论内容': comment.get('content', '')
                        }
                        simplified_hot_comments.append(simplified_comment)
                
                # 简化普通评论
                simplified_comments = []
                for comment in comments:
                    if comment:
                        user = comment.get('user', {})
                        simplified_comment = {
                            '评论id': comment.get('commentId', ''),
                            '评论人': user.get('nickname', ''),
                            '评论内容': comment.get('content', '')
                        }
                        simplified_comments.append(simplified_comment)
                
                print("[成功] 专辑评论获取成功")
                return {
                    '热门评论': simplified_hot_comments,
                    '评论': simplified_comments,
                    '总数': body.get('total', 0),
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取专辑评论失败"
    except Exception as e:
        print(f"[失败] 获取专辑评论时出错: {e}")
        return f"获取专辑评论失败: {str(e)}"

@tool(description="歌单评论，必选参数: id: 歌单id，可选参数: limit: 取出评论数量,默认为20, offset: 偏移数量,用于分页, before: 分页参数,取上一页最后一项的time获取下一页数据")
def comment_playlist(id, limit=None, offset=None, before=None):
    try:
        print(f"正在获取歌单 {id} 的评论...")
        response = api.comment_playlist(id=id, limit=limit, offset=offset, before=before, cookie=cookie)
        if response and response.status == 200:
            body = response.body
            if body:
                # 提取热门评论
                hot_comments = body.get('hotComments', [])
                # 提取普通评论
                comments = body.get('comments', [])
                
                # 简化热门评论
                simplified_hot_comments = []
                for comment in hot_comments:
                    if comment:
                        user = comment.get('user', {})
                        simplified_comment = {
                            '评论id': comment.get('commentId', ''),
                            '评论人': user.get('nickname', ''),
                            '评论内容': comment.get('content', '')
                        }
                        simplified_hot_comments.append(simplified_comment)
                
                # 简化普通评论
                simplified_comments = []
                for comment in comments:
                    if comment:
                        user = comment.get('user', {})
                        simplified_comment = {
                            '评论id': comment.get('commentId', ''),
                            '评论人': user.get('nickname', ''),
                            '评论内容': comment.get('content', '')
                        }
                        simplified_comments.append(simplified_comment)
                
                print("[成功] 歌单评论获取成功")
                return {
                    '热门评论': simplified_hot_comments,
                    '评论': simplified_comments,
                    '总数': body.get('total', 0),
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取歌单评论失败"
    except Exception as e:
        print(f"[失败] 获取歌单评论时出错: {e}")
        return f"获取歌单评论失败: {str(e)}"









@tool(description="发送/删除评论，必选参数: t: 1发送,2回复,0删除, type: 数字,资源类型,对应歌曲,专辑,歌单,对应以下类型:0:歌曲,2:歌单,3:专辑, id: 对应资源id, content: 要发送的内容或内容id,可通过/comment/mv等接口获取，可选参数: commentId: 回复的评论id(回复评论时必填), threadId: 如给动态发送评论，则不需要传id，需要传动态的threadId")
def comment(t, type, id, content, commentId=None, threadId=None):
    action = "发送" if t == 1 else "回复" if t == 2 else "删除"
    try:
        print(f"正在{action}评论...")
        response = api.comment(t=t, type=type, id=id, content=content, commentId=commentId, threadId=threadId, cookie=cookie)
        if response.status == 200:
            print(f"[成功] 评论{action}成功")
            return f"[成功] 评论{action}成功"
    except Exception as e:
        print(f"[失败] {action}评论时出错: {e}")





# 专辑相关接口
@tool(description="获取专辑内容，必选参数: id: 专辑id")
def album(id):
    try:
        print(f"正在获取专辑 {id} 的内容...")
        response = api.album(id=id, cookie=cookie)
        if response and response.status == 200:
            body = response.body
            if body:
                album_data = body.get('album', {})
                if album_data:
                    # 提取歌手信息
                    artists = album_data.get('artists', [])
                    chinese_artists = []
                    for artist in artists:
                        if artist:
                            chinese_artist = {
                                '歌手id': artist.get('id'),
                                '歌手名字': artist.get('name', '')
                            }
                            chinese_artists.append(chinese_artist)
                    
                    chinese_album = {
                        '专辑id': album_data.get('id'),
                        '专辑名字': album_data.get('name', ''),
                        '专辑描述': album_data.get('description', ''),
                        '歌手': chinese_artists
                    }
                    
                    print("[成功] 专辑内容获取成功")
                    return chinese_album
                else:
                    return "API 响应中无专辑数据"
            else:
                return "API 响应体为空"
        else:
            return "获取专辑内容失败"
    except Exception as e:
        print(f"[失败] 获取专辑内容时出错: {e}")
        return f"获取专辑内容失败: {str(e)}"

@tool(description="专辑动态信息，必选参数: id: 专辑id")
def album_detail_dynamic(id):
    try:
        print(f"正在获取专辑 {id} 的动态信息...")
        response = api.album_detail_dynamic(id=id, cookie=cookie)
        print(f"album_detail_dynamic status={_safe_response_status(response)}")
        if response and response.status == 200:
            body = response.body
            if body:
                # 将英文字段转换为中文
                chinese_body = {
                    '付费': body.get('paid', False),
                    '销量': body.get('sales', 0),
                    '显示类型': body.get('displayType', 0),
                    '在售': body.get('onSale', False),
                    '评论数': body.get('commentCount', 0),
                    '点赞数': body.get('likedCount', 0),
                    '分享数': body.get('shareCount', 0),
                    '订阅时间': body.get('subTime', 0),
                    '是否订阅': body.get('isSub', False),
                    '订阅数': body.get('subCount', 0),
                    '代码': body.get('code', 0)
                }
                
                print("[成功] 专辑动态信息获取成功")
                return chinese_body
            else:
                return "API 响应体为空"
        else:
            return "获取专辑动态信息失败"
    except Exception as e:
        print(f"[失败] 获取专辑动态信息时出错: {e}")
        return f"获取专辑动态信息失败: {str(e)}"

@tool(description="收藏/取消收藏专辑，必选参数: id: 专辑id, t: 1为收藏,其他为取消收藏")
def album_sub(id, t):
    action = "收藏" if t == 1 else "取消收藏"
    try:
        print(f"正在{action}专辑 {id}...")
        response = api.album_sub(id=id, t=t, cookie=cookie)
        if response and response.status == 200:
            body = response.body
            if body:
                print(f"[成功] 专辑{action}成功")
                return {
                    '代码': body.get('code', 0),
                    '消息': body.get('message', f'专辑{action}成功')
                }
            else:
                return "API 响应体为空"
        else:
            return f"专辑{action}失败"
    except Exception as e:
        print(f"[失败] {action}专辑时出错: {e}")
        return f"专辑{action}失败: {str(e)}"

@tool(description="获取已收藏专辑列表，可选参数: limit: 取出数量,默认为25, offset: 偏移数量,用于分页")
def album_sublist(limit=None, offset=None):
    try:
        print("正在获取已收藏专辑列表...")
        response = api.album_sublist(limit=limit, offset=offset, cookie=cookie)
        if response and response.status == 200:
            body = response.body
            if body:
                # 提取专辑列表
                albums = body.get('data', [])
                
                # 简化专辑列表
                chinese_albums = []
                for album in albums:
                    if album:
                        # 提取歌手信息
                        artists = album.get('artists', [])
                        artist_names = [a.get('name', '') for a in artists if a]
                        artists_str = ' / '.join(artist_names)
                        
                        chinese_album = {
                            '专辑id': album.get('id'),
                            '专辑名字': album.get('name', ''),
                            '歌手': artists_str,
                            '专辑封面': album.get('picUrl', '')
                        }
                        chinese_albums.append(chinese_album)
                
                print("[成功] 已收藏专辑列表获取成功")
                return {
                    '专辑列表': chinese_albums,
                    '总数': body.get('total', 0),
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取已收藏专辑列表失败"
    except Exception as e:
        print(f"[失败] 获取已收藏专辑列表时出错: {e}")
        return f"获取已收藏专辑列表失败: {str(e)}"

# 歌手相关接口
@tool(description="获取歌手单曲，必选参数: id: 歌手id")
def artists(id):
    try:
        print(f"正在获取歌手 {id} 的单曲...")
        response = api.artists(id=id, cookie=cookie)
        print(f"artists status={_safe_response_status(response)}")
        if response and response.status == 200:
            body = response.body
            if body:
                # 提取热门歌曲
                hot_songs = body.get('hotSongs', [])
                
                # 简化热门歌曲
                simplified_songs = []
                for song in hot_songs:
                    if song:
                        simplified_song = {
                            '歌曲id': song.get('id'),
                            '歌曲名字': song.get('name', '')
                        }
                        simplified_songs.append(simplified_song)
                
                print("[成功] 歌手单曲获取成功")
                return {
                    '热门歌曲': simplified_songs,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取歌手单曲失败"
    except Exception as e:
        print(f"[失败] 获取歌手单曲时出错: {e}")
        return f"获取歌手单曲失败: {str(e)}"


@tool(description="获取歌手专辑，必选参数: id: 歌手id，可选参数: limit: 取出数量,默认为30, offset: 偏移数量,用于分页")
def artist_album(id, limit=None, offset=None):
    try:
        print(f"正在获取歌手 {id} 的专辑...")
        response = api.artist_album(id=id, limit=limit, offset=offset, cookie=cookie)
        if response and response.status == 200:
            body = response.body
            if body:
                # 提取专辑列表
                albums = body.get('hotAlbums', [])
                
                # 简化专辑列表
                simplified_albums = []
                for album in albums:
                    if album:
                        simplified_album = {
                            '专辑id': album.get('id'),
                            '专辑名字': album.get('name', ''),
                            '发布时间': album.get('publishTime', 0),
                        }
                        simplified_albums.append(simplified_album)
                
                print("[成功] 歌手专辑获取成功")
                return {
                    '专辑列表': simplified_albums,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取歌手专辑失败"
    except Exception as e:
        print(f"[失败] 获取歌手专辑时出错: {e}")
        return f"获取歌手专辑失败: {str(e)}"

@tool(description="获取歌手描述，必选参数: id: 歌手id")
def artist_desc(id):
    try:
        print(f"正在获取歌手 {id} 的描述...")
        response = api.artist_desc(id=id, cookie=cookie)
        if response and response.status == 200:
            body = response.body
            if body:
                print("[成功] 歌手描述获取成功")
                return {
                    '歌手描述': body.get('introduction', ''),
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取歌手描述失败"
    except Exception as e:
        print(f"[失败] 获取歌手描述时出错: {e}")
        return f"获取歌手描述失败: {str(e)}"

@tool(description="获取歌手详情，必选参数: id: 歌手id")
def artist_detail(id):
    try:
        print(f"正在获取歌手 {id} 的详情...")
        response = api.artist_detail(id=id, cookie=cookie)

        if response and response.status == 200:
            body = response.body
            if body:
                # 提取歌手详情
                data = body.get('data', {})
                artist = data.get('artist', {})
                if artist:
                    chinese_artist = {
                        '歌手id': artist.get('id'),
                        '歌手名字': artist.get('name', ''),
                        '歌手别名': artist.get('alias', []),
                        '歌手描述': artist.get('briefDesc', ''),
                        '专辑数量': artist.get('albumSize', 0),
                        '单曲数量': artist.get('musicSize', 0),
                        'MV数量': artist.get('mvSize', 0),
                        '歌手头像': artist.get('avatar', '')
                    }
                    
                    print("[成功] 歌手详情获取成功")
                    return chinese_artist
                else:
                    return "API 响应中无歌手数据"
            else:
                return "API 响应体为空"
        else:
            return "获取歌手详情失败"
    except Exception as e:
        print(f"[失败] 获取歌手详情时出错: {e}")
        return f"获取歌手详情失败: {str(e)}"

# 相似推荐相关接口
@tool(description="获取相似歌手，必选参数: id: 歌手id")
def simi_artist(id):
    try:
        print(f"正在获取与歌手 {id} 相似的歌手...")
        response = api.simi_artist(id=id, cookie=cookie)
        if response and response.status == 200:
            body = response.body
            if body:
                # 提取相似歌手列表
                artists = body.get('artists', [])
                
                # 简化相似歌手列表
                simplified_artists = []
                for artist in artists:
                    if artist:
                        simplified_artist = {
                            '歌手id': artist.get('id'),
                            '歌手名字': artist.get('name', ''),
                            '歌手头像': artist.get('picUrl', '')
                        }
                        simplified_artists.append(simplified_artist)
                
                print("[成功] 相似歌手获取成功")
                return {
                    '相似歌手': simplified_artists,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取相似歌手失败"
    except Exception as e:
        print(f"[失败] 获取相似歌手时出错: {e}")
        return f"获取相似歌手失败: {str(e)}"




@tool(description="获取相似音乐，必选参数: id: 歌曲id")
def simi_song(id):
    try:
        print(f"正在获取与歌曲 {id} 相似的音乐...")
        response = api.simi_song(id=id, cookie=cookie)
        if response and response.status == 200:
            body = response.body
            if body:
                # 提取相似音乐列表
                songs = body.get('songs', [])
                
                # 简化相似音乐列表
                simplified_songs = []
                for song in songs:
                    if song:
                        # 提取歌手信息
                        artists = song.get('artists', [])
                        artist_names = [a.get('name', '') for a in artists if a]
                        artists_str = ' / '.join(artist_names)
                        
                        simplified_song = {
                            '歌曲id': song.get('id'),
                            '歌曲名字': song.get('name', ''),
                            '歌手': artists_str
                        }
                        simplified_songs.append(simplified_song)
                
                print("[成功] 相似音乐获取成功")
                return {
                    '相似音乐': simplified_songs,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取相似音乐失败"
    except Exception as e:
        print(f"[失败] 获取相似音乐时出错: {e}")
        return f"获取相似音乐失败: {str(e)}"



# 推荐相关接口
@tool(description="获取每日推荐歌单（今日专属推荐），适用于：今日歌单、今天有什么好歌单、每日推荐歌单")
def recommend_resource():
    try:
        print("正在获取每日推荐歌单...")
        response = api.recommend_resource(cookie=cookie)
        if response and response.status == 200:
            body = response.body
            if body:
                # 提取推荐歌单列表
                recommend = body.get('recommend', [])
                
                # 简化推荐歌单列表
                simplified_recommend = []
                for item in recommend:
                    if item:
                        simplified_item = {
                            '歌单id': item.get('id'),
                            '歌单名字': item.get('name', ''),
                            '歌单封面': item.get('picUrl', ''),
                            '封面url': item.get('picUrl', ''),
                            '描述': item.get('copywriter', '') or item.get('description', ''),
                            '歌曲数量': item.get('trackCount') or item.get('songCount', 0),
                            '播放量': item.get('playCount') or item.get('playcount', 0),
                        }
                        simplified_recommend.append(simplified_item)
                
                print("[成功] 每日推荐歌单获取成功")
                return {
                    '每日推荐歌单': simplified_recommend,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取每日推荐歌单失败"
    except Exception as e:
        print(f"[失败] 获取每日推荐歌单时出错: {e}")
        return f"获取每日推荐歌单失败: {str(e)}"

@tool(description="获取每日推荐歌曲（今日专属），适用于：今日推荐歌曲、日推、今天有什么好听的歌")
def recommend_songs():
    try:
        print("正在获取每日推荐歌曲...")
        response = api.recommend_songs(cookie=cookie)
        if response and response.status == 200:
            body = response.body
            if body:
                # 提取推荐歌曲列表
                songs = body.get('data', {}).get('dailySongs', [])
                
                # 简化推荐歌曲列表
                simplified_songs = []
                for song in songs:
                    if song:
                        artists_str = _join_artist_names(song.get('ar', []))
                        simplified_song = {
                            '歌曲id': song.get('id'),
                            '歌曲名字': song.get('name', ''),
                            '歌手': artists_str,
                            '专辑名字': _extract_song_album_name(song),
                            '封面url': _extract_song_cover_url(song),
                            '时长': song.get('dt', 0),
                        }
                        simplified_songs.append(simplified_song)
                
                print("[成功] 每日推荐歌曲获取成功")
                return {
                    '每日推荐歌曲': simplified_songs,
                    '代码': body.get('code', 0)
                }
            else:
                return "暂时获取不到每日推荐歌曲，请稍后再试"
        else:
            return "暂时获取不到每日推荐歌曲，请稍后再试"
    except Exception as e:
        print(f"[失败] 获取每日推荐歌曲时出错: {e}")
        return _friendly_tool_failure("暂时获取不到每日推荐歌曲，请稍后再试", e)



@tool(description="获取历史日推可用日期列表")
def history_recommend_songs():
    try:
        print("正在获取历史日推可用日期列表...")
        response = api.history_recommend_songs(cookie=cookie)
        if response.status == 200:
            print("[成功] 历史日推可用日期列表获取成功")
            return response.body
    except Exception as e:
        print(f"[失败] 获取历史日推可用日期列表时出错: {e}")
        return f"获取历史日推可用日期列表失败: {str(e)}"

@tool(description="获取历史日推详情数据，必选参数: date: 日期,通过历史日推可用日期列表接口获取,不能任意日期")
def history_recommend_songs_detail(date):
    try:
        print(f"正在获取 {date} 的历史日推详情...")
        response = api.history_recommend_songs_detail(date=date, cookie=cookie)
        if response and response.status == 200:
            body = response.body
            if body:
                # 提取歌曲列表
                songs = body.get('data', {}).get('songs', [])
                
                # 简化歌曲列表
                simplified_songs = []
                for song in songs:
                    if song:
                        # 提取歌手信息
                        artists = song.get('ar', [])
                        artist_names = [a.get('name', '') for a in artists if a]
                        artists_str = ' / '.join(artist_names)
                        
                        simplified_song = {
                            '歌曲id': song.get('id'),
                            '歌曲名字': song.get('name', ''),
                            '歌手': artists_str
                        }
                        simplified_songs.append(simplified_song)
                
                print("[成功] 历史日推详情获取成功")
                return {
                    '历史日推歌曲': simplified_songs,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取历史日推详情失败"
    except Exception as e:
        print(f"[失败] 获取历史日推详情时出错: {e}")
        return f"获取历史日推详情失败: {str(e)}"

@tool(description="私人FM")
def personal_fm():
    try:
        print("正在获取私人FM...")
        response = api.personal_fm(cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                songs = body.get('data', [])
                simplified_songs = []
                for song in songs:
                    if song:
                        artists_str = _join_artist_names(song.get('artists', []))
                        simplified_song = {
                            '歌曲id': song.get('id'),
                            '歌曲名字': song.get('name', ''),
                            '歌手': artists_str,
                            '专辑名字': _extract_song_album_name(song),
                            '封面url': _extract_song_cover_url(song),
                            '时长': song.get('duration', 0),
                        }
                        simplified_songs.append(simplified_song)
                
                print("[成功] 私人FM获取成功")
                return {
                    '私人FM歌曲': simplified_songs,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取私人FM失败"
    except Exception as e:
        print(f"[失败] 获取私人FM时出错: {e}")
        return f"获取私人FM失败: {str(e)}"





@tool(description="获取用户点赞音乐的id列表，必选参数: uid: 用户id")
def likelist():
    try:
        print(f"正在获取用户 {user_id} 的喜欢音乐列表...")
        response = api.likelist(uid=user_id, cookie=cookie)
        if response.status == 200:
            print("[成功] 喜欢音乐列表获取成功")
            return response.body
    except Exception as e:
        print(f"[失败] 获取喜欢音乐列表时出错: {e}")
        return f"获取喜欢音乐列表失败: {str(e)}"







@tool(description="最新专辑")
def album_newest():
    try:
        print("正在获取最新专辑...")
        response = api.album_newest(cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                albums = body.get('albums', [])
                simplified_albums = []
                for album in albums:
                    if album:
                        # 提取歌手信息
                        artists = album.get('artists', [])
                        artist_names = [a.get('name', '') for a in artists if a]
                        artists_str = ' / '.join(artist_names)
                        
                        simplified_album = {
                            '专辑id': album.get('id'),
                            '专辑名字': album.get('name', ''),
                            '歌手': artists_str,
                        }
                        simplified_albums.append(simplified_album)
                
                print("[成功] 最新专辑获取成功")
                return {
                    '最新专辑': simplified_albums,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取最新专辑失败"
    except Exception as e:
        print(f"[失败] 获取最新专辑时出错: {e}")
        return f"获取最新专辑失败: {str(e)}"



@tool(description="热门歌手，可选参数: limit: 取出数量,默认为50, offset: 偏移数量,用于分页")
def top_artists(limit=None, offset=None):
    try:
        print("正在获取热门歌手...")
        response = api.top_artists(limit=limit, offset=offset, cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                artists = body.get('artists', [])
                simplified_artists = []
                for artist in artists:
                    if artist:
                        simplified_artist = {
                            '歌手id': artist.get('id'),
                            '歌手名字': artist.get('name', '')
                        }
                        simplified_artists.append(simplified_artist)
                
                print("[成功] 热门歌手获取成功")
                return {
                    '热门歌手': simplified_artists,
                    '代码': body.get('code', 0),
                    '更多': body.get('more', False)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取热门歌手失败"
    except Exception as e:
        print(f"[失败] 获取热门歌手时出错: {e}")
        return f"获取热门歌手失败: {str(e)}"









# 个性化推荐相关接口
@tool(description="获取个性化推荐歌单（发现页推荐），可选参数: limit: 取出数量,默认为30。适用于：个性化推荐歌单、发现歌单、随便推荐些歌单")
def personalized(limit=30):
    try:
        print("正在获取个性化推荐歌单...")
        response = api.personalized(limit=limit, cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                playlists = body.get('result', [])
                simplified_playlists = []
                for playlist in playlists:
                    if playlist:
                        simplified_playlist = {
                            'id': playlist.get('id'),
                            'name': playlist.get('name', ''),
                            '封面url': playlist.get('picUrl', ''),
                            '描述': playlist.get('copywriter', '') or playlist.get('description', ''),
                            '歌曲数': playlist.get('trackCount', 0),
                            '播放量': playlist.get('playCount', 0),
                        }
                        simplified_playlists.append(simplified_playlist)
                
                print("[成功] 个性化推荐歌单获取成功")
                return {
                    '推荐歌单': simplified_playlists,
                    '代码': body.get('code', 0),
                    '有品味': body.get('hasTaste', False)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取个性化推荐歌单失败"
    except Exception as e:
        print(f"[失败] 获取个性化推荐歌单时出错: {e}")
        return f"获取个性化推荐歌单失败: {str(e)}"

@tool(description="获取个性化推荐新歌（发现页推荐），可选参数: limit: 取出数量,默认为10。适用于：个性化新歌、个性化推荐歌曲、个性化歌曲、推荐新歌、发现新歌、新音乐")
def personalized_newsong(limit=20):
    try:
        print("正在获取个性化推荐新歌...")
        response = api.personalized_newsong(limit=limit, cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                songs = body.get('result', [])
                simplified_songs = []
                for item in songs:
                    if item:
                        song = item.get('song', {})
                        if song:
                            artists_str = _join_artist_names(song.get('artists', []))
                            simplified_song = {
                                '歌曲id': song.get('id'),
                                '歌曲名字': song.get('name', ''),
                                '歌手': artists_str,
                                '专辑名字': _extract_song_album_name(song),
                                '封面url': str(item.get('picUrl') or _extract_song_cover_url(song) or '').strip(),
                                '时长': song.get('duration', 0),
                            }
                            simplified_songs.append(simplified_song)
                
                print("[成功] 个性化推荐新歌获取成功")
                return {
                    '推荐新音乐': simplified_songs
                }
            else:
                return "API 响应体为空"
        else:
            return "获取个性化推荐新歌失败"
    except Exception as e:
        print(f"[失败] 获取个性化推荐新歌时出错: {e}")
        return f"获取个性化推荐新歌失败: {str(e)}"





# 排行榜相关接口
@tool(description="排行榜")
def toplist():
    try:
        print("正在获取排行榜...")
        response = api.toplist(cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                top_lists = body.get('list', [])
                simplified_top_lists = []
                for top_list_item in top_lists:
                    if top_list_item:
                        simplified_top_list = {
                            '歌单id': top_list_item.get('id'),
                            '歌单名字': top_list_item.get('name', ''),
                            '描述': top_list_item.get('description', ''),
                            '封面url': _extract_playlist_cover_url(top_list_item),
                            '歌曲数量': top_list_item.get('trackCount', 0),
                            '播放量': top_list_item.get('playCount', 0),
                        }
                        simplified_top_lists.append(simplified_top_list)
                
                print("[成功] 排行榜获取成功")
                return {
                    '排行榜': simplified_top_lists,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取排行榜失败"
    except Exception as e:
        print(f"[失败] 获取排行榜时出错: {e}")
        return f"获取排行榜失败: {str(e)}"

@tool(description="排行榜详情，必选参数: id: 排行榜id")
def top_list(id):
    try:
        print(f"正在获取排行榜 {id} 的详情...")
        response = api.top_list(id=id, cookie=cookie)
        if response.status == 200:
            body = response.body
            print(body)
            if body:
                playlist = body.get('playlist', {})
                if playlist:
                    tracks = playlist.get('tracks', [])
                    simplified_tracks = []
                    for track in tracks:
                        if track:
                            # 提取歌手信息
                            artists = track.get('ar', [])
                            artist_names = [a.get('name', '') for a in artists if a]
                            artist_ids = [a.get('id') for a in artists if a]
                            artists_str = ' / '.join(artist_names)
                            artist_ids_str = ' / '.join(map(str, artist_ids)) if artist_ids else ''
                            
                            simplified_track = {
                                '歌曲id': track.get('id'),
                                'name': track.get('name', ''),
                                '歌手id': artist_ids_str,
                                '歌手name': artists_str
                            }
                            simplified_tracks.append(simplified_track)
                    
                    print("[成功] 排行榜详情获取成功")
                    return {
                        '排行榜名称': playlist.get('name', ''),
                        '排行榜描述': playlist.get('description', ''),
                        '歌曲列表': simplified_tracks,
                        '代码': body.get('code', 0)
                    }
                else:
                    return "排行榜信息为空"
            else:
                return "API 响应体为空"
        else:
            return "获取排行榜详情失败"
    except Exception as e:
        print(f"[失败] 获取排行榜详情时出错: {e}")
        return f"获取排行榜详情失败: {str(e)}"

@tool(description="排行榜详情")
def toplist_detail():
    try:
        print("正在获取排行榜详情...")
        response = api.toplist_detail(cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                list_of_lists = body.get('list', [])
                simplified_lists = []
                for item in list_of_lists:
                    if item:
                        # 提取排行榜基本信息
                        simplified_list = {
                            '排行榜id': item.get('id'),
                            '名称': item.get('name', ''),
                            '描述': item.get('description', ''),
                            '播放量': item.get('playCount', 0),
                            '歌曲数': item.get('trackCount', 0)
                        }
                        simplified_lists.append(simplified_list)
                
                print("[成功] 排行榜详情获取成功")
                return {
                    '排行榜详情': simplified_lists,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取排行榜详情失败"
    except Exception as e:
        print(f"[失败] 获取排行榜详情时出错: {e}")
        return f"获取排行榜详情失败: {str(e)}"

@tool(description="歌手排行榜，可选参数: type: 分类, 1: 华语, 2: 欧美3: 韩国 4: 日本")
def toplist_artist(type=1):
    try:
        print("正在获取歌手排行榜...")
        response = api.toplist_artist(type=type, cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                list_data = body.get('list', {})
                artists = list_data.get('artists', [])
                simplified_artists = []
                for artist in artists:
                    if artist:
                        simplified_artist = {
                            '歌手id': artist.get('id'),
                            '歌手名字': artist.get('name', ''),
                        }
                        simplified_artists.append(simplified_artist)
                
                print("[成功] 歌手排行榜获取成功")
                return {
                    '歌手排行榜': simplified_artists,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取歌手排行榜失败"
    except Exception as e:
        print(f"[失败] 获取歌手排行榜时出错: {e}")
        return f"获取歌手排行榜失败: {str(e)}"







# 消息相关接口
@tool(description="私信内容，可选参数: limit: 返回数量, offset: 偏移数量")
def msg_private(limit=None, offset=None):
    try:
        import json
        print("正在获取私信内容...")
        response = api.msg_private(limit=limit, offset=offset, cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                msgs = body.get('msgs', [])
                simplified_msgs = []
                for msg in msgs:
                    if msg:
                        from_user = msg.get('fromUser', {})
                        to_user = msg.get('toUser', {})
                        last_msg = msg.get('lastMsg', '')
                        
                        # 尝试解析 lastMsg 中的 JSON 字符串，提取简洁的消息内容
                        try:
                            msg_json = json.loads(last_msg)
                            if isinstance(msg_json, dict):
                                # 提取消息内容
                                if 'msg' in msg_json:
                                    last_msg = msg_json['msg']
                                elif 'title' in msg_json and msg_json['title']:
                                    last_msg = msg_json['title']
                                else:
                                    last_msg = '消息内容'
                        except:
                            # 如果解析失败，使用原始消息
                            pass
                        
                        simplified_msg = {
                            '发送者': from_user.get('nickname', ''),
                            '接收者': to_user.get('nickname', ''),
                            '最后一条消息': last_msg,
                            '最后消息时间': msg.get('lastMsgTime', 0),
                            '新消息数量': msg.get('newMsgCount', 0)
                        }
                        simplified_msgs.append(simplified_msg)
                
                print("[成功] 私信内容获取成功")
                return {
                    '私信列表': simplified_msgs,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取私信内容失败"
    except Exception as e:
        print(f"[失败] 获取私信内容时出错: {e}")
        return f"获取私信内容失败: {str(e)}"

@tool(description="按昵称搜索并发送文本私信，必选参数: nickname: 对方昵称关键词, msg: 消息内容，可选参数: limit: 搜索数量(默认5)")
def send_text_by_nickname(nickname, msg, limit=5):
    try:
        print("正在搜索收件人并发送文本私信...")
        search_resp = api.search(keywords=nickname, type=1002, limit=limit, offset=0, cookie=cookie)
        if not search_resp or search_resp.status != 200:
            return "发送失败：无法搜索到收件人"
        body = search_resp.body or {}
        result = body.get("result", {}) or {}
        profiles = result.get("userprofiles") or result.get("userProfiles") or []
        if not profiles:
            return "发送失败：未找到可私信的用户"

        def score_profile(p):
            try:
                nick = p.get("nickname", "") or ""
                followeds = int(p.get("followeds") or 0)
                user_type = int(p.get("userType") or 0)
                auth_status = int(p.get("authStatus") or 0)
            except Exception:
                nick, followeds, user_type, auth_status = "", 0, 0, 0
            score = 0
            if nick == nickname:
                score += 10**12
            score += followeds
            if auth_status:
                score += 10**8
            if user_type:
                score += 10**6
            return score

        best = max(profiles, key=score_profile)
        best_uid = best.get("userId") or best.get("user_id") or best.get("uid")
        best_nick = best.get("nickname", "") or nickname
        if not best_uid:
            return "发送失败：未找到收件人账号标识"

        resp = api.send_text(user_ids=[best_uid], msg=msg, cookie=cookie)
        if resp and resp.status == 200:
            return {
                "状态": "发送成功",
                "收件人": best_nick,
                "消息内容": msg,
            }
        return "发送失败：接口返回异常"
    except Exception as e:
        print(f"[失败] 按昵称发送文本私信时出错: {e}")
        return f"发送失败：{str(e)}"

@tool(description="发送私信-文本，必选参数: user_ids: 用户id列表, msg: 消息内容")
def send_text(user_ids, msg):
    try:
        import json
        print("正在发送文本私信...")
        response = api.send_text(user_ids=user_ids, msg=msg, cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                new_msgs = body.get('newMsgs', [])
                simplified_msgs = []
                for msg_item in new_msgs:
                    if msg_item:
                        from_user = msg_item.get('fromUser', {})
                        to_user = msg_item.get('toUser', {})
                        
                        # 尝试解析 msg 中的 JSON 字符串，提取消息内容
                        msg_content = msg_item.get('msg', '')
                        try:
                            msg_json = json.loads(msg_content)
                            if isinstance(msg_json, dict) and 'msg' in msg_json:
                                msg_content = msg_json['msg']
                        except:
                            pass
                        
                        simplified_msg = {
                            '发送者': from_user.get('nickname', ''),
                            '接收者': to_user.get('nickname', ''),
                            '消息内容': msg_content,
                            '发送时间': msg_item.get('time', 0),
                            '消息id': msg_item.get('id', 0)
                        }
                        simplified_msgs.append(simplified_msg)
                
                print("[成功] 文本私信发送成功")
                return {
                    '状态': '发送成功',
                    '发送结果': simplified_msgs,
                    '代码': body.get('code', 0),
                    '消息id': body.get('id', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "发送文本私信失败"
    except Exception as e:
        print(f"[失败] 发送文本私信时出错: {e}")
        return f"发送文本私信失败: {str(e)}"

@tool(description="发送私信-歌曲，必选参数: user_ids: 用户id列表, id: 歌曲id, msg: 消息内容")
def send_song(user_ids, id, msg):
    try:
        import json
        print("正在发送歌曲私信...")
        response = api.send_song(user_ids=user_ids, id=id, msg=msg, cookie=cookie)
        print(f"send_song status={_safe_response_status(response)}")
        if response.status == 200:
            body = response.body
            if body:
                new_msgs = body.get('newMsgs', [])
                simplified_msgs = []
                for msg_item in new_msgs:
                    if msg_item:
                        from_user = msg_item.get('fromUser', {})
                        to_user = msg_item.get('toUser', {})
                        
                        # 尝试解析 msg 中的 JSON 字符串，提取消息内容
                        msg_content = msg_item.get('msg', '')
                        try:
                            msg_json = json.loads(msg_content)
                            if isinstance(msg_json, dict) and 'msg' in msg_json:
                                msg_content = msg_json['msg']
                        except:
                            pass
                        
                        simplified_msg = {
                            '发送者': from_user.get('nickname', ''),
                            '接收者': to_user.get('nickname', ''),
                            '消息内容': msg_content,
                            '发送时间': msg_item.get('time', 0),
                            '消息id': msg_item.get('id', 0)
                        }
                        simplified_msgs.append(simplified_msg)
                
                print("[成功] 歌曲私信发送成功")
                return {
                    '状态': '分享歌曲成功',
                    '发送结果': simplified_msgs,
                    '代码': body.get('code', 0),
                    '消息id': body.get('id', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "发送歌曲私信失败"
    except Exception as e:
        print(f"[失败] 发送歌曲私信时出错: {e}")
        return f"发送歌曲私信失败: {str(e)}"

@tool(description="发送私信-专辑，必选参数: user_ids: 用户id列表, id: 专辑id, msg: 消息内容")
def send_album(user_ids, id, msg):
    try:
        import json
        print("正在发送专辑私信...")
        response = api.send_album(user_ids=user_ids, id=id, msg=msg, cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                new_msgs = body.get('newMsgs', [])
                simplified_msgs = []
                for msg_item in new_msgs:
                    if msg_item:
                        from_user = msg_item.get('fromUser', {})
                        to_user = msg_item.get('toUser', {})
                        
                        # 尝试解析 msg 中的 JSON 字符串，提取消息内容
                        msg_content = msg_item.get('msg', '')
                        try:
                            msg_json = json.loads(msg_content)
                            if isinstance(msg_json, dict) and 'msg' in msg_json:
                                msg_content = msg_json['msg']
                        except:
                            pass
                        
                        simplified_msg = {
                            '发送者': from_user.get('nickname', ''),
                            '接收者': to_user.get('nickname', ''),
                            '消息内容': msg_content,
                            '发送时间': msg_item.get('time', 0),
                            '消息id': msg_item.get('id', 0)
                        }
                        simplified_msgs.append(simplified_msg)
                
                print("[成功] 专辑私信发送成功")
                return {
                    '状态': '分享专辑成功',
                    '发送结果': simplified_msgs,
                    '代码': body.get('code', 0),
                    '消息id': body.get('id', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "发送专辑私信失败"
    except Exception as e:
        print(f"[失败] 发送专辑私信时出错: {e}")
        return f"发送专辑私信失败: {str(e)}"

@tool(description="发送私信-歌单，必选参数: user_ids: 用户id列表, playlist: 歌单id, msg: 消息内容")
def send_playlist(user_ids, playlist, msg):
    try:
        import json
        print("正在发送歌单私信...")
        # 直接调用 request 方法，绕过 send_playlist 方法，这样可以传递 playlist 参数
        response = api.request("/send/playlist", cookie, None, user_ids=user_ids, msg=msg, playlist=playlist)
        if response.status == 200:
            body = response.body
            if body:
                new_msgs = body.get('newMsgs', [])
                simplified_msgs = []
                for msg_item in new_msgs:
                    if msg_item:
                        from_user = msg_item.get('fromUser', {})
                        to_user = msg_item.get('toUser', {})
                        
                        # 尝试解析 msg 中的 JSON 字符串，提取消息内容
                        msg_content = msg_item.get('msg', '')
                        try:
                            msg_json = json.loads(msg_content)
                            if isinstance(msg_json, dict) and 'msg' in msg_json:
                                msg_content = msg_json['msg']
                        except:
                            pass
                        
                        simplified_msg = {
                            '发送者': from_user.get('nickname', ''),
                            '接收者': to_user.get('nickname', ''),
                            '消息内容': msg_content,
                            '发送时间': msg_item.get('time', 0),
                            '消息id': msg_item.get('id', 0)
                        }
                        simplified_msgs.append(simplified_msg)
                
                print("[成功] 歌单私信发送成功")
                return {
                    '状态': '分享歌单成功',
                    '发送结果': simplified_msgs,
                    '代码': body.get('code', 0),
                    '消息id': body.get('id', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "发送歌单私信失败"
    except Exception as e:
        print(f"[失败] 发送歌单私信时出错: {e}")
        return f"发送歌单私信失败: {str(e)}"

@tool(description="最近联系人")
def msg_recentcontact():
    try:
        print("正在获取最近联系人...")
        response = api.msg_recentcontact(cookie=cookie)
        if response.status == 200:
            body = response.body
            print(body)
            if body:
                # 从正确的路径获取联系人数据
                data = body.get('data', {})
                contacts = data.get('follow', [])
                simplified_contacts = []
                for contact in contacts:
                    if contact:
                        simplified_contact = {
                            '用户名称': contact.get('nickname', ''),
                            '用户id': contact.get('userId', ''),
                            '是否互相关注': contact.get('mutual', False)
                        }
                        simplified_contacts.append(simplified_contact)
                
                print("[成功] 最近联系人获取成功")
                return {
                    '最近联系人': simplified_contacts,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取最近联系人失败"
    except Exception as e:
        print(f"[失败] 获取最近联系人时出错: {e}")
        return f"获取最近联系人失败: {str(e)}"

@tool(description="私信历史，可选参数: limit: 返回数量, offset: 偏移数量")
def msg_private_history(uid, limit=10):
    try:
        import json
        print(f"正在获取与用户 {uid} 的私信历史...")
        response = api.msg_private_history(uid=uid, limit=limit, cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                msgs = body.get('msgs', [])
                simplified_msgs = []
                for msg in msgs:
                    if msg:
                        from_user = msg.get('fromUser', {})
                        to_user = msg.get('toUser', {})
                        
                        # 尝试解析 msg 中的 JSON 字符串，提取消息内容
                        msg_content = msg.get('msg', '')
                        try:
                            msg_json = json.loads(msg_content)
                            if isinstance(msg_json, dict) and 'msg' in msg_json:
                                msg_content = msg_json['msg']
                        except:
                            pass
                        
                        simplified_msg = {
                            '发送者': from_user.get('nickname', ''),
                            '接收者': to_user.get('nickname', ''),
                            '消息内容': msg_content,
                            '发送时间': msg.get('time', 0),
                        }
                        simplified_msgs.append(simplified_msg)
                
                print("[成功] 私信历史获取成功")
                return {
                    '私信历史': simplified_msgs,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
        else:
            return "获取私信历史失败"
    except Exception as e:
        print(f"[失败] 获取私信历史时出错: {e}")
        return f"获取私信历史失败: {str(e)}"







# 其他接口

@tool(description="专辑列表，可选参数: limit: 取出数量, offset: 偏移数量, area: 地区")
def album_list(limit=None, offset=None):
    try:
        print("正在获取专辑列表...")
        response = api.album_list(limit=limit, offset=offset, cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                products = body.get('products', [])
                simplified_albums = []
                for product in products:
                    if product:
                        simplified_album = {
                            '专辑id': product.get('albumId', ''),
                            '专辑名称': product.get('albumName', ''),
                            '艺术家': product.get('artistName', ''),
                            '发布时间': product.get('pubTime', 0),
                            '价格': product.get('price', 0),
                            '销量': product.get('saleNum', 0),
                            '是否新专辑': product.get('newAlbum', False)
                        }
                        simplified_albums.append(simplified_album)
                
                print("[成功] 专辑列表获取成功")
                return {
                    '专辑列表': simplified_albums,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
    except Exception as e:
        print(f"[失败] 获取专辑列表时出错: {e}")
        return f"获取专辑列表失败: {str(e)}"

@tool(description="专辑销售榜，可选参数: limit: 取出数量, offset: 偏移数量, albumType: 0为数字专辑,1为数字单曲, type: daily:日榜,week:周榜,year:年榜,total:总榜")
def album_songsaleboard(limit=None, offset=None, albumType=0, type='week'):
    try:
        print(f"正在获取专辑销售榜...")
        # 直接调用 request 方法，使用正确的接口路径
        response = api.request("/album/songsaleboard", cookie, None, limit=limit, offset=offset, albumType=albumType, type=type)
        if response.status == 200:
            body = response.body
            if body:
                products = body.get('products', [])
                simplified_albums = []
                for product in products:
                    if product:
                        simplified_album = {
                            '专辑id': product.get('albumId', ''),
                            '专辑名称': product.get('albumName', ''),
                            '艺术家': product.get('artistName', ''),
                            '价格': product.get('price', 0),
                            '销量': product.get('saleNum', 0)
                        }
                        simplified_albums.append(simplified_album)
                
                print("[成功] 专辑销售榜获取成功")
                return {
                    '专辑销售榜': simplified_albums,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
    except Exception as e:
        print(f"[失败] 获取专辑销售榜时出错: {e}")
        return f"获取专辑销售榜失败: {str(e)}"


@tool(description="专辑详情，必选参数: id: 专辑id")
def album_detail(id):
    try:
        print(f"正在获取专辑 {id} 的详情...")
        response = api.album_detail(id=id, cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                product = body.get('product', {})
                album = body.get('album', {})
                
                # 提取描述信息
                descr_list = product.get('descr', [])
                description = ''
                for descr_item in descr_list:
                    if descr_item and 'resource' in descr_item:
                        description += descr_item['resource'].replace('<br>', '\n')
                
                simplified_album = {
                    '专辑id': album.get('albumId', ''),
                    '专辑名称': album.get('albumName', ''),
                    '艺术家': album.get('artistName', ''),
                    '艺术家id': album.get('artistId', ''),
                    '封面': album.get('coverUrl', ''),
                    '价格': product.get('price', 0),
                    '销量': product.get('saleNum', 0),
                    '发布时间': product.get('pubTime', 0),
                    '是否免费': product.get('isFree', False),
                    '专辑费用': product.get('albumfee', 0),
                    '描述': description
                }
                
                print("[成功] 专辑详情获取成功")
                return {
                    '专辑详情': simplified_album,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
    except Exception as e:
        print(f"[失败] 获取专辑详情时出错: {e}")
        return f"获取专辑详情失败: {str(e)}"












@tool(description="已购单曲，可选参数: limit: 取出数量, offset: 偏移数量")
def song_purchased(limit=None, offset=None):
    try:
        print("正在获取已购单曲...")
        response = api.song_purchased(limit=limit, offset=offset, cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                data = body.get('data', {})
                songs = data.get('list', [])
                simplified_songs = []
                for song in songs:
                    if song:
                        simplified_song = {
                            '歌曲id': song.get('songId', ''),
                            '歌曲名称': song.get('name', ''),
                            '艺术家': song.get('artistName', ''),
                            '专辑名称': song.get('albumName', ''),
                            '专辑id': song.get('albumId', ''),
                            '是否为VIP歌曲': song.get('vip', False),
                            '是否为无损音质': song.get('sq', False)
                        }
                        simplified_songs.append(simplified_song)
                
                print("[成功] 已购单曲获取成功")
                return {
                    '已购单曲': simplified_songs,
                    '总数': data.get('count', 0),
                    '是否有更多': data.get('hasMore', False),
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
    except Exception as e:
        print(f"[失败] 获取已购单曲时出错: {e}")
        return f"获取已购单曲失败: {str(e)}"




@tool(description="歌手粉丝数量，必选参数: id: 歌手id，可选参数: limit: 取出粉丝数量, offset: 偏移数量")
def artist_follow_count(id, limit=None, offset=None):
    try:
        print(f"正在获取歌手 {id} 的粉丝数量...")
        response = api.artist_follow_count(id=id, limit=limit, offset=offset, cookie=cookie)
        if response.status == 200:
            print("[成功] 歌手粉丝数量获取成功")
            return response.body
    except Exception as e:
        print(f"[失败] 获取歌手粉丝数量时出错: {e}")


@tool(description="获取VIP信息，可选参数: uid: 用户id")
def vip_info():
    try:
        print("正在获取VIP信息...")
        response = api.vip_info(uid=user_id,cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                data = body.get('data', {})
                simplified_vip = {
                    '红钻VIP等级': data.get('redVipLevel', 0),
                    '音乐包': {
                        '过期时间': data.get('musicPackage', {}).get('expireTime', 0),
                        '等级': data.get('musicPackage', {}).get('vipLevel', 0),
                    },
                    '会员': {
                        '过期时间': data.get('associator', {}).get('expireTime', 0),
                        '等级': data.get('associator', {}).get('vipLevel', 0),
                    },
                    '家庭VIP': {
                        '过期时间': data.get('familyVip', {}).get('expireTime', 0),
                        '等级': data.get('familyVip', {}).get('vipLevel', 0),
                    },
                    'Red+': {
                        '过期时间': data.get('redplus', {}).get('expireTime', 0),
                        '等级': data.get('redplus', {}).get('vipLevel', 0),
                    },
                    '代码': body.get('code', 0)
                }
                
                print("[成功] VIP信息获取成功")
                return simplified_vip
            else:
                return "API 响应体为空"
    except Exception as e:
        print(f"[失败] 获取VIP信息时出错: {e}")
        return f"获取VIP信息失败: {str(e)}"

@tool(description="获取VIP信息(app端)，可选参数: uid: 用户id")
def vip_info_v2():
    try:
        print("正在获取VIP信息(app端)...")
        response = api.vip_info_v2(uid=user_id, cookie=cookie)
        if response.status == 200:
            body = response.body
            print(body)
            if body:
                data = body.get('data', {})
                simplified_vip = {
                    '红钻VIP等级': data.get('redVipLevel', 0),
                    '音乐包': {
                        '过期时间': data.get('musicPackage', {}).get('expireTime', 0),
                        '等级': data.get('musicPackage', {}).get('vipLevel', 0),
                    },
                    '会员': {
                        '过期时间': data.get('associator', {}).get('expireTime', 0),
                        '等级': data.get('associator', {}).get('vipLevel', 0),
                    },
                    '家庭VIP': {
                        '过期时间': data.get('familyVip', {}).get('expireTime', 0),
                        '等级': data.get('familyVip', {}).get('vipLevel', 0),
                    },
                    'Red+': {
                        '过期时间': data.get('redplus', {}).get('expireTime', 0),
                        '等级': data.get('redplus', {}).get('vipLevel', 0),
                    },
                    '代码': body.get('code', 0)
                }
                
                print("[成功] VIP信息(app端)获取成功")
                return simplified_vip
            else:
                return "API 响应体为空"
    except Exception as e:
        print(f"[失败] 获取VIP信息(app端)时出错: {e}")
        return f"获取VIP信息(app端)失败: {str(e)}"




@tool(description="获取客户端歌曲下载url，必选参数: id:int 音乐id")
def song_download_url(id, br=None):
    try:
        print(f"正在获取歌曲 {id} 的下载地址...")
        response = api.song_download_url(id=id, br=br, cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                # 初始化简化 URL 列表
                simplified_urls = []
                
                # 检查 body 是否为字符串
                if isinstance(body, str):
                    # 尝试解析字符串为 JSON
                    import json
                    try:
                        body = json.loads(body)
                        print("成功解析 JSON 响应")
                    except Exception as json_error:
                        print(f"JSON 解析失败: {json_error}")
                        return f"API 响应格式错误: {body}"
                
                # 检查 data 字段的类型
                if 'data' in body:
                    data = body['data']
                    # 如果 data 是字典，直接处理
                    if isinstance(data, dict):
                        simplified_url = {
                            '歌曲id': data.get('id', ''),
                            '下载地址': data.get('url', ''),
                            '比特率': data.get('br', 0),
                            '文件大小': data.get('size', 0),
                            '扩展名': data.get('type', ''),
                            'md5': data.get('md5', '')
                        }
                        simplified_urls.append(simplified_url)
                    # 如果 data 是列表，遍历处理
                    elif isinstance(data, list):
                        for item in data:
                            if item:
                                simplified_url = {
                                    '歌曲id': item.get('id', ''),
                                    '下载地址': item.get('url', ''),
                                    '比特率': item.get('br', 0),
                                    '文件大小': item.get('size', 0),
                                    '扩展名': item.get('type', ''),
                                    'md5': item.get('md5', '')
                                }
                                simplified_urls.append(simplified_url)
                    else:
                        return f"API 响应数据格式错误: {type(data)}"
                
                print("[成功] 歌曲下载地址获取成功")
                return {
                    '下载地址': simplified_urls,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
    except Exception as e:
        print(f"[失败] 获取歌曲下载地址时出错: {e}")
        return f"获取歌曲下载地址失败: {str(e)}"



# 最近播放相关接口
@tool(description="最近播放-歌曲，可选参数: limit: 返回数量")
def record_recent_song(limit=20):
    try:
        print("正在获取最近播放-歌曲...")
        response = api.record_recent_song(limit=limit, cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                data = body.get('data', {})
                songs = data.get('list', [])
                simplified_songs = []
                for song in songs:
                    if song:
                        # 从 data 字段中获取歌曲信息
                        song_data = song.get('data', {})
                        # 提取歌手信息
                        artists = song_data.get('ar', [])
                        artist_names = [artist.get('name', '') for artist in artists if artist]
                        artists_str = ' / '.join(artist_names)
                        
                        simplified_song = {
                            '歌曲id': song_data.get('id', ''),
                            '歌曲名称': song_data.get('name', ''),
                            '歌手': artists_str,
                        }
                        simplified_songs.append(simplified_song)
                
                print("[成功] 最近播放-歌曲获取成功")
                return {
                    '最近播放-歌曲': simplified_songs,
                    '总数': data.get('total', 0),
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
    except Exception as e:
        print(f"[失败] 获取最近播放-歌曲时出错: {e}")
        return f"获取最近播放-歌曲失败: {str(e)}"



@tool(description="最近播放-歌单，可选参数: limit: 返回数量")
def record_recent_playlist(limit=20):
    try:
        print("正在获取最近播放-歌单...")
        response = api.record_recent_playlist(limit=limit, cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                data = body.get('data', {})
                playlists = data.get('list', [])
                simplified_playlists = []
                for playlist in playlists:
                    if playlist:
                        # 从 data 字段中获取歌单信息
                        playlist_data = playlist.get('data', {})
                        simplified_playlist = {
                            '歌单id': playlist_data.get('id', ''),
                            '歌单名称': playlist_data.get('name', ''),
                        }
                        simplified_playlists.append(simplified_playlist)
                
                print("[成功] 最近播放-歌单获取成功")
                return {
                    '最近播放-歌单': simplified_playlists,
                    '总数': data.get('total', 0),
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
    except Exception as e:
        print(f"[失败] 获取最近播放-歌单时出错: {e}")
        return f"获取最近播放-歌单失败: {str(e)}"

@tool(description="最近播放-专辑，可选参数: limit: 返回数量")
def record_recent_album(limit=20):
    try:
        print("正在获取最近播放-专辑...")
        response = api.record_recent_album(limit=limit, cookie=cookie)
        if response.status == 200:
            body = response.body
            print(body)
            if body:
                data = body.get('data', {})
                albums = data.get('list', [])
                simplified_albums = []
                for album in albums:
                    if album:
                        # 从 data 字段中获取专辑信息
                        album_data = album.get('data', {})
                        simplified_album = {
                            '专辑id': album_data.get('id', ''),
                            '专辑名称': album_data.get('name', ''),
                            '封面': album_data.get('coverUrl', ''),
                            '歌手': album_data.get('artist', {}).get('name', ''),
                            '歌手id': album_data.get('artist', {}).get('id', ''),
                            '播放时间': album.get('playTime', 0)
                        }
                        simplified_albums.append(simplified_album)
                
                print("[成功] 最近播放-专辑获取成功")
                return {
                    '最近播放-专辑': simplified_albums,
                    '总数': data.get('total', 0),
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
    except Exception as e:
        print(f"[失败] 获取最近播放-专辑时出错: {e}")
        return f"获取最近播放-专辑失败: {str(e)}"





@tool(description="音乐百科 - 简要信息，必选参数: id: 歌曲ID")
def song_wiki_summary(id):
    try:
        print(f"正在获取歌曲 {id} 的音乐百科信息...")
        response = api.song_wiki_summary(id=id, cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                data = body.get('data', {})
                blocks = data.get('blocks', [])
                wiki_info = {}
                
                for block in blocks:
                    if block.get('code') == 'SONG_PLAY_ABOUT_SONG_BASIC':
                        # 提取音乐百科基本信息
                        creatives = block.get('creatives', [])
                        for creative in creatives:
                            creative_type = creative.get('creativeType')
                            if creative_type == 'songTag':
                                # 提取曲风信息
                                resources = creative.get('resources', [])
                                if resources:
                                    wiki_info['曲风'] = resources[0].get('uiElement', {}).get('mainTitle', {}).get('title', '')
                            elif creative_type == 'songBizTag':
                                # 提取推荐标签
                                resources = creative.get('resources', [])
                                tags = []
                                for resource in resources:
                                    tag = resource.get('uiElement', {}).get('mainTitle', {}).get('title', '')
                                    if tag:
                                        tags.append(tag)
                                if tags:
                                    wiki_info['推荐标签'] = tags
                            elif creative_type == 'language':
                                # 提取语种
                                text_links = creative.get('uiElement', {}).get('textLinks', [])
                                if text_links:
                                    wiki_info['语种'] = text_links[0].get('text', '')
                            elif creative_type == 'bpm':
                                # 提取BPM
                                text_links = creative.get('uiElement', {}).get('textLinks', [])
                                if text_links:
                                    wiki_info['BPM'] = text_links[0].get('text', '')
                
                print("[成功] 音乐百科信息获取成功")
                return {
                    '音乐百科': wiki_info,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
    except Exception as e:
        print(f"[失败] 获取音乐百科信息时出错: {e}")
        return f"获取音乐百科信息失败: {str(e)}"





@tool(description="回忆坐标，必选参数: id: 歌曲 ID")
def music_first_listen_info(id):
    try:
        print(f"正在获取歌曲 {id} 的回忆坐标信息...")
        response = api.music_first_listen_info(id=id, cookie=cookie)

        if response.status == 200:
            body = response.body
            print(body)
            if body:
                data = body.get('data', {})
                # 提取歌曲基本信息
                song_info = data.get('songInfoDto', {})
                # 提取首次听歌信息
                first_listen = data.get('musicFirstListenDto', {})
                # 提取总播放信息
                total_play = data.get('musicTotalPlayDto', {})
                # 提取最多播放信息
                most_play = data.get('musicPlayMostDto', {})
                # 提取收藏信息
                like_info = data.get('musicLikeSongDto', {})
                # 提取评论信息
                comment_info = data.get('musicCommentDto', {})
                # 提取频繁听歌信息
                frequent_listen = data.get('musicFrequentListenDto', {})
                
                simplified_info = {
                    '歌曲信息': {
                        '歌曲id': song_info.get('songId', ''),
                        '歌曲名称': song_info.get('songName', ''),
                        '歌手': song_info.get('singer', '')
                    },
                    '首次听歌': {
                        '日期': first_listen.get('date', ''),
                        '季节': first_listen.get('season', ''),
                        '时段': first_listen.get('period', ''),
                        '时间': first_listen.get('time', ''),
                        '听歌时长': first_listen.get('meetDuration', ''),
                        '描述': first_listen.get('meetDurationDesc', '')
                    },
                    '总播放': {
                        '播放次数': total_play.get('playCount', 0),
                        '总时长': total_play.get('duration', 0),
                        '描述': total_play.get('text', ''),
                        '最多播放年份': total_play.get('maxPlayTimes', [{}])[0].get('year', '') if total_play.get('maxPlayTimes') else ''
                    },
                    '最多播放': {
                        '日期': most_play.get('date', ''),
                        '播放次数': most_play.get('mostPlayedCount', 0),
                        '描述': most_play.get('text', '')
                    },
                    '收藏信息': {
                        '是否收藏': like_info.get('like', False),
                        '收藏日期': like_info.get('redTime', ''),
                        '描述': like_info.get('text', '')
                    },
                    '评论信息': {
                        '评论内容': comment_info.get('comment', ''),
                        '评论时间': comment_info.get('commentTimeStr', '')
                    },
                    '频繁听歌': {
                        '描述': frequent_listen.get('describe', ''),
                        '开始时间': frequent_listen.get('startTime', ''),
                        '结束时间': frequent_listen.get('endTime', '')
                    }
                }
                
                print("[成功] 回忆坐标信息获取成功")
                return {
                    '回忆坐标信息': simplified_info,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
    except Exception as e:
        print(f"[失败] 获取回忆坐标信息时出错: {e}")
        return f"获取回忆坐标信息失败: {str(e)}"















@tool(description="验证接口-二维码生成，必选参数: vid: 触发验证后,接口返回的verifyId, type: 触发验证后,接口返回的verifyType, token: 触发验证后,接口返回的verifyToken, evid: 触发验证后,接口返回的params的event_id, sign: 触发验证后,接口返回的params的sign")
def verify_getQr(vid, type, token, evid, sign):
    try:
        print("正在生成验证二维码...")
        response = api.verify_getQr(vid=vid, type=type, token=token, evid=evid, sign=sign, cookie=cookie)
        if response.status == 200:
            print("[成功] 验证二维码生成成功")
            return response.body
    except Exception as e:
        print(f"[失败] 生成验证二维码时出错: {e}")

@tool(description="验证接口-二维码检测，必选参数: qr: /verify/getQr接口返回的qr字符串")
def verify_qrcodestatus(qr):
    try:
        print("正在检测验证二维码状态...")
        response = api.verify_qrcodestatus(qr=qr, cookie=cookie)
        if response.status == 200:
            print("[成功] 验证二维码状态检测成功")
            return response.body
    except Exception as e:
        print(f"[失败] 检测验证二维码状态时出错: {e}")



@tool(description="根据nickname获取userid，必选参数: nicknames: 用户昵称,多个用分号(;)隔开")
def get_userids(nicknames):
    try:
        print("正在根据昵称获取用户id...")
        response = api.get_userids(nicknames=nicknames, cookie=cookie)
        if response.status == 200:
            print("[成功] 根据昵称获取用户id成功")
            return response.body
    except Exception as e:
        print(f"[失败] 根据昵称获取用户id时出错: {e}")

@tool(description="专辑简要百科信息，必选参数: id: 专辑id")
def ugc_album_get(id):
    try:
        print(f"正在获取专辑 {id} 的简要百科信息...")
        response = api.ugc_album_get(id=id, cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                data = body.get('data', {})
                # 提取艺术家信息
                artists = data.get('artistRepVos', [])
                artist_names = [artist.get('artistName', '') for artist in artists if artist]
                artists_str = ' / '.join(artist_names)

                # 提取专辑标签
                album_tags = data.get('songTags', [])
                album_tag_names = [tag.get('name', '') for tag in album_tags if tag]
                
                simplified_album = {
                    '专辑id': data.get('albumId', ''),
                    '专辑名称': data.get('albumName', ''),
                    '歌手': artists_str,

                    '公司': data.get('company', ''),
                    '发布时间': data.get('publishTime', 0),
                    '语种': data.get('language', ''),
                    '类型': data.get('type', ''),
                    '标签': album_tag_names,
                    '介绍': data.get('production', ''),
                    '英文名': data.get('transName', ''),

                }
                
                print("[成功] 专辑简要百科信息获取成功")
                return {
                    '专辑简要百科信息': simplified_album,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
    except Exception as e:
        print(f"[失败] 获取专辑简要百科信息时出错: {e}")
        return f"获取专辑简要百科信息失败: {str(e)}"

@tool(description="歌曲简要百科信息，必选参数: id: 歌曲id")
def ugc_song_get(id):
    try:
        print(f"正在获取歌曲 {id} 的简要百科信息...")
        response = api.ugc_song_get(id=id, cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                data = body.get('data', {})
                # 提取艺术家信息
                artists = data.get('artistRepVos', [])
                artist_names = [artist.get('artistName', '') for artist in artists if artist]
                artists_str = ' / '.join(artist_names)
                # 提取作词者信息
                lyric_artists = data.get('lyricArtists', [])
                lyric_artist_names = [artist.get('artistName', '') for artist in lyric_artists if artist]
                lyric_artists_str = ' / '.join(lyric_artist_names)
                # 提取作曲者信息
                compose_artists = data.get('composeArtists', [])
                compose_artist_names = [artist.get('artistName', '') for artist in compose_artists if artist]
                compose_artists_str = ' / '.join(compose_artist_names)
                # 提取编曲者信息
                arrange_artists = data.get('arrangeArtists', [])
                arrange_artist_names = [artist.get('artistName', '') for artist in arrange_artists if artist]
                arrange_artists_str = ' / '.join(arrange_artist_names)
                # 提取专辑信息
                album_info = data.get('albumRepVo', {})
                
                simplified_song = {
                    '歌曲id': data.get('songId', ''),
                    '歌曲名称': data.get('songName', ''),
                    '歌手': artists_str,
                    '副标题': data.get('songSubTitle', ''),
                    '公司': data.get('company', ''),
                    '发布时间': data.get('publishTime', 0),
                    '语种': data.get('language', ''),
                    '编号': data.get('no', ''),
                    '碟片': data.get('disc', ''),
                    '作词': lyric_artists_str,
                    '作曲': compose_artists_str,
                    '编曲': arrange_artists_str,
                    '英文名': data.get('transName', ''),
                    'MV id': data.get('mvIds', []),
                    '歌词': data.get('lyricContent', ''),
                    '播放地址': data.get('playUrl', ''),
                    '时长': data.get('duration', 0),
                    '专辑信息': {
                        '专辑id': album_info.get('albumId', ''),
                        '专辑名称': album_info.get('albumName', '')
                    }
                }
                
                print("[成功] 歌曲简要百科信息获取成功")
                return {
                    '歌曲简要百科信息': simplified_song,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
    except Exception as e:
        print(f"[失败] 获取歌曲简要百科信息时出错: {e}")
        return f"获取歌曲简要百科信息失败: {str(e)}"

@tool(description="艺术家简要百科信息，必选参数: id: 艺术家id")
def ugc_artist_get(id):
    try:
        print(f"正在获取艺术家 {id} 的简要百科信息...")
        response = api.ugc_artist_get(id=id, cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                data = body.get('data', {})
                
                simplified_artist = {
                    '艺术家id': data.get('artistId', ''),
                    '艺术家名称': data.get('artistName', ''),
                    '别名': data.get('alias', ''),
                    '地区': data.get('area', ''),
                    '类型': data.get('type', ''),
                    '简介': data.get('desc', ''),
                    '详细介绍': data.get('production', '')
                }
                
                print("[成功] 艺术家简要百科信息获取成功")
                return {
                    '艺术家简要百科信息': simplified_artist,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
    except Exception as e:
        print(f"[失败] 获取艺术家简要百科信息时出错: {e}")
        return f"获取艺术家简要百科信息失败: {str(e)}"


@tool(description="艺术家搜索，必选参数: keyword: 关键词，可选参数: offset: 偏移量, limit: 限制数量")
def ugc_artist_search(keyword, limit=5):
    try:
        print(f"正在搜索艺术家: {keyword}...")
        response = api.ugc_artist_search(keyword=keyword, limit=limit)
        if response.status == 200:
            body = response.body
            if body:
                data = body.get('data', {})
                artists = data.get('list', [])
                simplified_artists = []
                for artist in artists:
                    if artist:
                        simplified_artist = {
                            '艺术家id': artist.get('artistId', ''),
                            '艺术家名称': artist.get('artistName', ''),
                        }
                        simplified_artists.append(simplified_artist)
                
                print("[成功] 艺术家搜索成功")
                return {
                    '搜索结果': simplified_artists,
                    '总数': data.get('totalCount', 0),
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
    except Exception as e:
        print(f"[失败] 搜索艺术家时出错: {e}")
        return f"搜索艺术家失败: {str(e)}"




@tool(description="年度总结，必选参数: year: 年份")
def summary_annual(year):
    try:
        print(f"正在获取 {year} 年度总结...")
        response = api.summary_annual(year=year, cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                data = body.get('data', {})
                # 提取概览信息
                overview = data.get('meetTimeOverview', {})
                # 提取新发现信息
                new_discovery = data.get('newDiscoveryDTO', {})
                # 提取关键词信息
                keywords = data.get('keyWord', {})
                # 提取曲风播放排名
                genre_rank = data.get('genrePlayRank', {})
                # 提取季节听歌信息
                seasons = data.get('seasonsListen', {})
                # 提取月度听歌信息
                months = data.get('monthListenDTO', {})
                
                simplified_summary = {
                    '概览': {
                        '播放次数': overview.get('playCount', 0),
                        '播放时长': overview.get('playTime', 0),
                        'PC端播放时长': overview.get('pcTerminalPlayTime', 0),
                    },
                    '新发现': {
                        '总艺术家数': new_discovery.get('totalArtistCount', 0),
                        '新艺术家数': new_discovery.get('newArtistCount', 0),
                        '总曲风数': new_discovery.get('totalGenreCount', 0),
                        '新曲风数': new_discovery.get('newGenreCount', 0),
                        '特别曲风': new_discovery.get('specialGenre', []),
                        ' top5 艺术家': new_discovery.get('top5SingerDetails', [])
                    },
                    '关键词': {
                        '第一关键词': keywords.get('firstKeyWord', {}),
                        '第二关键词': keywords.get('secondKeyWord', {}),
                        '爱关键词': keywords.get('loveKeyword', {})
                    },
                    '曲风排名': {
                        '排名': genre_rank.get('genreRank', []),
                        '特别曲风排名': genre_rank.get('specialGenreRank', []),
                        '音乐年龄': genre_rank.get('musicAge', 0),
                        '描述': genre_rank.get('word', '')
                    },
                    '季节听歌': {
                        '春季': seasons.get('spring', {}),
                        '夏季': seasons.get('summer', {}),
                        '秋季': seasons.get('autumn', {}),
                        '冬季': seasons.get('winter', {})
                    },
                    '月度听歌': months.get('monthListenItemList', [])
                }
                
                print("[成功] 年度总结获取成功")
                return {
                    '年度总结': simplified_summary,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
    except Exception as e:
        print(f"[失败] 获取年度总结时出错: {e}")
        return f"获取年度总结失败: {str(e)}"


@tool(description="歌曲下载地址v1，# 必选参数 : id : 音乐 id,level: 默认jymaster，可选值为 hires=>Hi-Res, jyeffect => 高清环绕声, sky => 沉浸环绕声, dolby => 杜比全景声, jymaster => 超清母带")
def song_download_url_v1(id, level="jymaster"):
    fallback_message = "暂时获取不到歌曲下载地址，请稍后再试"

    for attempt in range(2):
        session_api = None
        try:
            print(f"正在获取歌曲 {id} 的下载地址(v1)...")
            with _NCM_API_LOCK:
                session_api, session_cookie = _open_music_api_only(force_refresh_env=attempt > 0)
                if session_api is None:
                    continue
                response = session_api.song_download_url_v1(id=id, level=level, cookie=session_cookie)

            if _should_retry_ncm_response(response) and attempt == 0:
                continue

            response_status = _safe_response_status(response)
            response_body = _safe_response_body(response)
            if response_status == 200:
                body = response_body
                if body:
                    data = body.get('data', {})
                    simplified_url = {
                        'id': data.get('id', ''),
                        'url': data.get('url', ''),
                        'br': data.get('br', 0),
                        'size': data.get('size', 0),
                        'type': data.get('type', ''),
                        'md5': data.get('md5', ''),
                        'level': data.get('level', ''),
                        'sr': data.get('sr', 0),
                        'time': data.get('time', 0)
                    }

                    print("[成功] 歌曲下载地址(v1)获取成功")
                    return {
                        'data': simplified_url,
                        '下载地址': simplified_url,
                        'code': body.get('code', 0),
                        '代码': body.get('code', 0)
                    }
        except Exception as e:
            print(f"[失败] 获取歌曲下载地址(v1)时出错: {e}")
            if attempt == 0 and _looks_like_internal_api_failure(e):
                continue
            return _friendly_tool_failure(fallback_message, e)
        finally:
            _destroy_music_api(session_api)

    return _friendly_tool_failure(fallback_message)





@tool(description="听歌数据今日歌曲")
def listen_data_today_song():
    try:
        print("正在获取听歌数据今日歌曲...")
        response = api.listen_data_today_song(cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                data = body.get('data', {})
                song_dtos = data.get('songDTOs', [])
                simplified_songs = []
                for song in song_dtos:
                    if song:
                        artists = song.get('artists', [])
                        artist_names = [artist.get('artistName', '') for artist in artists if artist]
                        artist_str = ' / '.join(artist_names)
                        
                        simplified_song = {
                            '歌曲id': song.get('songId', ''),
                            '歌曲名称': song.get('songName', ''),
                            '艺术家': artist_str,
                            '最后播放时间': song.get('lastPlayTime', 0),
                        }
                        simplified_songs.append(simplified_song)
                
                print("[成功] 听歌数据今日歌曲获取成功")
                return {
                    '今日听歌': simplified_songs,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
    except Exception as e:
        print(f"[失败] 获取听歌数据今日歌曲时出错: {e}")
        return f"获取听歌数据今日歌曲失败: {str(e)}"

@tool(description="听歌数据总计")
def listen_data_total():
    try:
        print("正在获取听歌数据总计...")
        response = api.listen_data_total(cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                data = body.get('data', {})
                simplified_total = {
                    '总时长': data.get('totalDuration', 0)
                }
                
                print("[成功] 听歌数据总计获取成功")
                return {
                    '听歌数据总计': simplified_total,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
    except Exception as e:
        print(f"[失败] 获取听歌数据总计时出错: {e}")
        return f"获取听歌数据总计失败: {str(e)}"

@tool(description="听歌数据实时报告，可选参数:  type: 维度类型 周 week 月 month; ")
def listen_data_realtime_report(type="week"):
    try:
        print("正在获取听歌数据实时报告...")
        response = api.listen_data_realtime_report(type=type, cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                data = body.get('data', {})
                listen_time_block = data.get('listenTimeDistributionBlock', {})
                week_today_block = data.get('weekTodayListenBlock', {})
                week_friends_block = data.get('weekFriendsListenBlock', {})
                friend_records = week_friends_block.get('friendListenRecords', [])
                
                # 简化朋友听歌记录
                simplified_friends = []
                for friend in friend_records:
                    if friend:
                        simplified_friend = {
                            '用户id': friend.get('userId', ''),
                            '用户名称': friend.get('username', ''),
                            '最后播放时间': friend.get('latestListenTime', 0)
                        }
                        simplified_friends.append(simplified_friend)
                
                simplified_report = {
                    '类型': data.get('type', ''),
                    '开始时间': data.get('startTime', 0),
                    '结束时间': data.get('endTime', 0),
                    '总播放时长': listen_time_block.get('playDuration', 0),
                    '听歌天数': listen_time_block.get('listenDays', 0),
                    '每日播放时长': listen_time_block.get('durationDetails', []),
                    '本周今日听歌': {
                        '歌曲数量': week_today_block.get('songCount', 0),
                        '收藏数量': week_today_block.get('redCount', 0)
                    }

                }
                
                print("[成功] 听歌数据实时报告获取成功")
                return {
                    '实时听歌报告': simplified_report,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
    except Exception as e:
        print(f"[失败] 获取听歌数据实时报告时出错: {e}")
        return f"获取听歌数据实时报告失败: {str(e)}"






@tool(description="传入歌单id, 获取相关歌单推荐，必选参数: id: 歌单id")
def playlist_detail_rcmd_get(id):
    try:
        print(f"正在获取歌单 {id} 的详情推荐...")
        response = api.playlist_detail_rcmd_get(id=id, cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                data = body.get('data', {})
                rec_playlists = data.get('recPlaylist', [])
                simplified_playlists = []
                for item in rec_playlists:
                    if item:
                        playlist = item.get('playlist', {})
                        simplified_playlist = {
                            '歌单id': playlist.get('id', ''),
                            '歌单名称': playlist.get('name', ''),
                            '播放量': playlist.get('playCount', 0),
                        }
                        simplified_playlists.append(simplified_playlist)
                
                print("[成功] 歌单详情推荐获取成功")
                return {
                    '推荐标题': data.get('rcmdTitle', ''),
                    '推荐歌单': simplified_playlists,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
    except Exception as e:
        print(f"[失败] 获取歌单详情推荐时出错: {e}")
        return f"获取歌单详情推荐失败: {str(e)}"














@tool(description="获取用户的创建歌单列表")
def user_playlist_create(uid=user_id):
    if uid is None:
        uid = get_user_id()
    else:
        uid = str(uid)
    try:
        print(f"正在获取用户创建歌单...")
        response = api.user_playlist_create(uid=uid, cookie=cookie)
        if response.status == 200:
            body = response.body
            if body:
                data = body.get('data', {})
                playlists = data.get('playlist', [])
                simplified_playlists = []
                for playlist in playlists:
                    if playlist:
                        simplified_playlist = {
                            '歌单id': playlist.get('id', ''),
                            '歌单名称': playlist.get('name', ''),
                            '歌曲数量': playlist.get('trackCount', 0),
                            '播放量': playlist.get('playCount', 0),
                            '创建时间': playlist.get('createTime', 0),
                            '更新时间': playlist.get('updateTime', 0),
                        }
                        simplified_playlists.append(simplified_playlist)
                
                print("[成功] 用户创建歌单获取成功")
                return {
                    '用户歌单': simplified_playlists,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
    except Exception as e:
        print(f"[失败] 获取用户创建歌单列表时出错: {e}")
        return f"获取用户创建歌单列表失败: {str(e)}"


@tool(description="用户的收藏歌单列表，必选参数: id: 歌单id, t: 操作类型")
def user_playlist_collect(id=user_id, limit=20, offset=0):
    try:
        print(f"正在获取用户的收藏歌单列表 ...")
        response = api.user_playlist_collect(uid=id, limit=limit, offset=offset)
        if response.status == 200:
            body = response.body
            print(body)
            if body:
                data = body.get('data', {})
                playlists = data.get('playlist', [])
                simplified_playlists = []
                for playlist in playlists:
                    if playlist:
                        simplified_playlist = {
                            '歌单id': playlist.get('id', ''),
                            '歌单名称': playlist.get('name', ''),
                            '歌曲数量': playlist.get('trackCount', 0),
                            '播放量': playlist.get('playCount', 0),
                            '创建时间': playlist.get('createTime', 0),
                            '更新时间': playlist.get('updateTime', 0),
                        }
                        simplified_playlists.append(simplified_playlist)
                
                print("[成功] 用户创建歌单获取成功")
                return {
                    '用户歌单': simplified_playlists,
                    '代码': body.get('code', 0)
                }
            else:
                return "API 响应体为空"
    except Exception as e:
        print(f"[失败] 获取用户的收藏歌单列表时出错: {e}")
        return f"获取用户的收藏歌单列表失败: {str(e)}"

@tool(description="根据歌曲名和歌手获取歌曲ID")
def get_song_id(song_name: str, artist: str = None, limit=10):
    """
        根据歌曲名和歌手获取歌曲ID
        说明 : 调用此接口 , 传入歌曲名和歌手名，获取歌曲的唯一ID
        必选参数 : song_name : 歌曲名称
        可选参数 : artist : 歌手名称，如果不传入则默认为原唱
                   limit : 返回的歌曲数量，默认10首
        :param song_name: 歌曲名称
        :param artist: 歌手名称
        :param limit: 返回的歌曲数量，默认10首
        :return: 歌曲信息列表，包含所有匹配的歌曲ID、名称和歌手
    """
    try:
        # 构建搜索关键词
        if artist:
            search_keyword = f"{song_name} {artist}"
        else:
            search_keyword = song_name
        
        print(f"正在搜索歌曲: {search_keyword}")
        response = api.search(keywords=search_keyword)
        
        if response.status == 200:
            result = response.body
            if result and 'result' in result and 'songs' in result['result']:
                songs = result['result']['songs']
                if songs:
                    matched_songs = []
                    # 如果指定了歌手，尝试找到所有匹配的歌手
                    if artist:
                        for song in songs:
                            # 检查歌曲的歌手是否匹配
                            song_artists = [a['name'] for a in song.get('artists', [])]
                            # 检查是否有任何一个歌手的名称包含传入的歌手名
                            if any(artist in a for a in song_artists):
                                song_info = {
                                    '歌曲ID': song.get('id', ''),
                                    '歌曲名称': song.get('name', ''),
                                    '歌手': song_artists
                                }
                                matched_songs.append(song_info)
                        if matched_songs:
                            # 限制返回的歌曲数量
                            limited_songs = matched_songs[:limit]
                            print(f"[成功] 成功获取 {len(limited_songs)} 首匹配的歌曲信息")
                            return {"匹配歌曲": limited_songs}
                        else:
                            # 如果没有找到匹配的歌手
                            print("[失败] 未找到指定歌手的歌曲")
                            return {"错误": "未找到指定歌手的歌曲"}
                    else:
                        # 没有指定歌手，返回所有结果
                        for song in songs:
                            song_artists = [a['name'] for a in song.get('artists', [])]
                            song_info = {
                                '歌曲ID': song.get('id', ''),
                                '歌曲名称': song.get('name', ''),
                                '歌手': song_artists
                            }
                            matched_songs.append(song_info)
                        # 限制返回的歌曲数量
                        limited_songs = matched_songs[:limit]
                        print(f"[成功] 成功获取 {len(limited_songs)} 首歌曲信息")
                        return {"匹配歌曲": limited_songs}
                else:
                    print("[失败] 未找到歌曲")
                    return {"错误": "未找到歌曲"}
            else:
                print("[失败] 搜索结果格式错误")
                return {"错误": "搜索结果格式错误"}
    except Exception as e:
        print(f"[失败] 获取歌曲ID时出错: {e}")
        return {"错误": f"获取歌曲ID时出错: {str(e)}"}

def _get_user_id_impl():
    session_user_id = user_id
    if session_user_id is not None:
        return session_user_id

    try:
        _, session_user_id, _, _ = _ensure_global_music_session()
        return session_user_id
    except Exception as e:
        print(f"[失败] 获取当前用户id时出错: {e}")
        return None


_user_detail_impl = user_detail


def _liked_songs_impl():
    for attempt in range(2):
        session_api = None
        try:
            with _NCM_API_LOCK:
                session_api, session_user_id, _, _ = _open_music_session(force_refresh_env=attempt > 0)
                if session_api is None or session_user_id is None:
                    break

                liked_response = session_api.likelist(uid=session_user_id)
                if _should_retry_ncm_response(liked_response) and attempt == 0:
                    continue

                liked_status = _safe_response_status(liked_response)
                liked_body = _safe_response_body(liked_response)
                if liked_status != 200:
                    message = str(liked_body.get("message") or "未知错误")
                    return f"获取失败：{message}"

                liked_song_ids = liked_body.get("ids", [])
                if not liked_song_ids:
                    return "暂无点赞歌曲"

                ids_str = ",".join(map(str, liked_song_ids))
                detail_response = session_api.song_detail(ids=ids_str)
                if _should_retry_ncm_response(detail_response) and attempt == 0:
                    continue

                detail_status = _safe_response_status(detail_response)
                detail_body = _safe_response_body(detail_response)
                songs = detail_body.get("songs", []) if detail_status == 200 else []

            if not isinstance(songs, list) or not songs:
                return "获取失败：未能读取点赞歌曲详情"

            liked_songs_list = []
            for song in songs:
                if not isinstance(song, dict):
                    continue

                song_id = song.get("id")
                song_name = song.get("name")
                if not song_id or not song_name:
                    continue

                duration = song.get("dt", 0)
                publish_time = song.get("publishTime", 0)
                album_name = _extract_song_album_name(song)
                cover_url = _extract_song_cover_url(song)

                artists = song.get("ar")
                if not isinstance(artists, list):
                    artists = song.get("artists") or []
                artist_name = _join_artist_names(artists)
                if not artist_name and isinstance(artists, list):
                    artist_name = ", ".join(
                        [
                            str(item.get("artistName") or item.get("name") or "").strip()
                            for item in artists
                            if isinstance(item, dict) and (item.get("artistName") or item.get("name"))
                        ]
                    ).strip()
                artist_id = artists[0].get("id") if artists and isinstance(artists[0], dict) else 0

                liked_songs_list.append(
                    {
                        "id": song_id,
                        "name": song_name,
                        "artist": artist_name,
                        "album": album_name,
                        "cover_url": cover_url,
                        "duration_ms": duration,
                        "publish_time": publish_time,
                    }
                )

            if liked_songs_list:
                return _build_liked_songs_result(liked_songs_list)

            return "暂无点赞歌曲"
        except Exception as e:
            print(f"[失败] 获取点赞歌曲出错: {e}")
            if attempt == 0 and _looks_like_internal_api_failure(e):
                continue
            return f"获取点赞歌曲出错：{str(e)}"
        finally:
            _destroy_music_api(session_api)

    return "暂无点赞歌曲"


@tool(description="获取我点赞的歌")
def liked_songs():
    return _liked_songs_impl()


@tool(description="获取用户信息")
def user_detail():
    return _user_detail_impl()



@tool(description="获取当前帐号用户id")
def get_user_id():
    return _get_user_id_impl()



# if __name__ == "__main__":
#     print(playlist_create('新歌单'))

