"""
登录状态组件 - 显示在顶部栏
"""
import sys
import os
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, pyqtSlot


class LoginCheckThread(QThread):
    """后台线程检查登录状态"""
    result = pyqtSignal(bool)

    def __init__(self, api):
        super().__init__()
        self.api = api

    def run(self):
        result = self.api.check_login()
        self.result.emit(result)


class LoginWidget(QWidget):
    """顶部登录状态组件"""

    login_state_changed = pyqtSignal(bool)

    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        self._logged_in = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.status_label = QLabel("未登录")
        self.status_label.setStyleSheet(
            "color: #fca5a5; font-size: 12px;"
        )
        layout.addWidget(self.status_label)

        self.login_btn = QPushButton("登录百度账号")
        self.login_btn.setFixedHeight(30)
        self.login_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.2); color: white; "
            "border: 1px solid rgba(255,255,255,0.5); border-radius: 4px; "
            "padding: 3px 12px; font-size: 12px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.35); }"
        )
        self.login_btn.clicked.connect(self._do_login)
        layout.addWidget(self.login_btn)

        self.logout_btn = QPushButton("退出登录")
        self.logout_btn.setFixedHeight(30)
        self.logout_btn.setVisible(False)
        self.logout_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.1); color: #fca5a5; "
            "border: 1px solid rgba(255,100,100,0.4); border-radius: 4px; "
            "padding: 3px 12px; font-size: 12px; }"
            "QPushButton:hover { background: rgba(255,100,100,0.2); }"
        )
        self.logout_btn.clicked.connect(self._do_logout)
        layout.addWidget(self.logout_btn)

    def set_logged_in(self, logged_in: bool):
        self._logged_in = logged_in
        if logged_in:
            self.status_label.setText("已登录")
            self.status_label.setStyleSheet(
                "color: #86efac; font-size: 12px;"
            )
            self.login_btn.setVisible(False)
            self.logout_btn.setVisible(True)
        else:
            self.status_label.setText("未登录")
            self.status_label.setStyleSheet(
                "color: #fca5a5; font-size: 12px;"
            )
            self.login_btn.setVisible(True)
            self.logout_btn.setVisible(False)

    def _do_login(self):
        """打开登录对话框"""
        try:
            from ..core.login_server import LoginDialog
            dialog = LoginDialog(self.window())
            dialog.login_success.connect(self._on_login_success)
            dialog.exec_()
        except ImportError:
            # WebEngine可能不可用，提示手动输入Cookie
            self._show_cookie_input()

    def _on_login_success(self, cookies: dict):
        """登录成功回调"""
        self.api.update_cookies_from_browser(cookies)
        # 验证登录
        if self.api.check_login():
            self.set_logged_in(True)
            self.login_state_changed.emit(True)
            QMessageBox.information(
                self.window(), "登录成功", "百度账号登录成功！"
            )
        else:
            QMessageBox.warning(
                self.window(), "登录失败",
                "Cookie获取成功但验证失败，请重试。"
            )

    def _show_cookie_input(self):
        """备用：手动输入Cookie方式"""
        from PyQt5.QtWidgets import QInputDialog
        text, ok = QInputDialog.getMultiLineText(
            self.window(),
            "手动输入Cookie",
            "请打开浏览器登录百度网盘，然后从开发者工具中复制Cookie粘贴到此处：\n"
            "（格式：BDUSS=xxx; STOKEN=xxx; ...）",
            ""
        )
        if ok and text.strip():
            cookies = {}
            for item in text.split(";"):
                item = item.strip()
                if "=" in item:
                    k, v = item.split("=", 1)
                    cookies[k.strip()] = v.strip()
            if cookies:
                self._on_login_success(cookies)

    def _do_logout(self):
        """退出登录"""
        reply = QMessageBox.question(
            self.window(), "确认退出登录",
            "退出登录后需要重新扫码登录，确定吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            import os
            try:
                if os.path.exists(self.api.session_file):
                    os.remove(self.api.session_file)
            except Exception:
                pass
            self.api.session.cookies.clear()
            self.api.bdstoken = None
            self.set_logged_in(False)
            self.login_state_changed.emit(False)
