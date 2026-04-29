from .node_ncm_client import NeteaseCloudMusicApi

from . import music_config as config
from .ncm_env import get_ncm_process_env


def Music_account(*, force_refresh_env: bool = False):
    try:
        api = NeteaseCloudMusicApi(env=get_ncm_process_env(force_refresh=force_refresh_env))

        cookie = config.get_music_cookie()
        if cookie:
            api.set_cookie(cookie)
        else:
            config.warn_missing_music_cookie()
            return api, None, None, {}

        account_info = api.user_account(cookie=cookie)
        if account_info.status == 200:
            user_id = account_info.body["account"]["id"]
            user_name = account_info.body["profile"]["nickname"]
            print(f"   [成功] 用户: {user_name} (ID: {user_id})")
            return api, user_id, user_name, cookie

        if not force_refresh_env:
            try:
                api.destroy()
            except Exception:
                pass
            return Music_account(force_refresh_env=True)

        print(f"   [失败] Cookie无效: {account_info.body.get('message', '未知错误')}")
        return api, None, None, cookie
    except Exception as e:
        print(f"   [失败] 获取用户信息失败: {e}")
        return None, None, None, None
