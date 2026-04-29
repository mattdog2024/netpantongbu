"""
文件浏览器组件 - 浏览百度网盘目录，选择要下载的文件
"""
import os
import json
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTreeWidget, QTreeWidgetItem, QLineEdit,
    QFileDialog, QMessageBox, QProgressBar, QFrame,
    QSizePolicy, QAbstractItemView
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QIcon, QColor, QFont


def format_size(size_bytes: int) -> str:
    """格式化文件大小"""
    if size_bytes == 0:
        return "-"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


class LoadFilesThread(QThread):
    """后台加载文件列表的线程"""
    files_loaded = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, api, path):
        super().__init__()
        self.api = api
        self.path = path

    def run(self):
        try:
            files = self.api.list_files(self.path, num=200)
            self.files_loaded.emit(files)
        except Exception as e:
            self.error_occurred.emit(str(e))


class FileBrowserWidget(QWidget):
    """文件浏览器"""

    def __init__(self, api, manager, parent=None):
        super().__init__(parent)
        self.api = api
        self.manager = manager
        self._logged_in = False
        self._current_path = "/"
        self._path_history = ["/"]
        self._load_thread = None
        self._config_file = os.path.join(
            os.path.expanduser("~"), ".bdpan_ui.json"
        )
        self._save_dir = self._load_save_dir()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ---- 顶部工具栏 ----
        toolbar = QFrame()
        toolbar.setStyleSheet(
            "QFrame { background: #f8f9fc; border-bottom: 1px solid #e5e7eb; "
            "border-radius: 0px; }"
        )
        toolbar.setFixedHeight(46)
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(10, 0, 10, 0)
        tb_layout.setSpacing(6)

        # 返回按钮
        self.back_btn = QPushButton("←")
        self.back_btn.setFixedSize(32, 28)
        self.back_btn.setToolTip("返回上级目录")
        self.back_btn.clicked.connect(self._go_back)
        self.back_btn.setEnabled(False)
        tb_layout.addWidget(self.back_btn)

        # 刷新按钮
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setFixedHeight(28)
        self.refresh_btn.setToolTip("刷新当前目录")
        self.refresh_btn.clicked.connect(self._refresh)
        tb_layout.addWidget(self.refresh_btn)

        # 路径显示
        self.path_label = QLabel("/")
        self.path_label.setStyleSheet(
            "color: #2563eb; font-size: 12px; padding: 0 6px;"
        )
        self.path_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb_layout.addWidget(self.path_label)

        # 全选/取消全选
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.setFixedHeight(28)
        self.select_all_btn.clicked.connect(self._select_all)
        tb_layout.addWidget(self.select_all_btn)

        layout.addWidget(toolbar)

        # ---- 文件树 ----
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["文件名", "大小", "修改时间"])
        self.tree.setColumnWidth(0, 320)
        self.tree.setColumnWidth(1, 90)
        self.tree.setColumnWidth(2, 140)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.setStyleSheet(
            "QTreeWidget { border: none; background: white; }"
            "QTreeWidget::item { height: 28px; padding: 2px; }"
            "QTreeWidget::item:selected { background: #dbeafe; color: #1e40af; }"
            "QTreeWidget::item:hover { background: #f0f4ff; }"
            "QHeaderView::section { background: #f3f4f6; border: none; "
            "border-bottom: 1px solid #e5e7eb; padding: 5px 8px; "
            "font-weight: bold; color: #374151; }"
        )
        layout.addWidget(self.tree)

        # ---- 加载进度条 ----
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setRange(0, 0)  # 无限循环模式
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet(
            "QProgressBar { border: none; background: #e5e7eb; }"
            "QProgressBar::chunk { background: #2563eb; }"
        )
        layout.addWidget(self.progress_bar)

        # ---- 底部操作栏 ----
        bottom_bar = QFrame()
        bottom_bar.setStyleSheet(
            "QFrame { background: #f8f9fc; border-top: 1px solid #e5e7eb; }"
        )
        bottom_bar.setFixedHeight(52)
        bot_layout = QHBoxLayout(bottom_bar)
        bot_layout.setContentsMargins(10, 0, 10, 0)
        bot_layout.setSpacing(8)

        # 保存目录选择
        bot_layout.addWidget(QLabel("保存到:"))
        self.save_dir_edit = QLineEdit(self._save_dir)
        self.save_dir_edit.setReadOnly(True)
        self.save_dir_edit.setStyleSheet(
            "QLineEdit { border: 1px solid #d1d5db; border-radius: 4px; "
            "padding: 3px 6px; background: white; color: #374151; }"
        )
        bot_layout.addWidget(self.save_dir_edit)

        browse_btn = QPushButton("浏览...")
        browse_btn.setFixedHeight(28)
        browse_btn.clicked.connect(self._browse_save_dir)
        bot_layout.addWidget(browse_btn)

        bot_layout.addStretch()

        # 添加到下载队列按钮
        self.add_btn = QPushButton("添加到下载队列")
        self.add_btn.setObjectName("primaryBtn")
        self.add_btn.setFixedHeight(34)
        self.add_btn.setMinimumWidth(130)
        self.add_btn.clicked.connect(self._add_to_queue)
        bot_layout.addWidget(self.add_btn)

        layout.addWidget(bottom_bar)

        # 未登录提示
        self._show_not_logged_in()

    def _show_not_logged_in(self):
        """显示未登录提示"""
        self.tree.clear()
        item = QTreeWidgetItem(["请先登录百度账号", "", ""])
        item.setForeground(0, QColor("#9ca3af"))
        item.setTextAlignment(0, Qt.AlignCenter)
        self.tree.addTopLevelItem(item)

    def set_logged_in(self, logged_in: bool):
        self._logged_in = logged_in
        if logged_in:
            self._load_directory("/")
        else:
            self._show_not_logged_in()

    def _load_directory(self, path: str):
        """加载指定目录"""
        if not self._logged_in:
            return
        self._current_path = path
        self.path_label.setText(path)
        self.back_btn.setEnabled(path != "/")
        self.tree.clear()
        self.progress_bar.setVisible(True)

        self._load_thread = LoadFilesThread(self.api, path)
        self._load_thread.files_loaded.connect(self._on_files_loaded)
        self._load_thread.error_occurred.connect(self._on_load_error)
        self._load_thread.start()

    def _on_files_loaded(self, files: list):
        """文件加载完成"""
        self.progress_bar.setVisible(False)
        self.tree.clear()

        if not files:
            item = QTreeWidgetItem(["（空目录）", "", ""])
            item.setForeground(0, QColor("#9ca3af"))
            self.tree.addTopLevelItem(item)
            return

        import datetime
        for f in files:
            name = f.get("server_filename", "")
            size = format_size(f.get("size", 0)) if not f.get("isdir") else "目录"
            mtime = f.get("local_mtime", 0)
            try:
                time_str = datetime.datetime.fromtimestamp(mtime).strftime(
                    "%Y-%m-%d %H:%M"
                )
            except Exception:
                time_str = ""

            item = QTreeWidgetItem([name, size, time_str])
            item.setData(0, Qt.UserRole, f)  # 存储完整文件信息

            if f.get("isdir"):
                item.setForeground(0, QColor("#2563eb"))
                item.setText(0, "📁 " + name)
            else:
                item.setText(0, "📄 " + name)

            self.tree.addTopLevelItem(item)

    def _on_load_error(self, error: str):
        """加载出错"""
        self.progress_bar.setVisible(False)
        if "登录" in error or "expired" in error.lower():
            self._show_not_logged_in()
            QMessageBox.warning(
                self, "登录过期", "登录已过期，请重新登录。"
            )
        else:
            item = QTreeWidgetItem([f"加载失败: {error}", "", ""])
            item.setForeground(0, QColor("#ef4444"))
            self.tree.addTopLevelItem(item)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, col: int):
        """双击进入目录"""
        file_info = item.data(0, Qt.UserRole)
        if file_info and file_info.get("isdir"):
            new_path = file_info.get("path", self._current_path)
            self._path_history.append(self._current_path)
            self._load_directory(new_path)

    def _go_back(self):
        """返回上级目录"""
        if len(self._path_history) > 1:
            self._path_history.pop()
            prev_path = self._path_history[-1]
            self._current_path = prev_path
            self._load_directory(prev_path)
        else:
            self._load_directory("/")

    def _refresh(self):
        """刷新当前目录"""
        self._load_directory(self._current_path)

    def _select_all(self):
        """全选/取消全选"""
        all_selected = all(
            self.tree.topLevelItem(i).isSelected()
            for i in range(self.tree.topLevelItemCount())
        )
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            item.setSelected(not all_selected)
        self.select_all_btn.setText("取消全选" if not all_selected else "全选")

    def _load_save_dir(self) -> str:
        """从配置文件读取上次保存的下载目录"""
        try:
            if os.path.exists(self._config_file):
                with open(self._config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    saved = data.get("save_dir", "")
                    if saved and os.path.isdir(saved):
                        return saved
        except Exception:
            pass
        return os.path.expanduser("~/Downloads")

    def _persist_save_dir(self, path: str):
        """把下载目录写入配置文件"""
        try:
            data = {}
            if os.path.exists(self._config_file):
                with open(self._config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data["save_dir"] = path
            with open(self._config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _browse_save_dir(self):
        """选择保存目录"""
        d = QFileDialog.getExistingDirectory(
            self, "选择保存目录", self._save_dir
        )
        if d:
            self._save_dir = d
            self.save_dir_edit.setText(d)
            self._persist_save_dir(d)  # 持久化保存

    def _add_to_queue(self):
        """将选中的文件添加到下载队列"""
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.information(self, "提示", "请先选择要下载的文件或目录。")
            return

        save_dir = self.save_dir_edit.text().strip()
        if not save_dir:
            QMessageBox.warning(self, "提示", "请先选择保存目录。")
            return

        added = 0
        for item in selected:
            file_info = item.data(0, Qt.UserRole)
            if not file_info:
                continue

            if file_info.get("isdir"):
                # 目录：递归加载所有文件
                self._add_directory_to_queue(file_info["path"], save_dir)
                added += 1
            else:
                self.manager.add_task(
                    pan_path=file_info["path"],
                    fs_id=file_info["fs_id"],
                    file_name=file_info["server_filename"],
                    file_size=file_info.get("size", 0),
                    save_dir=save_dir,
                )
                added += 1

        if added > 0:
            QMessageBox.information(
                self, "已添加",
                f"已将 {added} 个文件/目录添加到下载队列。\n"
                "请在「下载任务」标签页中查看。"
            )

    def _add_directory_to_queue(self, pan_path: str, save_dir: str):
        """递归将目录下所有文件加入队列"""
        try:
            files = self.api.list_all_files(pan_path)
            dir_name = os.path.basename(pan_path)
            local_dir = os.path.join(save_dir, dir_name)
            for f in files:
                if not f.get("isdir"):
                    self.manager.add_task(
                        pan_path=f["path"],
                        fs_id=f["fs_id"],
                        file_name=f["server_filename"],
                        file_size=f.get("size", 0),
                        save_dir=local_dir,
                    )
        except Exception as e:
            QMessageBox.warning(self, "错误", f"加载目录失败: {e}")
