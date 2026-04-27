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
from urllib.parse import quote

# 百度网盘网页端常用接口
BAIDU_HOME = "https://pan.baidu.com/disk/home"
BAIDU_LIST_API = "https://pan.baidu.com/api/list"
BAIDU_FILEMETAS_API = "https://pan.baidu.com/api/filemetas"
BAIDU_DOWNLOAD_API = "https://pan.baidu.com/api/download"
BAIDU_QUOTA_API = "https://pan.baidu.com/api/quota"

# 模拟浏览器请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://pan.baidu.com/disk/home",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# app_id: 使用百度官方网页端的app_id，无需开发者申请
APP_ID = "250528"


class BaiduPanAPI:
    """百度网盘API封装类"""

    def __init__(self, session_file=None):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.bdstoken = None
        self.uk = None
        self.session_file = session_file or os.path.join(
            os.path.expanduser("~"), ".bdpan_session.pkl"
        )
        self._load_session()

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
            os.makedirs(os.path.dirname(self.session_file), exist_ok=True)
            with open(self.session_file, "wb") as f:
                pickle.dump(dict(self.session.cookies), f)
        except Exception:
            pass

    def _get_bdstoken(self):
        """从网盘主页提取bdstoken"""
        try:
            resp = self.session.get(BAIDU_HOME, timeout=15)
            match = re.search(r'"bdstoken"\s*:\s*"([a-f0-9]+)"', resp.text)
            if match:
                return match.group(1)
            # 备用方式
            match = re.search(r"bdstoken\s*=\s*['\"]([a-f0-9]+)['\"]", resp.text)
            if match:
                return match.group(1)
        except Exception:
            pass
        return None

    def _get_uk(self):
        """获取用户uk（用户唯一标识）"""
        try:
            resp = self.session.get(BAIDU_HOME, timeout=15)
            match = re.search(r'"uk"\s*:\s*(\d+)', resp.text)
            if match:
                return match.group(1)
        except Exception:
            pass
        return None

    def check_login(self):
        """检查是否已登录，返回True/False"""
        try:
            resp = self.session.get(BAIDU_QUOTA_API, timeout=10)
            data = resp.json()
            if data.get("errno") == 0:
                self.bdstoken = self._get_bdstoken()
                self.uk = self._get_uk()
                return True
        except Exception:
            pass
        return False

    def get_user_info(self):
        """获取用户信息（用量等）"""
        try:
            resp = self.session.get(BAIDU_QUOTA_API, timeout=10)
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
        :param path: 网盘路径，如 "/" 或 "/我的文档"
        :param order: 排序方式 name/time/size
        :param desc: 是否降序 0/1
        :param page: 页码
        :param num: 每页数量
        :return: 文件列表 list[dict]
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
                # 登录过期
                raise LoginExpiredError("登录已过期，请重新登录")
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
        :param fs_id: 文件的fs_id
        :return: 下载链接字符串
        """
        params = {
            "app_id": APP_ID,
            "bdstoken": self.bdstoken or "",
            "logid": "",
            "clienttype": 0,
        }
        data = {
            "fidlist": json.dumps([int(fs_id)]),
            "type": "dlink",
        }
        try:
            resp = self.session.post(
                BAIDU_FILEMETAS_API, params=params, data=data, timeout=15
            )
            result = resp.json()
            if result.get("errno") == 0:
                info_list = result.get("info", [])
                if info_list:
                    dlink = info_list[0].get("dlink", "")
                    if dlink:
                        # 跟随重定向获取真实下载链接
                        head_resp = self.session.head(
                            dlink,
                            headers={"User-Agent": "pan.baidu.com"},
                            allow_redirects=True,
                            timeout=10,
                        )
                        return head_resp.url
                        
        except Exception as e:
            raise APIError(f"获取下载链接失败: {e}")
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

        # 获取下载链接
        dlink = self.get_download_link(fs_id)
        if not dlink:
            raise APIError(f"无法获取下载链接: {file_path}")

        # 检查已下载大小（断点续传）
        downloaded = 0
        if os.path.exists(part_path):
            downloaded = os.path.getsize(part_path)

        headers = {"User-Agent": "pan.baidu.com"}
        if downloaded > 0:
            headers["Range"] = f"bytes={downloaded}-"

        try:
            resp = self.session.get(
                dlink, headers=headers, stream=True, timeout=30
            )

            # 获取文件总大小
            if downloaded > 0 and resp.status_code == 206:
                content_range = resp.headers.get("Content-Range", "")
                match = re.search(r"/(\d+)", content_range)
                total = int(match.group(1)) if match else 0
            else:
                total = int(resp.headers.get("Content-Length", 0))

            os.makedirs(save_dir, exist_ok=True)

            start_time = time.time()
            last_time = start_time
            last_downloaded = downloaded

            with open(part_path, "ab") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if stop_event and stop_event.is_set():
                        return False
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        # 计算速度和进度
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

            return True

        except Exception as e:
            raise DownloadError(f"下载失败 {file_name}: {e}")

    def update_cookies_from_browser(self, cookies_dict):
        """从外部设置Cookie（用于登录后更新）"""
        self.session.cookies.update(cookies_dict)
        self._save_session()
        self.bdstoken = self._get_bdstoken()
        self.uk = self._get_uk()


class LoginExpiredError(Exception):
    pass


class APIError(Exception):
    pass


class DownloadError(Exception):
    pass
