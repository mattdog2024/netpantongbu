"""
登录状态组件 - 显示在顶部栏
"""
import sys
import os
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, QMessageBox,
    QInputDialog, QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox
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
            from core.login_server import LoginDialog
            dialog = LoginDialog(self.window())
            dialog.login_success.connect(self._on_login_success)
            dialog.exec_()
        except ImportError:
            # WebEngine不可用，使用手动输入Cookie方式
            self._show_cookie_input()
        except Exception:
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
        """手动输入Cookie方式（带详细说明）"""
        dialog = CookieInputDialog(self.window())
        if dialog.exec_() == QDialog.Accepted:
            cookie_text = dialog.get_cookie_text()
            if cookie_text.strip():
                cookies = self._parse_cookie_string(cookie_text)
                if cookies:
                    self.api.update_cookies_from_browser(cookies)
                    # 验证
                    if self.api.check_login():
                        self.set_logged_in(True)
                        self.login_state_changed.emit(True)
                        QMessageBox.information(
                            self.window(), "登录成功",
                            "Cookie验证成功，已登录！"
                        )
                    else:
                        QMessageBox.warning(
                            self.window(), "验证失败",
                            "Cookie格式正确但验证失败。\n\n"
                            "可能原因：\n"
                            "1. Cookie已过期，请重新从浏览器复制\n"
                            "2. 请确保复制的是登录后的Cookie\n"
                            "3. 确保包含 BDUSS 字段"
                        )
                else:
                    QMessageBox.warning(
                        self.window(), "格式错误",
                        "Cookie格式不正确，请按 名称=值; 名称=值 的格式输入"
                    )

    def _parse_cookie_string(self, text: str) -> dict:
        """解析Cookie字符串为字典"""
        cookies = {}
        for item in text.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                k = k.strip()
                v = v.strip()
                if k:
                    cookies[k] = v
        return cookies

    def _do_logout(self):
        """退出登录"""
        reply = QMessageBox.question(
            self.window(), "确认退出登录",
            "退出登录后需要重新输入Cookie，确定吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            try:
                if os.path.exists(self.api.session_file):
                    os.remove(self.api.session_file)
            except Exception:
                pass
            self.api.session.cookies.clear()
            self.api.bdstoken = None
            self.api.uk = None
            self.set_logged_in(False)
            self.login_state_changed.emit(False)


class CookieInputDialog(QDialog):
    """Cookie输入对话框，带详细操作说明"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("输入百度网盘 Cookie")
        self.setMinimumWidth(600)
        self.setMinimumHeight(420)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 说明文字
        guide = QLabel(
            "操作步骤：\n"
            "1. 用 Chrome 浏览器打开 pan.baidu.com 并登录\n"
            "2. 按 F12 打开开发者工具\n"
            "3. 点击顶部「Network（网络）」标签\n"
            "4. 按 F5 刷新页面\n"
            "5. 点击左侧第一个请求（通常是 pan.baidu.com）\n"
            "6. 在右侧找到「Request Headers（请求标头）」\n"
            "7. 找到「cookie」这一行，右键 → Copy value\n"
            "8. 粘贴到下方输入框"
        )
        guide.setStyleSheet(
            "background: #eff6ff; border: 1px solid #bfdbfe; "
            "border-radius: 6px; padding: 10px; color: #1e40af; "
            "font-size: 12px; line-height: 1.6;"
        )
        guide.setWordWrap(True)
        layout.addWidget(guide)

        # 输入框
        input_label = QLabel("粘贴 Cookie 内容（包含 BDUSS 和 STOKEN）：")
        input_label.setStyleSheet("font-weight: bold; color: #374151;")
        layout.addWidget(input_label)

        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText(
            "粘贴格式示例：\n"
            "BDUSS=k8zRnFW...; STOKEN=109e308...; BAIDUID=C0D8A6...\n\n"
            "（直接从开发者工具复制整行Cookie即可，不需要手动整理格式）"
        )
        self.text_edit.setMinimumHeight(120)
        self.text_edit.setStyleSheet(
            "border: 1px solid #d1d5db; border-radius: 4px; "
            "padding: 8px; font-family: Consolas, monospace; font-size: 11px;"
        )
        layout.addWidget(self.text_edit)

        # 提示
        tip = QLabel("注意：Cookie 相当于登录密码，请勿泄露给他人。")
        tip.setStyleSheet("color: #ef4444; font-size: 11px;")
        layout.addWidget(tip)

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Ok).setText("确认登录")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_cookie_text(self) -> str:
        return self.text_edit.toPlainText().strip()
