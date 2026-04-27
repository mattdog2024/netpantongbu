"""
百度网盘定时下载器 - 主界面
"""
import os
import sys
import datetime
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QLabel, QPushButton,
    QStatusBar, QAction, QToolBar, QMessageBox,
    QFileDialog, QFrame, QApplication
)
from PyQt5.QtCore import Qt, QTimer, pyqtSlot, QSize
from PyQt5.QtGui import QIcon, QFont, QColor, QPalette

from .file_browser import FileBrowserWidget
from .task_panel import TaskPanelWidget
from .schedule_panel import SchedulePanelWidget
from .login_widget import LoginWidget


STYLE_SHEET = """
QMainWindow {
    background-color: #f5f6fa;
}
QWidget {
    font-family: "Microsoft YaHei", "微软雅黑", Arial, sans-serif;
    font-size: 13px;
}
QTabWidget::pane {
    border: 1px solid #dde1e7;
    border-radius: 6px;
    background: white;
}
QTabBar::tab {
    background: #eef0f5;
    border: 1px solid #dde1e7;
    border-bottom: none;
    padding: 7px 18px;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    margin-right: 2px;
    color: #555;
}
QTabBar::tab:selected {
    background: white;
    color: #2563eb;
    font-weight: bold;
    border-bottom: 2px solid white;
}
QTabBar::tab:hover {
    background: #dce3f5;
}
QPushButton {
    border: 1px solid #c8ccd4;
    border-radius: 5px;
    padding: 5px 14px;
    background: white;
    color: #333;
}
QPushButton:hover {
    background: #eef2ff;
    border-color: #2563eb;
    color: #2563eb;
}
QPushButton:pressed {
    background: #dbeafe;
}
QPushButton#primaryBtn {
    background: #2563eb;
    color: white;
    border: none;
    font-weight: bold;
}
QPushButton#primaryBtn:hover {
    background: #1d4ed8;
}
QPushButton#primaryBtn:pressed {
    background: #1e40af;
}
QPushButton#dangerBtn {
    background: #ef4444;
    color: white;
    border: none;
}
QPushButton#dangerBtn:hover {
    background: #dc2626;
}
QStatusBar {
    background: #f0f2f8;
    border-top: 1px solid #dde1e7;
    color: #555;
    font-size: 12px;
}
QSplitter::handle {
    background: #dde1e7;
    width: 2px;
}
QFrame#topBar {
    background: #2563eb;
    border-radius: 0px;
}
QLabel#titleLabel {
    color: white;
    font-size: 16px;
    font-weight: bold;
}
QLabel#subtitleLabel {
    color: #bfdbfe;
    font-size: 11px;
}
"""


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self, api, manager):
        super().__init__()
        self.api = api
        self.manager = manager
        self.setWindowTitle("百度网盘定时下载器")
        self.setMinimumSize(1100, 720)
        self.resize(1200, 780)
        self.setStyleSheet(STYLE_SHEET)
        self._setup_ui()
        self._connect_signals()
        self._check_login_status()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ---- 顶部标题栏 ----
        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_bar.setFixedHeight(56)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(18, 0, 18, 0)

        title_label = QLabel("百度网盘定时下载器")
        title_label.setObjectName("titleLabel")
        top_layout.addWidget(title_label)

        subtitle_label = QLabel("BaiduPan Scheduler  v1.0")
        subtitle_label.setObjectName("subtitleLabel")
        top_layout.addWidget(subtitle_label)
        top_layout.addStretch()

        # 登录状态区域
        self.login_widget = LoginWidget(self.api, self)
        top_layout.addWidget(self.login_widget)

        main_layout.addWidget(top_bar)

        # ---- 主内容区 ----
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(12, 12, 12, 8)
        content_layout.setSpacing(10)

        # 左侧：文件浏览器
        left_frame = QFrame()
        left_frame.setStyleSheet(
            "QFrame { background: white; border: 1px solid #dde1e7; "
            "border-radius: 8px; }"
        )
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.file_browser = FileBrowserWidget(self.api, self.manager)
        left_layout.addWidget(self.file_browser)

        # 右侧：任务面板 + 定时面板
        right_tabs = QTabWidget()
        right_tabs.setMinimumWidth(380)

        self.task_panel = TaskPanelWidget(self.manager)
        right_tabs.addTab(self.task_panel, "  下载任务  ")

        self.schedule_panel = SchedulePanelWidget(self.manager)
        right_tabs.addTab(self.schedule_panel, "  定时设置  ")

        # 分割器
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_frame)
        splitter.addWidget(right_tabs)
        splitter.setSizes([680, 420])
        splitter.setHandleWidth(6)

        content_layout.addWidget(splitter)
        main_layout.addWidget(content_widget)

        # ---- 状态栏 ----
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.status_login = QLabel("未登录")
        self.status_login.setStyleSheet("color: #ef4444; padding: 0 8px;")
        self.status_bar.addPermanentWidget(self.status_login)

        self.status_schedule = QLabel(self.manager.get_schedule_status())
        self.status_schedule.setStyleSheet("color: #555; padding: 0 8px;")
        self.status_bar.addWidget(self.status_schedule)

        self.status_msg = QLabel("就绪")
        self.status_bar.addWidget(self.status_msg)

    def _connect_signals(self):
        """连接信号槽"""
        self.manager.log_message.connect(self._on_log_message)
        self.manager.schedule_status_changed.connect(self._on_schedule_changed)
        self.login_widget.login_state_changed.connect(self._on_login_state_changed)

    def _check_login_status(self):
        """启动时检查登录状态"""
        QTimer.singleShot(500, self._do_check_login)

    def _do_check_login(self):
        if self.api.check_login():
            self.login_widget.set_logged_in(True)
            self._on_login_state_changed(True)
        else:
            self.login_widget.set_logged_in(False)
            self._on_login_state_changed(False)

    @pyqtSlot(bool)
    def _on_login_state_changed(self, logged_in: bool):
        if logged_in:
            self.status_login.setText("已登录")
            self.status_login.setStyleSheet("color: #16a34a; padding: 0 8px;")
            self.file_browser.set_logged_in(True)
        else:
            self.status_login.setText("未登录")
            self.status_login.setStyleSheet("color: #ef4444; padding: 0 8px;")
            self.file_browser.set_logged_in(False)

    @pyqtSlot(str)
    def _on_log_message(self, msg: str):
        self.status_msg.setText(msg)

    @pyqtSlot(str)
    def _on_schedule_changed(self, status: str):
        self.status_schedule.setText(status)

    def closeEvent(self, event):
        """关闭时停止下载"""
        reply = QMessageBox.question(
            self, "确认退出",
            "退出程序将停止所有下载任务，确定退出吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.manager.stop_download()
            event.accept()
        else:
            event.ignore()
