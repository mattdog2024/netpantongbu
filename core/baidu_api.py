"""
百度网盘核心API模块
使用网页端Cookie模拟登录，无需开发者账号

关键说明：
  pan.baidu.com/api/download 接口需要 sign + timestamp 两个动态参数，
  这两个参数必须从百度网盘主页 HTML 里实时提取，不能写死。
  sign 的计算方式是 JS 加密，需要用 Python 复现。
"""
import os
import re
import json
import time
import base64
import pickle
import requests
import threading
from urllib.parse import quote

# 百度网盘网页端常用接口
BAIDU_HOME = "https://pan.baidu.com/disk/home"
BAIDU_LIST_API = "https://pan.baidu.com/api/list"
BAIDU_DOWNLOAD_API = "https://pan.baidu.com/api/download"
BAIDU_QUOTA_API = "https://pan.baidu.com/api/quota"

# 模拟浏览器请求头
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# 下载时使用的 User-Agent（百度服务器验证）
PAN_UA = "pan.baidu.com"

HEADERS = {
    "User-Agent": BROWSER_UA,
    "Referer": "https://pan.baidu.com/disk/home",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

APP_ID = "250528"


def _calc_sign(sign3, sign1):
    """
    复现百度网盘主页的 JS sign2 函数
    用于计算下载接口所需的 sign 参数
    """
    a = []
    p = []
    o = []
    v = len(sign3)

    for q in range(256):
        p.append(ord(sign3[q % v]))
        a.append(q)

    u = 0
    for q in range(256):
        u = (u + a[q] + p[q]) % 256
        a[q], a[u] = a[u], a[q]

    i = 0
    u = 0
    for q in range(len(sign1)):
        i = (i + 1) % 256
        u = (u + a[i]) % 256
        a[i], a[u] = a[u], a[i]
        o.append(chr(ord(sign1[q]) ^ a[(a[i] + a[u]) % 256]))

    return base64.b64encode("".join(o).encode("latin-1")).decode("utf-8")


class BaiduPanAPI:
    """百度网盘API封装类"""

    def __init__(self, session_file=None, log_callback=None):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.bdstoken = None
        self.uk = None
        self.username = None
        self._dsign = None
        self._timestamp = None
        self._sign_expire = 0  # sign 缓存过期时间（秒级时间戳）
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

    def _refresh_home(self):
        """
        访问网盘主页，提取 bdstoken / uk / sign1 / sign3 / timestamp
        sign 有效期约 10 分钟，缓存复用
        """
        try:
            resp = self.session.get(BAIDU_HOME, timeout=20)
            html = resp.text

            token = self._extract_bdstoken(html)
            uk = self._extract_uk(html)
            if token:
                self.bdstoken = token
            if uk:
                self.uk = uk

            # 提取 sign1 / sign3 / timestamp
            sign1_m = re.search(r'"sign1"\s*:\s*"([^"]+)"', html)
            sign3_m = re.search(r'"sign3"\s*:\s*"([^"]+)"', html)
            ts_m = re.search(r'"timestamp"\s*:\s*(\d+)', html)

            if sign1_m and sign3_m and ts_m:
                sign1 = sign1_m.group(1)
                sign3 = sign3_m.group(1)
                ts = ts_m.group(1)
                self._dsign = _calc_sign(sign3, sign1)
                self._timestamp = ts
                self._sign_expire = time.time() + 540  # 9分钟后过期
                self._log(f"[API] sign刷新成功，timestamp={ts}")
                return True
            else:
                self._log("[API] 主页中未找到sign1/sign3/timestamp，尝试备用提取")
                # 备用：yunData 格式
                m = re.search(r'yunData\.setData\((\{.+?\})\)', html, re.DOTALL)
                if m:
                    try:
                        data = json.loads(m.group(1))
                        sign1 = data.get("sign1", "")
                        sign3 = data.get("sign3", "")
                        ts = str(data.get("timestamp", ""))
                        if sign1 and sign3 and ts:
                            self._dsign = _calc_sign(sign3, sign1)
                            self._timestamp = ts
                            self._sign_expire = time.time() + 540
                            self._log(f"[API] sign备用提取成功，timestamp={ts}")
                            return True
                    except Exception as e:
                        self._log(f"[API] yunData解析失败: {e}")

                self._log("[API] 无法提取sign，下载接口可能失败")
                return token is not None

        except Exception as e:
            self._log(f"[API] 刷新主页失败: {e}")
            return False

    def _ensure_sign(self):
        """确保 sign 和 timestamp 是有效的（过期则刷新）"""
        if not self._dsign or time.time() > self._sign_expire:
            self._log("[API] sign已过期或不存在，重新获取...")
            self._refresh_home()

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
                # 同时提取 sign
                self._refresh_home()
                self._save_session()
                self._log(f"[API] 已登录，bdstoken={'已获取' if self.bdstoken else '未获取'}")
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
            "app_id": APP_ID,
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

    def get_download_link(self, fs_id):
        """
        获取文件真实下载链接（dlink）
        必须使用 sign + timestamp 参数，这两个参数从主页动态提取
        """
        self._ensure_sign()

        if not self._dsign or not self._timestamp:
            self._log("[下载] 无法获取sign/timestamp，下载链接获取失败")
            return None

        self._log(f"[下载] 获取下载链接，fs_id={fs_id}")
        self._log(f"[下载] sign={self._dsign[:20]}..., timestamp={self._timestamp}")

        params = {
            "sign": self._dsign,
            "timestamp": self._timestamp,
            "fidlist": json.dumps([int(fs_id)]),
            "type": "dlink",
            "app_id": APP_ID,
            "web": 1,
            "channel": "chunlei",
            "clienttype": 0,
        }

        try:
            resp = self.session.get(BAIDU_DOWNLOAD_API, params=params, timeout=15)
            result = resp.json()
            errno = result.get("errno", -1)
            self._log(f"[下载] download接口返回: errno={errno}")

            if errno == 0:
                dlink_list = result.get("dlink", [])
                if dlink_list:
                    dlink = dlink_list[0].get("dlink", "")
                    if dlink:
                        self._log(f"[下载] 成功获取dlink: {dlink[:80]}...")
                        return dlink
                self._log(f"[下载] errno=0但dlink为空，完整返回: {result}")
                return None

            elif errno == 2:
                self._log("[下载] errno=2（参数错误），强制刷新sign后重试...")
                self._sign_expire = 0  # 强制过期
                self._ensure_sign()
                if self._dsign and self._timestamp:
                    params["sign"] = self._dsign
                    params["timestamp"] = self._timestamp
                    resp2 = self.session.get(BAIDU_DOWNLOAD_API, params=params, timeout=15)
                    result2 = resp2.json()
                    self._log(f"[下载] 重试返回: errno={result2.get('errno')}")
                    if result2.get("errno") == 0:
                        dlink_list = result2.get("dlink", [])
                        if dlink_list:
                            dlink = dlink_list[0].get("dlink", "")
                            if dlink:
                                self._log(f"[下载] 重试成功获取dlink")
                                return dlink
                return None

            elif errno == -6:
                raise LoginExpiredError("登录已过期，请重新登录")

            else:
                self._log(f"[下载] 未知错误，errno={errno}，完整返回: {result}")
                return None

        except LoginExpiredError:
            raise
        except Exception as e:
            self._log(f"[下载] 获取下载链接异常: {e}")
            return None

    def download_file(self, fs_id, file_path, save_dir, progress_callback=None,
                      stop_event=None):
        """
        下载单个文件，支持断点续传
        """
        file_name = os.path.basename(file_path)
        local_path = os.path.join(save_dir, file_name)
        part_path = local_path + ".bdpart"

        self._log(f"[下载] 开始: {file_name}")
        self._log(f"[下载] fs_id={fs_id}, 保存到: {save_dir}")

        dlink = self.get_download_link(fs_id)
        if not dlink:
            raise APIError(f"无法获取下载链接: {file_path}")

        # 断点续传
        downloaded = 0
        if os.path.exists(part_path):
            downloaded = os.path.getsize(part_path)
            self._log(f"[下载] 断点续传，已下载: {downloaded} 字节")

        download_headers = {
            "User-Agent": PAN_UA,
            "Referer": "https://pan.baidu.com/disk/home",
        }
        if downloaded > 0:
            download_headers["Range"] = f"bytes={downloaded}-"

        try:
            dl_session = requests.Session()
            dl_session.cookies.update(dict(self.session.cookies))

            self._log(f"[下载] 发起HTTP请求...")
            resp = dl_session.get(
                dlink,
                headers=download_headers,
                stream=True,
                timeout=60,
                allow_redirects=True
            )
            self._log(f"[下载] HTTP状态码: {resp.status_code}")

            if resp.status_code == 403:
                self._log("[下载] 收到403，刷新链接后重试...")
                self._sign_expire = 0
                dlink = self.get_download_link(fs_id)
                if not dlink:
                    raise DownloadError(f"下载链接获取失败（403）: {file_name}")
                resp = dl_session.get(
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
                for chunk in resp.iter_content(chunk_size=524288):
                    if stop_event and stop_event.is_set():
                        self._log(f"[下载] 用户停止: {file_name}")
                        return False
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        now = time.time()
                        if now - last_time >= 0.5:
                            speed = (downloaded - last_downloaded) / (now - last_time)
                            last_time = now
                            last_downloaded = downloaded
                            if progress_callback:
                                progress_callback(downloaded, total, speed)

            if os.path.exists(local_path):
                os.remove(local_path)
            os.rename(part_path, local_path)

            if progress_callback:
                progress_callback(total, total, 0)

            self._log(f"[下载] 完成: {file_name}")
            return True

        except DownloadError:
            raise
        except Exception as e:
            raise DownloadError(f"下载失败 {file_name}: {e}")

    def update_cookies_from_browser(self, cookies_dict):
        """从外部设置Cookie（用于登录后更新）"""
        self.session.cookies.update(cookies_dict)
        self._save_session()
        try:
            self._refresh_home()
            self._log(f"[API] Cookie更新，bdstoken={'已获取' if self.bdstoken else '未获取'}")
        except Exception as e:
            self._log(f"[API] Cookie更新后刷新主页失败: {e}")


class LoginExpiredError(Exception):
    pass


class APIError(Exception):
    pass


class DownloadError(Exception):
    pass
