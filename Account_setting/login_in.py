import time
import json
import os

import pyqrcode
import qrcode
from PIL import Image
from tools.MusicTools.node_ncm_client import NeteaseCloudMusicApi

from tools.MusicTools.ncm_env import get_ncm_process_env

class Login:
    def __init__(self, cookie_file='cookie.json'):
        self.api = NeteaseCloudMusicApi(env=get_ncm_process_env())
        self.cookie = {}
        self.user_name = None
        self.user_id = None
        self.cookie_file = cookie_file
        # 尝试从文件加载cookie
        self._load_cookie()

    def _load_cookie(self):
        """从文件加载cookie"""
        if os.path.exists(self.cookie_file):
            try:
                with open(self.cookie_file, 'r', encoding='utf-8') as f:
                    self.cookie = json.load(f)
                if self.cookie:
                    print(f"已从文件加载 cookie 文件: {self.cookie_file}")
                    self.api.set_cookie(self.cookie)
                    # 验证cookie是否有效
                    if self._is_cookie_valid():
                        # 获取用户信息
                        try:
                            account_info = self.api.user_account()
                            if account_info.status == 200 and account_info.body.get('code') == 200:
                                self.user_name = account_info.body["profile"]["nickname"]
                                self.user_id = account_info.body["profile"]["userId"]
                                print(f"欢迎用户{self.user_name}!")
                                print("Cookie有效，无需重新登录")
                            else:
                                print("Cookie无效，需要重新登录")
                                self.cookie = {}
                        except Exception:
                            print("获取用户信息失败，需要重新登录")
                            self.cookie = {}
                    else:
                        print("Cookie无效，需要重新登录")
                        self.cookie = {}
            except Exception as e:
                print(f"加载cookie失败: {e}")
                self.cookie = {}

    def _save_cookie(self):
        """保存cookie到文件"""
        if self.cookie:
            try:
                with open(self.cookie_file, 'w', encoding='utf-8') as f:
                    json.dump(self.cookie, f, ensure_ascii=False, indent=2)
                print(f"Cookie已保存到文件: {self.cookie_file}")
            except Exception as e:
                print(f"保存cookie失败: {e}")

    def _is_cookie_valid(self):
        """验证cookie是否有效"""
        try:
            response = self.api.login_status(cookie=self.cookie)
            if response.status == 200 and response.body.get('code') == 200:
                return True
            return False
        except Exception:
            return False

    def login_qr(self):
        # 检查是否已有有效cookie
        if self.cookie and self._is_cookie_valid():
            print("已有有效cookie，无需重新登录")
            return self.api

        key=self.api.login_qr_key(cookie=self.cookie).body["data"]["unikey"]
        qr_url=self.api.login_qr_create(key=key, cookie=self.cookie).body["data"]["qrurl"]
        print(qr_url)
        img=qrcode.make(qr_url)
        img.show()

        #轮询：
        state={
            800:"二维码过期...",801:"等待扫码...",
            802:"已扫描,等待确认...",803:"登录成功...",
        }

        while True:
            response=self.api.login_qr_check(key=key, cookie=self.cookie)
            print(state[response.body['code']])
            if response.body['code'] == 803:
                print("扫码登录成功，正在保存 cookie...")
                self.cookie = response.body['cookie']
                self.api.set_cookie(self.cookie)

                self.user_name =self.api.user_account().body["profile"]["nickname"]
                self.user_id=self.api.user_account().body["profile"]["userId"]
                print(f"欢迎用户{self.user_name}!")
                # 保存cookie到文件
                self._save_cookie()
                return self.api
            time.sleep(2)

def login():
    login=Login()
    return login.login_qr()

# 测试函数
def test_login():
    """测试登录功能"""
    print("开始测试登录功能...")
    # 获取API实例
    api = login()
    
    # 验证登录是否成功
    try:
        # 获取用户账号信息
        account_info = api.user_account()
        if account_info.status == 200 and account_info.body.get('code') == 200:
            user_name = account_info.body["profile"]["nickname"]
            user_id = account_info.body["profile"]["userId"]
            print(f"✅ 登录测试成功！")
            print(f"   用户: {user_name}")
            print(f"   用户ID: {user_id}")
        else:
            print("❌ 登录测试失败: 获取账号信息失败")
            print(f"   错误信息: {account_info.body.get('message', '未知错误')}")
    except Exception as e:
        print(f"❌ 登录测试失败: {e}")

if __name__ == "__main__":
    test_login()






