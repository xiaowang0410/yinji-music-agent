
from __future__ import annotations

import re

from env_settings import get_first_env, load_env


load_env()

_COOKIE_ITEM_RE = re.compile(r"(?:^|;\s*)([^=;\s]+)=([^;]*)")
_PLACEHOLDER_PREFIXES = ("YOUR_", "<YOUR_", "${", "REPLACE_", "CHANGE_ME")
_MISSING_COOKIE_WARNING_SHOWN = False


def _clean_secret_value(value: str) -> str:
    text = str(value or "").strip().strip('"').strip("'")
    if not text:
        return ""

    lowered = text.lower()
    if lowered in {"none", "null", "undefined"}:
        return ""

    upper = text.upper()
    if any(upper.startswith(prefix) for prefix in _PLACEHOLDER_PREFIXES):
        return ""

    return text


def parse_cookie_string(raw_cookie: str) -> dict[str, str]:
    cookie: dict[str, str] = {}
    text = str(raw_cookie or "").strip()
    if not text:
        return cookie

    for match in _COOKIE_ITEM_RE.finditer(text):
        key = str(match.group(1) or "").strip()
        value = _clean_secret_value(match.group(2))
        if key and value:
            cookie[key] = value
    return cookie


def get_music_cookie() -> dict[str, str]:
    cookie = parse_cookie_string(get_first_env("NCM_COOKIE", "MUSIC_COOKIE", default=""))
    music_u_value = _clean_secret_value(get_first_env("NCM_MUSIC_U", "MUSIC_U", default=""))

    if music_u_value:
        cookie["MUSIC_U"] = music_u_value

    if cookie and "os" not in cookie:
        cookie["os"] = "pc"

    return cookie


def get_music_u() -> str:
    return str(get_music_cookie().get("MUSIC_U") or "").strip()


def warn_missing_music_cookie() -> None:
    global _MISSING_COOKIE_WARNING_SHOWN

    if _MISSING_COOKIE_WARNING_SHOWN:
        return

    _MISSING_COOKIE_WARNING_SHOWN = True
    print("[提示] 未配置 NCM_MUSIC_U/MUSIC_U，当前以未登录模式运行；需要个人账号能力时，请在 .env 中补上对应值。")


music_u = get_music_u()


MUSIC_TOOLS_MODULE_PATH = "tools.MusicTools.musicTools"

#get_song_details的配置
param_info= """
            获取歌曲详情
            说明 : 调用此接口 , 传入音乐 id(支持多个 id, 用 , 隔开), 可获得歌曲详情(dt为歌曲时长)
            必选参数 : song_id: 音乐 id, 如 ids="123456"
           
            """


playlist_tags="""
华语、欧美、日语、韩语、粤语
流行、摇滚、民谣、电子、舞曲、说唱、轻音乐、爵士、乡村、R&B/Soul、古典、民族、英伦、金属、朋克、蓝调、雷鬼、世界音乐、拉丁、New Age、古风、后摇、Bossa Nova
清晨、夜晚、学习、工作、午休、下午茶、地铁、驾车、运动、旅行、散步、酒吧
怀旧、清新、浪漫、伤感、治愈、放松、孤独、感动、兴奋、快乐、安静、思念
综艺、影视原声、ACG、儿童、校园、游戏、70 后、80 后、90 后、网络歌曲、KTV、经典、翻唱、吉他、钢琴、器乐、榜单、00 后
"""


artist_list_params="""
 歌手分类列表
        说明 : 调用此方法,可获取歌手分类列表
        可选参数 :
        limit : 返回数量 , 默认为 30 offset : 偏移数量，用于分页 , 如 :( 页数 -1)*30, 其中 30 为 limit 的值 , 默认为 0
        initial: 按首字母索引查找参数,如 /artist/list?type=1&area=96&initial=b 返回内容将以 name 字段开头为 b 或者拼音开头为 b 为顺序排列, 热门传-1,#传 0
        type 取值: -1:全部   1:男歌手   2:女歌手  3:乐队
        area 取值: -1:全部  7:华语  96:欧美  8:日本   16:韩国 0:其他
"""


song_url_v1_params="""
必选参数 : id : 音乐 id
        level: 播放音质等级, 分为 standard => 标准,higher => 较高, exhigh=>极高,
        lossless=>无损, hires=>Hi-Res, jyeffect => 高清环绕声, sky => 沉浸环绕声, dolby => 杜比全景声, jymaster => 超清母带
        说明：杜比全景声音质需要设备支持，不同的设备可能会返回不同码率的url。cookie需要传入os=pc保证返回正常码率的url。
        """
