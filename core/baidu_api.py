"""
百度网盘核心API模块
使用网页端Cookie模拟登录，无需开发者账号
"""
import os
import re
import json
import time
import pickle
import requests
import threading
from urllib.parse import quote, urlencode

# 百度网盘网页端常用接口
BAIDU_HOME = "https://pan.baidu.com/disk/home"
BAIDU_LIST_API = "https://pan.baidu.com/api/list"
BAIDU_FILEMETAS_API = "https://pan.baidu.com/api/filemetas"
BAIDU_DOWNLOAD_API = "https://pan.baidu.com/api/download"
BAIDU_QUOTA_API = "https://pan.baidu.com/api/quota"

# 模拟浏览器请求头（用于普通API请求）
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# 下载时必须使用的UA（百度服务器验证）
PAN_UA = "pan.baidu.com"

HEADERS = {
    "User-Agent": BROWSER_UA,
    "Referer": "https://pan.baidu.com/disk/home",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# 使用百度官方网页端的app_id
APP_ID = "250528"


class BaiduPanAPI:
    """百度网盘API封装类"""

    def __init__(self, session_file=None, log_callback=None):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.bdstoken = None
        self.uk = None
        self.username = None
        self.session_file = session_file or os.path.join(
            os.path.expanduser("~"), ".bdpan_session.pkl"
        )
        # 日志回调函数，用于向界面输出详细日志
        self._log = log_callback or (lambda msg: None)
        self._load_session()

    def set_log_callback(self, callback):
        """设置日志回调"""
        self._log = callback

    def _load_session(self):
        """从文件加载已保存的session"""
        try:
            if os.path.exists(self.session_file):
                with open(self.session_file, "rb") as f:
                    cookies = pickle.load(f)
                    self.session.cookies.update(cookies)
        except Exception:
            pass

    def _save_session(self):
        """保存session到文件"""
        try:
            save_dir = os.path.dirname(self.session_file)
            if save_dir:
                os.makedirs(save_dir, exist_ok=True)
            with open(self.session_file, "wb") as f:
                pickle.dump(dict(self.session.cookies), f)
        except Exception:
            pass

    def _extract_bdstoken(self, html):
        """从HTML中提取bdstoken"""
        patterns = [
            r'"bdstoken"\s*:\s*"([a-f0-9A-F]+)"',
            r'bdstoken\s*=\s*[\'"]([a-f0-9A-F]+)[\'"]',
            r'"bdstoken":"([a-f0-9A-F]+)"',
        ]
        for pat in patterns:
            match = re.search(pat, html)
            if match:
                return match.group(1)
        return None

    def _extract_uk(self, html):
        """从HTML中提取uk"""
        patterns = [
            r'"uk"\s*:\s*(\d+)',
            r'"uk":(\d+)',
        ]
        for pat in patterns:
            match = re.search(pat, html)
            if match:
                return match.group(1)
        return None

    def _refresh_bdstoken(self):
        """刷新bdstoken，确保下载接口可用"""
        try:
            resp = self.session.get(BAIDU_HOME, timeout=15)
            token = self._extract_bdstoken(resp.text)
            uk = self._extract_uk(resp.text)
            if token:
                self.bdstoken = token
                self._log(f"[API] bdstoken刷新成功: {token[:8]}...")
            if uk:
                self.uk = uk
            return token is not None
        except Exception as e:
            self._log(f"[API] bdstoken刷新失败: {e}")
            return False

    def check_login(self):
        """
        检查是否已登录，返回True/False
        """
        try:
            resp = self.session.get(
                BAIDU_HOME,
                timeout=15,
                allow_redirects=True
            )
            # 被重定向到登录页
            if "passport.baidu.com" in resp.url or "login" in resp.url.lower():
                self._log("[API] 检查登录：未登录（重定向到登录页）")
                return False
            # 检查响应内容是否包含登录标志
            if "bdstoken" in resp.text or '"uk"' in resp.text or "yunData" in resp.text:
                self.bdstoken = self._extract_bdstoken(resp.text)
                self.uk = self._extract_uk(resp.text)
                self._save_session()
                self._log(f"[API] 检查登录：已登录，bdstoken={'已获取' if self.bdstoken else '未获取'}")
                return True
        except Exception as e:
            self._log(f"[API] 检查登录异常: {e}")

        # 备用：调用quota接口
        try:
            resp = self.session.get(
                BAIDU_QUOTA_API,
                params={"checkfree": 1, "checkexpire": 1},
                timeout=10
            )
            data = resp.json()
            if data.get("errno") == 0:
                self._refresh_bdstoken()
                self._save_session()
                self._log("[API] 检查登录：已登录（quota接口验证）")
                return True
        except Exception as e:
            self._log(f"[API] quota接口异常: {e}")

        return False

    def get_user_info(self):
        """获取用户信息（用量等）"""
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
        """
        获取指定目录下的文件列表
        """
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
        """递归获取目录下所有文件（分页处理）"""
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
        获取文件的真实下载链接
        使用多种方法尝试，确保成功率
        """
        # 确保bdstoken存在
        if not self.bdstoken:
            self._log("[下载] bdstoken为空，尝试刷新...")
            self._refresh_bdstoken()

        self._log(f"[下载] 获取下载链接，fs_id={fs_id}, bdstoken={'有' if self.bdstoken else '无'}")

        # 方法1：使用 /api/filemetas 接口（POST）
        try:
            params = {
                "app_id": APP_ID,
                "bdstoken": self.bdstoken or "",
                "logid": "",
                "clienttype": 0,
                "web": 1,
                "channel": "chunlei",
            }
            post_data = {
                "fidlist": json.dumps([int(fs_id)]),
                "type": "dlink",
            }
            resp = self.session.post(
                BAIDU_FILEMETAS_API,
                params=params,
                data=post_data,
                timeout=15
            )
            result = resp.json()
            self._log(f"[下载] filemetas接口返回: errno={result.get('errno')}")
            if result.get("errno") == 0:
                info_list = result.get("info", [])
                if info_list:
                    dlink = info_list[0].get("dlink", "")
                    if dlink:
                        self._log(f"[下载] 方法1成功获取dlink: {dlink[:60]}...")
                        return dlink
        except Exception as e:
            self._log(f"[下载] 方法1异常: {e}")

        # 方法2：使用 /api/download 接口（GET）
        try:
            params = {
                "app_id": APP_ID,
                "bdstoken": self.bdstoken or "",
                "logid": "",
                "clienttype": 0,
                "web": 1,
                "fidlist": json.dumps([int(fs_id)]),
                "type": "dlink",
            }
            resp = self.session.get(
                BAIDU_DOWNLOAD_API,
                params=params,
                timeout=15
            )
            result = resp.json()
            self._log(f"[下载] download接口GET返回: errno={result.get('errno')}")
            if result.get("errno") == 0:
                dlink_list = result.get("dlink", [])
                if dlink_list:
                    dlink = dlink_list[0].get("dlink", "")
                    if dlink:
                        self._log(f"[下载] 方法2成功获取dlink: {dlink[:60]}...")
                        return dlink
        except Exception as e:
            self._log(f"[下载] 方法2异常: {e}")

        # 方法3：刷新bdstoken后重试方法1
        self._log("[下载] 前两种方法失败，刷新bdstoken后重试...")
        if self._refresh_bdstoken():
            try:
                params = {
                    "app_id": APP_ID,
                    "bdstoken": self.bdstoken or "",
                    "logid": "",
                    "clienttype": 0,
                    "web": 1,
                    "channel": "chunlei",
                }
                post_data = {
                    "fidlist": json.dumps([int(fs_id)]),
                    "type": "dlink",
                }
                resp = self.session.post(
                    BAIDU_FILEMETAS_API,
                    params=params,
                    data=post_data,
                    timeout=15
                )
                result = resp.json()
                self._log(f"[下载] 方法3返回: errno={result.get('errno')}")
                if result.get("errno") == 0:
                    info_list = result.get("info", [])
                    if info_list:
                        dlink = info_list[0].get("dlink", "")
                        if dlink:
                            self._log(f"[下载] 方法3成功获取dlink")
                            return dlink
            except Exception as e:
                self._log(f"[下载] 方法3异常: {e}")

        self._log("[下载] 所有方法均失败，无法获取下载链接")
        return None

    def download_file(self, fs_id, file_path, save_dir, progress_callback=None,
                      stop_event=None):
        """
        下载单个文件，支持断点续传
        :param fs_id: 文件fs_id
        :param file_path: 网盘中的文件路径（用于获取文件名）
        :param save_dir: 本地保存目录
        :param progress_callback: 进度回调函数 callback(downloaded, total, speed)
        :param stop_event: threading.Event，用于停止下载
        :return: True/False
        """
        file_name = os.path.basename(file_path)
        local_path = os.path.join(save_dir, file_name)
        part_path = local_path + ".bdpart"

        self._log(f"[下载] 开始下载: {file_name}")
        self._log(f"[下载] fs_id={fs_id}, 保存到: {save_dir}")

        # 获取下载链接
        dlink = self.get_download_link(fs_id)
        if not dlink:
            raise APIError(f"无法获取下载链接: {file_path}")

        # 检查已下载大小（断点续传）
        downloaded = 0
        if os.path.exists(part_path):
            downloaded = os.path.getsize(part_path)
            self._log(f"[下载] 断点续传，已下载: {downloaded} 字节")

        # 下载时必须使用 pan.baidu.com 作为 User-Agent，否则会被拒绝
        download_headers = {
            "User-Agent": PAN_UA,
            "Referer": "https://pan.baidu.com/disk/home",
        }
        if downloaded > 0:
            download_headers["Range"] = f"bytes={downloaded}-"

        try:
            # 创建一个新的session用于下载，保持cookie但使用pan UA
            dl_session = requests.Session()
            dl_session.cookies.update(dict(self.session.cookies))

            self._log(f"[下载] 发起HTTP请求，UA=pan.baidu.com")
            resp = dl_session.get(
                dlink,
                headers=download_headers,
                stream=True,
                timeout=60,
                allow_redirects=True
            )
            self._log(f"[下载] HTTP响应状态码: {resp.status_code}")

            # 如果返回403，尝试刷新下载链接重试一次
            if resp.status_code == 403:
                self._log("[下载] 收到403，刷新链接后重试...")
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

            # 获取文件总大小
            if downloaded > 0 and resp.status_code == 206:
                content_range = resp.headers.get("Content-Range", "")
                match = re.search(r"/(\d+)", content_range)
                total = int(match.group(1)) if match else 0
            else:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0  # 重新下载

            total_mb = round(total / 1024 / 1024, 1)
            self._log(f"[下载] 文件大小: {total_mb} MB，开始写入...")

            os.makedirs(save_dir, exist_ok=True)

            start_time = time.time()
            last_time = start_time
            last_downloaded = downloaded

            mode = "ab" if downloaded > 0 else "wb"
            with open(part_path, mode) as f:
                for chunk in resp.iter_content(chunk_size=524288):  # 512KB chunks
                    if stop_event and stop_event.is_set():
                        self._log(f"[下载] 用户停止下载: {file_name}")
                        return False
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        # 计算速度和进度（每0.5秒更新一次）
                        now = time.time()
                        if now - last_time >= 0.5:
                            speed = (downloaded - last_downloaded) / (now - last_time)
                            last_time = now
                            last_downloaded = downloaded
                            if progress_callback:
                                progress_callback(downloaded, total, speed)

            # 下载完成，重命名
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
        # 重新获取bdstoken和uk
        try:
            resp = self.session.get(BAIDU_HOME, timeout=15)
            self.bdstoken = self._extract_bdstoken(resp.text)
            self.uk = self._extract_uk(resp.text)
            self._log(f"[API] Cookie更新，bdstoken={'已获取' if self.bdstoken else '未获取'}")
        except Exception as e:
            self._log(f"[API] Cookie更新后获取bdstoken失败: {e}")


class LoginExpiredError(Exception):
    pass


class APIError(Exception):
    pass


class DownloadError(Exception):
    pass
