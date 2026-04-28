"""
百度网盘核心API模块
使用网页端Cookie模拟登录，无需开发者账号

下载方案：
  使用 pcs.baidu.com/rest/2.0/pcs/file?method=locatedownload 接口
  只需要 BDUSS + 动态计算的 rand 参数（SHA1），不需要 sign/timestamp
  此方案来自 BaiduPCS-Py 开源项目，经过验证可用
"""
import os
import re
import json
import time
import pickle
import hashlib
import requests
import threading
from urllib.parse import quote_plus

# 接口地址
BAIDU_HOME = "https://pan.baidu.com/disk/home"
BAIDU_LIST_API = "https://pan.baidu.com/api/list"
BAIDU_QUOTA_API = "https://pan.baidu.com/api/quota"
PCS_LOCATE_API = "https://pcs.baidu.com/rest/2.0/pcs/file"

# 模拟浏览器 UA（用于登录验证、文件列表）
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# PCS 客户端 UA（用于下载）
PCS_UA = "softxm;netdisk"

# 百度网盘 App ID
PAN_APP_ID = "250528"

HEADERS = {
    "User-Agent": BROWSER_UA,
    "Referer": "https://pan.baidu.com/disk/home",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def _md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


class LoginExpiredError(Exception):
    pass


class APIError(Exception):
    pass


class DownloadError(Exception):
    pass


class BaiduPanAPI:
    """百度网盘API封装类"""

    def __init__(self, session_file=None, log_callback=None):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.bdstoken = None
        self.uk = None
        self.username = None
        self._bduss = None   # 从 Cookie 中提取，用于计算 rand
        self.session_file = session_file or os.path.join(
            os.path.expanduser("~"), ".bdpan_session.pkl"
        )
        self._log = log_callback or (lambda msg: None)
        self._load_session()

    def set_log_callback(self, callback):
        self._log = callback

    def _load_session(self):
        try:
            if os.path.exists(self.session_file):
                with open(self.session_file, "rb") as f:
                    cookies = pickle.load(f)
                    self.session.cookies.update(cookies)
                    self._bduss = cookies.get("BDUSS", "")
        except Exception:
            pass

    def _save_session(self):
        try:
            save_dir = os.path.dirname(self.session_file)
            if save_dir:
                os.makedirs(save_dir, exist_ok=True)
            with open(self.session_file, "wb") as f:
                pickle.dump(dict(self.session.cookies), f)
        except Exception:
            pass

    def update_cookies(self, cookies: dict):
        """
        更新Cookie（支持字典格式）
        兼容旧版调用名 update_cookies_from_browser
        """
        if not cookies:
            return
        self.session.cookies.update(cookies)
        # 提取 BDUSS
        bduss = cookies.get("BDUSS", "")
        if bduss:
            self._bduss = bduss
            self._log(f"[API] BDUSS已更新，长度={len(bduss)}")
        else:
            self._log("[API] 警告：Cookie中未找到BDUSS字段")
        self._save_session()

    # 兼容旧版调用
    def update_cookies_from_browser(self, cookies: dict):
        self.update_cookies(cookies)

    def set_cookie_string(self, cookie_str: str):
        """
        直接解析 Cookie 字符串（如从浏览器开发者工具复制的整行 Cookie）
        支持两种格式：
          1. 完整格式：BDUSS=xxx; STOKEN=yyy; ...
          2. 仅BDUSS：BDUSS=xxx（用户只复制了BDUSS这一行）
        """
        cookies = {}
        # 先尝试按分号分割
        for item in cookie_str.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                k = k.strip()
                v = v.strip()
                if k:
                    cookies[k] = v
        if cookies:
            self.update_cookies(cookies)
            return True
        return False

    def _extract_bdstoken(self, html):
        for pat in [
            r'"bdstoken"\s*:\s*"([a-f0-9A-F]{32})"',
            r'bdstoken\s*=\s*[\'"]([a-f0-9A-F]{32})[\'"]',
            r'"bdstoken":"([a-f0-9A-F]{32})"',
        ]:
            m = re.search(pat, html)
            if m:
                return m.group(1)
        return None

    def _extract_uk(self, html):
        for pat in [r'"uk"\s*:\s*(\d+)', r'"uk":(\d+)']:
            m = re.search(pat, html)
            if m:
                return m.group(1)
        return None

    def _calc_rand(self, bduss: str, uid: str, timestamp: str) -> str:
        """
        计算 locatedownload 接口所需的 rand 参数
        算法来自 BaiduPCS-Py 开源项目
        """
        enc = _sha1(bduss)
        devuid = _md5(bduss).upper() + "|0"
        rand = _sha1(enc + uid + "ebrcUYiuxaZv2XGu7KIYKxUrqfnOfpDF" + timestamp + devuid)
        return rand, devuid

    def _refresh_home(self):
        """访问网盘主页，提取 bdstoken / uk"""
        try:
            resp = self.session.get(BAIDU_HOME, timeout=20)
            html = resp.text
            token = self._extract_bdstoken(html)
            uk = self._extract_uk(html)
            if token:
                self.bdstoken = token
            if uk:
                self.uk = uk
            self._log(f"[API] 主页刷新完成，bdstoken={'已获取' if self.bdstoken else '未获取'}，uk={self.uk}")
            return True
        except Exception as e:
            self._log(f"[API] 刷新主页失败: {e}")
            return False

    def check_login(self):
        try:
            resp = self.session.get(BAIDU_HOME, timeout=20, allow_redirects=True)
            if "passport.baidu.com" in resp.url or "login" in resp.url.lower():
                self._log("[API] 未登录（重定向到登录页）")
                return False
            html = resp.text
            if "bdstoken" in html or '"uk"' in html or "yunData" in html:
                self.bdstoken = self._extract_bdstoken(html)
                self.uk = self._extract_uk(html)
                # 从 Cookie 中提取 BDUSS
                self._bduss = self.session.cookies.get("BDUSS", self._bduss or "")
                self._save_session()
                self._log(f"[API] 已登录，bdstoken={'已获取' if self.bdstoken else '未获取'}，BDUSS={'已获取' if self._bduss else '未获取'}")
                return True
        except Exception as e:
            self._log(f"[API] 检查登录异常: {e}")

        # 备用：quota接口
        try:
            resp = self.session.get(
                BAIDU_QUOTA_API,
                params={"checkfree": 1, "checkexpire": 1},
                timeout=10
            )
            data = resp.json()
            if data.get("errno") == 0:
                self._bduss = self.session.cookies.get("BDUSS", self._bduss or "")
                self._refresh_home()
                self._save_session()
                self._log("[API] 已登录（quota接口验证）")
                return True
        except Exception as e:
            self._log(f"[API] quota接口异常: {e}")

        return False

    def get_user_info(self):
        try:
            resp = self.session.get(
                BAIDU_QUOTA_API,
                params={"checkfree": 1, "checkexpire": 1},
                timeout=10
            )
            data = resp.json()
            if data.get("errno") == 0:
                used = data.get("used", 0)
                total = data.get("total", 0)
                return {
                    "used": used,
                    "total": total,
                    "used_gb": round(used / 1024 ** 3, 2),
                    "total_gb": round(total / 1024 ** 3, 2),
                }
        except Exception:
            pass
        return None

    def list_files(self, path="/", order="name", desc=0, page=1, num=100):
        params = {
            "dir": path,
            "order": order,
            "desc": desc,
            "showempty": 1,
            "web": 1,
            "page": page,
            "num": num,
            "app_id": PAN_APP_ID,
            "bdstoken": self.bdstoken or "",
            "logid": "",
            "clienttype": 0,
        }
        try:
            resp = self.session.get(BAIDU_LIST_API, params=params, timeout=15)
            data = resp.json()
            if data.get("errno") == 0:
                return data.get("list", [])
            elif data.get("errno") == -6:
                raise LoginExpiredError("登录已过期，请重新登录")
            else:
                self._log(f"[API] 获取文件列表失败，errno={data.get('errno')}")
        except LoginExpiredError:
            raise
        except Exception as e:
            raise APIError(f"获取文件列表失败: {e}")
        return []

    def list_all_files(self, path="/"):
        all_files = []
        page = 1
        while True:
            files = self.list_files(path, page=page, num=200)
            if not files:
                break
            all_files.extend(files)
            if len(files) < 200:
                break
            page += 1
        return all_files

    def get_download_link(self, remote_path: str) -> str:
        """
        获取文件真实下载链接
        使用 pcs.baidu.com/rest/2.0/pcs/file?method=locatedownload 接口
        只需要 BDUSS，不需要 sign/timestamp
        """
        bduss = self._bduss or self.session.cookies.get("BDUSS", "")
        if not bduss:
            self._log("[下载] 未找到BDUSS，无法获取下载链接")
            return None

        uid = str(self.uk or "")
        timestamp = str(int(time.time()))
        rand, devuid = self._calc_rand(bduss, uid, timestamp)

        self._log(f"[下载] 获取下载链接: {os.path.basename(remote_path)}")
        self._log(f"[下载] 使用locatedownload接口，timestamp={timestamp}")

        params = {
            "apn_id": "1_0",
            "app_id": PAN_APP_ID,
            "channel": "0",
            "check_blue": "1",
            "clienttype": "17",
            "es": "1",
            "esl": "1",
            "freeisp": "0",
            "method": "locatedownload",
            "path": quote_plus(remote_path),
            "queryfree": "0",
            "use": "0",
            "ver": "4.0",
            "time": timestamp,
            "rand": rand,
            "devuid": devuid,
            "cuid": devuid,
        }

        headers = {
            "User-Agent": PCS_UA,
            "Cookie": f"BDUSS={bduss}",
        }

        try:
            resp = requests.get(
                PCS_LOCATE_API,
                params=params,
                headers=headers,
                timeout=20
            )
            self._log(f"[下载] locatedownload HTTP状态: {resp.status_code}")

            if resp.status_code != 200:
                self._log(f"[下载] locatedownload返回非200: {resp.status_code}")
                return None

            info = resp.json()
            self._log(f"[下载] locatedownload返回: {str(info)[:200]}")

            if info.get("host") == "issuecdn.baidupcs.com":
                self._log("[下载] 文件被百度屏蔽（issuecdn），无法下载")
                return None

            urls = info.get("urls", [])
            if urls:
                url = urls[0].get("url", "")
                if url:
                    self._log(f"[下载] 成功获取下载链接: {url[:80]}...")
                    return url

            self._log(f"[下载] 未找到下载链接，完整返回: {info}")
            return None

        except Exception as e:
            self._log(f"[下载] locatedownload异常: {e}")
            return None

    def download_file(self, fs_id, file_path, save_dir, progress_callback=None,
                      stop_event=None):
        """
        下载单个文件，支持断点续传
        file_path: 文件在网盘中的完整路径（如 /电影/xxx.mp4）
        """
        file_name = os.path.basename(file_path)
        local_path = os.path.join(save_dir, file_name)
        part_path = local_path + ".bdpart"

        self._log(f"[下载] 开始: {file_name}")
        self._log(f"[下载] 网盘路径: {file_path}")
        self._log(f"[下载] 保存到: {save_dir}")

        dlink = self.get_download_link(file_path)
        if not dlink:
            raise DownloadError(f"无法获取下载链接: {file_name}")

        # 断点续传
        downloaded = 0
        if os.path.exists(part_path):
            downloaded = os.path.getsize(part_path)
            self._log(f"[下载] 断点续传，已下载: {downloaded} 字节")

        bduss = self._bduss or self.session.cookies.get("BDUSS", "")
        download_headers = {
            "User-Agent": PCS_UA,
            "Cookie": f"BDUSS={bduss}",
            "Referer": "https://pan.baidu.com/disk/home",
        }
        if downloaded > 0:
            download_headers["Range"] = f"bytes={downloaded}-"

        try:
            self._log(f"[下载] 发起HTTP请求...")
            resp = requests.get(
                dlink,
                headers=download_headers,
                stream=True,
                timeout=60,
                allow_redirects=True
            )
            self._log(f"[下载] HTTP状态码: {resp.status_code}")

            if resp.status_code == 403:
                self._log("[下载] 收到403，重新获取链接后重试...")
                dlink = self.get_download_link(file_path)
                if not dlink:
                    raise DownloadError(f"下载链接获取失败（403）: {file_name}")
                resp = requests.get(
                    dlink,
                    headers=download_headers,
                    stream=True,
                    timeout=60,
                    allow_redirects=True
                )
                self._log(f"[下载] 重试后HTTP状态码: {resp.status_code}")

            if resp.status_code not in (200, 206):
                raise DownloadError(
                    f"下载失败，HTTP状态码: {resp.status_code} - {file_name}"
                )

            if downloaded > 0 and resp.status_code == 206:
                content_range = resp.headers.get("Content-Range", "")
                m = re.search(r"/(\d+)", content_range)
                total = int(m.group(1)) if m else 0
            else:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0

            self._log(f"[下载] 文件大小: {round(total/1024/1024, 1)} MB，开始写入...")
            os.makedirs(save_dir, exist_ok=True)

            start_time = time.time()
            last_time = start_time
            last_downloaded = downloaded

            mode = "ab" if downloaded > 0 else "wb"
            with open(part_path, mode) as f:
                for chunk in resp.iter_content(chunk_size=524288):  # 512KB
                    if stop_event and stop_event.is_set():
                        self._log(f"[下载] 已暂停: {file_name}")
                        return False

                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        now = time.time()
                        if now - last_time >= 1.0:
                            speed = (downloaded - last_downloaded) / (now - last_time)
                            progress = (downloaded / total * 100) if total > 0 else 0
                            if progress_callback:
                                progress_callback(progress, speed, downloaded, total)
                            last_time = now
                            last_downloaded = downloaded

            # 下载完成，重命名
            if os.path.exists(local_path):
                os.remove(local_path)
            os.rename(part_path, local_path)
            self._log(f"[下载] 完成: {file_name}")
            if progress_callback:
                progress_callback(100.0, 0, total, total)
            return True

        except DownloadError:
            raise
        except Exception as e:
            self._log(f"[下载] 下载异常: {e}")
            raise DownloadError(f"下载失败: {file_name} - {e}")
