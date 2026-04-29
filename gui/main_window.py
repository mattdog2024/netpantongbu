"""
百度网盘定时下载器 - 主界面
"""
import os
import sys
import datetime
from version import APP_VERSION, APP_NAME, APP_NAME_EN
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QLabel, QPushButton,
    QStatusBar, QMessageBox, QFrame, QApplication
)
from PyQt5.QtCore import Qt, QTimer, pyqtSlot, QSize, QPoint
from PyQt5.QtGui import QIcon, QFont, QColor, QPalette

from gui.file_browser import FileBrowserWidget
from gui.task_panel import TaskPanelWidget
from gui.schedule_panel import SchedulePanelWidget
from gui.login_widget import LoginWidget


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
QPushButton#winBtn {
    background: transparent;
    border: none;
    color: white;
    font-size: 16px;
    padding: 0px;
    border-radius: 0px;
    min-width: 46px;
    max-width: 46px;
    min-height: 46px;
    max-height: 46px;
}
QPushButton#winBtn:hover {
    background: rgba(255,255,255,0.18);
    color: white;
    border: none;
}
QPushButton#closeBtn {
    background: transparent;
    border: none;
    color: white;
    font-size: 16px;
    padding: 0px;
    border-radius: 0px;
    min-width: 46px;
    max-width: 46px;
    min-height: 46px;
    max-height: 46px;
}
QPushButton#closeBtn:hover {
    background: #ef4444;
    color: white;
    border: none;
}
"""


class TitleBar(QFrame):
    """可拖动的自定义标题栏，内含最小化/最大化/关闭按钮"""

    def __init__(self, parent_window):
        super().__init__(parent_window)
        self._parent = parent_window
        self._drag_pos = None
        self._maximized = False
        self.setObjectName("topBar")
        self.setFixedHeight(46)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 0, 0)
        layout.setSpacing(6)

        # 标题文字
        title_label = QLabel(APP_NAME)
        title_label.setObjectName("titleLabel")
        layout.addWidget(title_label)

        subtitle_label = QLabel(f"{APP_NAME_EN}  {APP_VERSION}")
        subtitle_label.setObjectName("subtitleLabel")
        layout.addWidget(subtitle_label)

        layout.addStretch()

        # 登录区域（由外部设置）
        self._login_placeholder = QWidget()
        self._login_placeholder.setFixedHeight(46)
        layout.addWidget(self._login_placeholder)

        # 最小化按钮
        btn_min = QPushButton("─")
        btn_min.setObjectName("winBtn")
        btn_min.setToolTip("最小化")
        btn_min.clicked.connect(self._parent.showMinimized)
        layout.addWidget(btn_min)

        # 最大化/还原按钮
        self._btn_max = QPushButton("□")
        self._btn_max.setObjectName("winBtn")
        self._btn_max.setToolTip("最大化")
        self._btn_max.clicked.connect(self._toggle_maximize)
        layout.addWidget(self._btn_max)

        # 关闭按钮
        btn_close = QPushButton("✕")
        btn_close.setObjectName("closeBtn")
        btn_close.setToolTip("关闭")
        btn_close.clicked.connect(self._parent._on_close_btn)
        layout.addWidget(btn_close)

        layout.setContentsMargins(14, 0, 0, 0)

    def set_login_widget(self, widget):
        """把登录控件插入到标题栏"""
        layout = self.layout()
        # 找到占位符的位置并替换
        idx = layout.indexOf(self._login_placeholder)
        if idx >= 0:
            layout.removeWidget(self._login_placeholder)
            self._login_placeholder.hide()
            layout.insertWidget(idx, widget)

    def _toggle_maximize(self):
        if self._parent.isMaximized():
            self._parent.showNormal()
            self._btn_max.setText("□")
            self._btn_max.setToolTip("最大化")
        else:
            self._parent.showMaximized()
            self._btn_max.setText("❐")
            self._btn_max.setToolTip("还原")

    # ---- 拖动支持 ----
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self._parent.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            if self._parent.isMaximized():
                self._parent.showNormal()
                self._btn_max.setText("□")
            self._parent.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._toggle_maximize()


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self, api, manager):
        super().__init__()
        self.api = api
        self.manager = manager

        # 去掉系统原生标题栏，使用自定义标题栏
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setWindowTitle(f"{APP_NAME}  {APP_VERSION}")
        self.setMinimumSize(1000, 680)
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

        # ---- 自定义标题栏（蓝色，可拖动，有三个按钮）----
        self.title_bar = TitleBar(self)
        main_layout.addWidget(self.title_bar)

        # 登录控件
        self.login_widget = LoginWidget(self.api, self)
        self.title_bar.set_login_widget(self.login_widget)

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
        QTimer.singleShot(800, self._do_check_login)

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

    def _on_close_btn(self):
        """标题栏关闭按钮点击"""
        from PyQt5.QtWidgets import QMessageBox as QMB
        msg = QMB(self)
        msg.setWindowTitle("关闭窗口")
        msg.setText(
            "关闭窗口后程序将继续在后台运行（系统托盘）。\n\n"
            "定时下载任务不会中断。"
        )
        btn_tray = msg.addButton("最小化到托盘", QMB.AcceptRole)
        btn_quit = msg.addButton("退出程序", QMB.DestructiveRole)
        msg.addButton("取消", QMB.RejectRole)
        msg.exec_()

        clicked = msg.clickedButton()
        if clicked == btn_tray:
            self.hide()
        elif clicked == btn_quit:
            self.manager.stop_download()
            QApplication.quit()

    def changeEvent(self, event):
        """最小化时隐藏到托盘"""
        from PyQt5.QtCore import QEvent
        if event.type() == QEvent.WindowStateChange:
            if self.isMinimized():
                QTimer.singleShot(100, self.hide)
        super().changeEvent(event)

    def closeEvent(self, event):
        """系统关闭事件（Alt+F4等）"""
        event.ignore()
        self._on_close_btn()
