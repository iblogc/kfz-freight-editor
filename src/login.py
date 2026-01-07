import requests
import json
from .utils import logger

class LoginManager:
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
        }
        self.session.headers.update(self.headers)

    def login(self, username, password):
        """
        登录孔网
        :param username: 用户名
        :param password: 密码
        :return: (bool, str) - (成功与否, 消息/错误信息)
        """
        login_url = 'https://login.kongfz.com/Pc/Login/account'
        params = {
            'loginName': username,
            'loginPass': password,
            'returnUrl': 'https://www.kongfz.com/',
            'autoLogin': 0
        }

        try:
            # 清除旧 cookie
            self.session.cookies.clear()
            
            logger.info(f"正在尝试登录用户: {username} ...")
            response = self.session.post(login_url, data=params, timeout=15)
            
            if response.status_code == 200:
                try:
                    res_json = response.json()
                except json.JSONDecodeError:
                    res_json = {}

                # 检查 Set-Cookie 和 errCode
                # 参考 kfz-cookie-monitor 逻辑
                set_cookie = response.headers.get('Set-Cookie', '')
                if 'PHPSESSID' in set_cookie and not res_json.get("errCode"):
                    logger.info("登录成功")
                    return True, "登录成功"
                else:
                    err_msg = res_json.get('errInfo', '未知错误')
                    if res_json.get("errCode"):
                         err_msg = f"{res_json.get('errCode')}: {err_msg}"
                    logger.error(f"登录失败: {err_msg}")
                    return False, err_msg
            else:
                logger.error(f"登录请求失败: {response.status_code}")
                return False, f"HTTP Error: {response.status_code}"

        except Exception as e:
            logger.error(f"登录异常: {e}")
            return False, str(e)

    def get_cookies(self):
        """
        获取当前 session 的 cookies 字典
        """
        return self.session.cookies.get_dict()
