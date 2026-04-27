"""
百度网盘登录模块
通过内嵌浏览器（PyQt5 WebEngine）完成扫码登录，自动提取Cookie
"""
import json
import threading
import time
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QProgressBar, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, QUrl
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineProfile
from PyQt5.QtNetwork import QNetworkCookie
from PyQt5.QtCore import QByteArray


class LoginDialog(QDialog):
    """内嵌浏览器登录对话框"""
    
    login_success = pyqtSignal(dict)  # 登录成功信号，传递cookies
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("登录百度网盘")
        self.setMinimumSize(900, 650)
        self.setModal(True)
        self.cookies = {}
        self._setup_ui()
        self._start_check_timer()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 顶部提示
        tip_label = QLabel(
            "请在下方浏览器中登录您的百度账号，登录成功后窗口将自动关闭。"
        )
        tip_label.setAlignment(Qt.AlignCenter)
        tip_label.setStyleSheet(
            "font-size: 13px; color: #333; padding: 6px; "
            "background: #e8f4fd; border-radius: 4px;"
        )
        layout.addWidget(tip_label)

        # 内嵌浏览器
        self.web_view = QWebEngineView()
        self.web_view.setMinimumHeight(520)
        
        # 使用独立的profile避免影响系统浏览器
        self.profile = QWebEngineProfile("BdPanLogin", self.web_view)
        from PyQt5.QtWebEngineWidgets import QWebEnginePage
        page = QWebEnginePage(self.profile, self.web_view)
        self.web_view.setPage(page)
        
        # 导航到百度网盘登录页
        self.web_view.load(QUrl("https://pan.baidu.com/disk/home"))
        layout.addWidget(self.web_view)

        # 底部按钮
        btn_layout = QHBoxLayout()
        self.status_label = QLabel("等待登录...")
        self.status_label.setStyleSheet("color: #666; font-size: 12px;")
        btn_layout.addWidget(self.status_label)
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedWidth(80)
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet(
            "QPushButton { background: #f0f0f0; border: 1px solid #ccc; "
            "border-radius: 4px; padding: 5px 10px; }"
            "QPushButton:hover { background: #e0e0e0; }"
        )
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _start_check_timer(self):
        """定时检查是否已登录成功"""
        self.check_timer = QTimer(self)
        self.check_timer.timeout.connect(self._check_login_status)
        self.check_timer.start(2000)  # 每2秒检查一次

    def _check_login_status(self):
        """检查Cookie中是否包含登录凭证"""
        self.web_view.page().runJavaScript(
            "document.cookie",
            self._on_cookie_received
        )

    def _on_cookie_received(self, cookie_str):
        """处理获取到的Cookie字符串"""
        if not cookie_str:
            return
        
        # 检查关键Cookie是否存在
        cookies = {}
        for item in cookie_str.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                cookies[k.strip()] = v.strip()
        
        # BDUSS是百度登录的核心Cookie
        if "BDUSS" in cookies and len(cookies.get("BDUSS", "")) > 10:
            self.check_timer.stop()
            self.status_label.setText("登录成功！正在保存...")
            self.status_label.setStyleSheet("color: green; font-size: 12px;")
            
            # 同时从WebEngine的CookieStore获取完整Cookie
            self._extract_all_cookies()

    def _extract_all_cookies(self):
        """从WebEngine的CookieStore提取所有Cookie"""
        cookie_store = self.profile.cookieStore()
        self._all_cookies = {}
        
        def on_cookie(cookie):
            name = bytes(cookie.name()).decode("utf-8", errors="ignore")
            value = bytes(cookie.value()).decode("utf-8", errors="ignore")
            self._all_cookies[name] = value
        
        cookie_store.cookieAdded.connect(on_cookie)
        
        # 延迟一下再关闭，确保Cookie收集完毕
        QTimer.singleShot(1500, self._finish_login)

    def _finish_login(self):
        """完成登录流程"""
        # 通过JavaScript再次获取Cookie作为备用
        self.web_view.page().runJavaScript(
            "document.cookie",
            self._finalize_with_js_cookies
        )

    def _finalize_with_js_cookies(self, cookie_str):
        """最终处理Cookie并关闭对话框"""
        final_cookies = {}
        if cookie_str:
            for item in cookie_str.split(";"):
                item = item.strip()
                if "=" in item:
                    k, v = item.split("=", 1)
                    final_cookies[k.strip()] = v.strip()
        
        # 合并两种方式获取的Cookie
        if hasattr(self, "_all_cookies"):
            final_cookies.update(self._all_cookies)
        
        if final_cookies:
            self.cookies = final_cookies
            self.login_success.emit(final_cookies)
            self.accept()
        else:
            QMessageBox.warning(self, "登录失败", "无法获取登录信息，请重试。")
