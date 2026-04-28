"""
下载任务管理器
管理下载队列、定时任务、断点续传
"""
import os
import json
import time
import threading
import datetime
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Callable
from PyQt5.QtCore import QObject, pyqtSignal, QTimer


class TaskStatus(Enum):
    PENDING = "等待中"
    RUNNING = "下载中"
    PAUSED = "已暂停"
    COMPLETED = "已完成"
    FAILED = "失败"
    SCHEDULED = "定时等待"
    STOPPED = "已停止"


@dataclass
class DownloadTask:
    """单个下载任务"""
    task_id: str
    pan_path: str           # 网盘路径
    fs_id: int              # 文件的fs_id
    file_name: str          # 文件名
    file_size: int          # 文件大小（字节）
    save_dir: str           # 本地保存目录
    status: str = TaskStatus.PENDING.value
    progress: float = 0.0   # 0.0 ~ 1.0
    downloaded: int = 0     # 已下载字节数
    speed: float = 0.0      # 当前速度 bytes/s
    error_msg: str = ""
    created_at: str = ""
    finished_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class ScheduleConfig:
    """定时配置"""
    enabled: bool = False
    start_hour: int = 21    # 开始小时（21 = 晚上9点）
    start_minute: int = 0
    stop_hour: int = 6      # 停止小时（6 = 早上6点）
    stop_minute: int = 0
    repeat_daily: bool = True


class DownloadManager(QObject):
    """下载任务管理器"""

    # Qt信号
    task_updated = pyqtSignal(str, dict)    # task_id, task_info
    task_added = pyqtSignal(str, dict)      # task_id, task_info
    all_tasks_updated = pyqtSignal(list)    # 所有任务列表
    log_message = pyqtSignal(str)           # 简短状态消息（状态栏用）
    detail_log = pyqtSignal(str)            # 详细日志（日志面板用）
    schedule_status_changed = pyqtSignal(str)  # 定时状态变化

    def __init__(self, api, config_file=None):
        super().__init__()
        self.api = api
        self.tasks: List[DownloadTask] = []
        self.schedule_config = ScheduleConfig()
        self.config_file = config_file or os.path.join(
            os.path.expanduser("~"), ".bdpan_tasks.json"
        )
        self._stop_event = threading.Event()
        self._download_thread = None
        self._schedule_timer = None
        self._is_in_schedule_window = False
        self._load_tasks()
        self._start_schedule_checker()

        # 把API的日志回调接入到detail_log信号
        self.api.set_log_callback(self._api_log)

    def _api_log(self, msg: str):
        """接收API层的日志并转发到detail_log信号"""
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.detail_log.emit(f"[{ts}] {msg}")

    def _log(self, msg: str, detail: str = None):
        """发出日志信号"""
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_message.emit(msg)
        self.detail_log.emit(f"[{ts}] {msg}")
        if detail:
            self.detail_log.emit(f"[{ts}]   {detail}")

    # ==================== 任务管理 ====================

    def add_task(self, pan_path: str, fs_id: int, file_name: str,
                 file_size: int, save_dir: str) -> str:
        """添加下载任务"""
        task_id = f"task_{int(time.time() * 1000)}_{len(self.tasks)}"
        task = DownloadTask(
            task_id=task_id,
            pan_path=pan_path,
            fs_id=fs_id,
            file_name=file_name,
            file_size=file_size,
            save_dir=save_dir,
        )
        self.tasks.append(task)
        self._save_tasks()
        self.task_added.emit(task_id, self._task_to_dict(task))
        self._log(f"已添加任务: {file_name}")
        return task_id

    def add_folder_tasks(self, folder_info_list: list, save_dir: str) -> List[str]:
        """批量添加文件夹中的所有文件任务"""
        task_ids = []
        for info in folder_info_list:
            if not info.get("isdir"):
                tid = self.add_task(
                    pan_path=info["path"],
                    fs_id=info["fs_id"],
                    file_name=info["server_filename"],
                    file_size=info.get("size", 0),
                    save_dir=save_dir,
                )
                task_ids.append(tid)
        return task_ids

    def remove_task(self, task_id: str):
        """删除任务"""
        self.tasks = [t for t in self.tasks if t.task_id != task_id]
        self._save_tasks()
        self.all_tasks_updated.emit(self._all_tasks_dict())

    def clear_completed(self):
        """清除已完成的任务"""
        self.tasks = [t for t in self.tasks
                      if t.status != TaskStatus.COMPLETED.value]
        self._save_tasks()
        self.all_tasks_updated.emit(self._all_tasks_dict())

    def retry_failed(self):
        """将所有失败的任务重置为等待中，以便重新下载"""
        count = 0
        for task in self.tasks:
            if task.status == TaskStatus.FAILED.value:
                task.status = TaskStatus.PENDING.value
                task.error_msg = ""
                count += 1
                self.task_updated.emit(task.task_id, self._task_to_dict(task))
        if count > 0:
            self._save_tasks()
            self._log(f"已重置 {count} 个失败任务为等待中")
        return count

    def start_download(self):
        """开始下载队列中的任务"""
        if self._download_thread and self._download_thread.is_alive():
            self._log("下载线程已在运行中")
            return

        # 检查是否有可下载的任务（PENDING 或 PAUSED）
        pending = [t for t in self.tasks
                   if t.status in (TaskStatus.PENDING.value, TaskStatus.PAUSED.value)]
        if not pending:
            self._log('没有待下载的任务（提示：失败的任务请点「重试失败」按钮）')
            return

        self._stop_event.clear()
        self._download_thread = threading.Thread(
            target=self._download_worker, daemon=True
        )
        self._download_thread.start()
        self._log(f"开始下载，共 {len(pending)} 个任务...")

    def stop_download(self):
        """停止下载"""
        self._stop_event.set()
        self._log("正在停止下载...")
        # 将运行中的任务标记为暂停
        for task in self.tasks:
            if task.status == TaskStatus.RUNNING.value:
                task.status = TaskStatus.PAUSED.value
                self.task_updated.emit(task.task_id, self._task_to_dict(task))
        self._save_tasks()

    def _download_worker(self):
        """下载工作线程"""
        while not self._stop_event.is_set():
            # 找到下一个待下载的任务（PENDING 或 PAUSED）
            pending_tasks = [
                t for t in self.tasks
                if t.status in (TaskStatus.PENDING.value, TaskStatus.PAUSED.value)
            ]
            if not pending_tasks:
                break

            task = pending_tasks[0]
            task.status = TaskStatus.RUNNING.value
            self.task_updated.emit(task.task_id, self._task_to_dict(task))
            self._log(f"正在下载: {task.file_name}")

            try:
                def progress_cb(downloaded, total, speed):
                    task.downloaded = downloaded
                    task.speed = speed
                    if total > 0:
                        task.progress = downloaded / total
                    self.task_updated.emit(task.task_id, self._task_to_dict(task))

                success = self.api.download_file(
                    fs_id=task.fs_id,
                    file_path=task.pan_path,
                    save_dir=task.save_dir,
                    progress_callback=progress_cb,
                    stop_event=self._stop_event,
                )

                if success:
                    task.status = TaskStatus.COMPLETED.value
                    task.progress = 1.0
                    task.finished_at = datetime.datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    self._log(f"下载完成: {task.file_name}")
                else:
                    task.status = TaskStatus.PAUSED.value
                    self._log(f"下载暂停: {task.file_name}")

            except Exception as e:
                task.status = TaskStatus.FAILED.value
                task.error_msg = str(e)
                self._log(f"下载失败: {task.file_name}", str(e))

            self.task_updated.emit(task.task_id, self._task_to_dict(task))
            self._save_tasks()

        self._log("下载队列处理完毕")

    # ==================== 定时管理 ====================

    def update_schedule(self, config: ScheduleConfig):
        """更新定时配置"""
        self.schedule_config = config
        self._save_tasks()
        status = self._get_schedule_status_text()
        self.schedule_status_changed.emit(status)
        self._log(f"定时设置已更新: {status}")

    def _start_schedule_checker(self):
        """启动定时检查器（每分钟检查一次）"""
        self._schedule_timer = QTimer()
        self._schedule_timer.timeout.connect(self._check_schedule)
        self._schedule_timer.start(60000)  # 每60秒检查一次
        # 立即检查一次
        QTimer.singleShot(3000, self._check_schedule)

    def _check_schedule(self):
        """检查是否到了定时下载时间"""
        if not self.schedule_config.enabled:
            return

        now = datetime.datetime.now()
        current_minutes = now.hour * 60 + now.minute
        start_minutes = (self.schedule_config.start_hour * 60 +
                         self.schedule_config.start_minute)
        stop_minutes = (self.schedule_config.stop_hour * 60 +
                        self.schedule_config.stop_minute)

        # 判断是否在下载时间窗口内
        # 跨天情况：比如21:00 ~ 06:00
        if start_minutes > stop_minutes:
            in_window = (current_minutes >= start_minutes or
                         current_minutes < stop_minutes)
        else:
            in_window = start_minutes <= current_minutes < stop_minutes

        if in_window and not self._is_in_schedule_window:
            # 进入时间窗口，先把失败的任务重置，再开始下载
            self._is_in_schedule_window = True
            self._log(
                f"定时下载开始 ({self.schedule_config.start_hour:02d}:"
                f"{self.schedule_config.start_minute:02d})"
            )
            self.schedule_status_changed.emit("定时下载进行中...")
            # 将失败的任务重置为等待中，确保定时能重新下载
            self.retry_failed()
            self.start_download()

        elif not in_window and self._is_in_schedule_window:
            # 离开时间窗口，停止下载
            self._is_in_schedule_window = False
            self._log(
                f"定时下载停止 ({self.schedule_config.stop_hour:02d}:"
                f"{self.schedule_config.stop_minute:02d})"
            )
            self.schedule_status_changed.emit(self._get_schedule_status_text())
            self.stop_download()

    def _get_schedule_status_text(self):
        """获取定时状态描述文字"""
        if not self.schedule_config.enabled:
            return "定时下载：未启用"
        cfg = self.schedule_config
        return (f"定时下载：每天 {cfg.start_hour:02d}:{cfg.start_minute:02d} ~ "
                f"{cfg.stop_hour:02d}:{cfg.stop_minute:02d}")

    # ==================== 数据持久化 ====================

    def _task_to_dict(self, task: DownloadTask) -> dict:
        return asdict(task)

    def _all_tasks_dict(self) -> list:
        return [self._task_to_dict(t) for t in self.tasks]

    def _save_tasks(self):
        """保存任务列表和配置到文件"""
        try:
            data = {
                "tasks": self._all_tasks_dict(),
                "schedule": {
                    "enabled": self.schedule_config.enabled,
                    "start_hour": self.schedule_config.start_hour,
                    "start_minute": self.schedule_config.start_minute,
                    "stop_hour": self.schedule_config.stop_hour,
                    "stop_minute": self.schedule_config.stop_minute,
                    "repeat_daily": self.schedule_config.repeat_daily,
                },
            }
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_tasks(self):
        """从文件加载任务列表和配置"""
        try:
            if not os.path.exists(self.config_file):
                return
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 加载任务（跳过已完成的，保留未完成的）
            for t_dict in data.get("tasks", []):
                if t_dict.get("status") != TaskStatus.COMPLETED.value:
                    # 将运行中的任务重置为暂停
                    if t_dict.get("status") == TaskStatus.RUNNING.value:
                        t_dict["status"] = TaskStatus.PAUSED.value
                    task = DownloadTask(**t_dict)
                    self.tasks.append(task)

            # 加载定时配置
            sch = data.get("schedule", {})
            if sch:
                self.schedule_config = ScheduleConfig(
                    enabled=sch.get("enabled", False),
                    start_hour=sch.get("start_hour", 21),
                    start_minute=sch.get("start_minute", 0),
                    stop_hour=sch.get("stop_hour", 6),
                    stop_minute=sch.get("stop_minute", 0),
                    repeat_daily=sch.get("repeat_daily", True),
                )
        except Exception:
            pass

    def get_schedule_status(self) -> str:
        return self._get_schedule_status_text()
