"""
登录状态组件 - 显示在顶部栏
"""
import sys
import os
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, QMessageBox,
    QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, pyqtSlot


class LoginCheckThread(QThread):
    """后台线程检查登录状态，避免主线程阻塞/崩溃"""
    result = pyqtSignal(bool, str)   # (成功与否, 消息)

    def __init__(self, api):
        super().__init__()
        self.api = api

    def run(self):
        try:
            ok = self.api.check_login()
            if ok:
                self.result.emit(True, "Cookie验证成功，已登录！")
            else:
                self.result.emit(False,
                    "Cookie验证失败。\n\n可能原因：\n"
                    "1. Cookie已过期，请重新从浏览器复制\n"
                    "2. 请确保在登录状态下复制Cookie\n"
                    "3. 确保包含 BDUSS 字段"
                )
        except Exception as e:
            self.result.emit(False, f"验证时发生错误：{e}")


class LoginWidget(QWidget):
    """顶部登录状态组件"""

    login_state_changed = pyqtSignal(bool)

    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        self._logged_in = False
        self._check_thread = None
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
            dialog.login_success.connect(self._on_login_success_from_browser)
            dialog.exec_()
        except Exception:
            # WebEngine不可用或其他错误，使用手动输入Cookie方式
            self._show_cookie_input()

    def _on_login_success_from_browser(self, cookies: dict):
        """浏览器登录成功回调"""
        try:
            self.api.update_cookies(cookies)
            self._start_verify()
        except Exception as e:
            QMessageBox.critical(self.window(), "错误", f"处理Cookie时出错：{e}")

    def _show_cookie_input(self):
        """手动输入Cookie方式（带详细说明）"""
        try:
            dialog = CookieInputDialog(self.window())
            if dialog.exec_() == QDialog.Accepted:
                cookie_text = dialog.get_cookie_text().strip()
                if not cookie_text:
                    return
                # 解析并设置Cookie
                ok = self.api.set_cookie_string(cookie_text)
                if not ok:
                    QMessageBox.warning(
                        self.window(), "格式错误",
                        "Cookie格式不正确，请按 名称=值; 名称=值 的格式输入，\n"
                        "或直接粘贴从浏览器开发者工具复制的整行Cookie。"
                    )
                    return
                # 检查是否包含BDUSS
                bduss = self.api._bduss or self.api.session.cookies.get("BDUSS", "")
                if not bduss:
                    QMessageBox.warning(
                        self.window(), "缺少BDUSS",
                        "Cookie中没有找到 BDUSS 字段。\n\n"
                        "请确保粘贴的是完整的Cookie，包含 BDUSS=xxx 这一项。\n\n"
                        "提示：也可以只输入 BDUSS=你的值 这一行。"
                    )
                    return
                self._start_verify()
        except Exception as e:
            QMessageBox.critical(self.window(), "错误", f"打开登录对话框时出错：{e}")

    def _start_verify(self):
        """在后台线程中验证Cookie，避免主线程阻塞"""
        self.login_btn.setEnabled(False)
        self.login_btn.setText("验证中...")
        self.status_label.setText("正在验证...")
        self.status_label.setStyleSheet("color: #fde68a; font-size: 12px;")

        self._check_thread = LoginCheckThread(self.api)
        self._check_thread.result.connect(self._on_verify_result)
        self._check_thread.start()

    @pyqtSlot(bool, str)
    def _on_verify_result(self, success: bool, message: str):
        """验证完成回调（在主线程中执行）"""
        self.login_btn.setEnabled(True)
        self.login_btn.setText("登录百度账号")

        if success:
            self.set_logged_in(True)
            self.login_state_changed.emit(True)
            QMessageBox.information(self.window(), "登录成功", message)
        else:
            self.set_logged_in(False)
            QMessageBox.warning(self.window(), "验证失败", message)

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
            self.api._bduss = None
            self.api.bdstoken = None
            self.api.uk = None
            self.set_logged_in(False)
            self.login_state_changed.emit(False)


class CookieInputDialog(QDialog):
    """Cookie输入对话框，带详细操作说明"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("输入百度网盘 Cookie")
        self.setMinimumWidth(620)
        self.setMinimumHeight(460)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 说明文字
        guide = QLabel(
            "【推荐方式】只复制 BDUSS 的值：\n"
            "1. 用 Chrome 浏览器打开 pan.baidu.com 并登录\n"
            "2. 按 F12 → 点「应用程序」→ 左侧「Cookie」→ pan.baidu.com\n"
            "3. 找到 BDUSS 那一行，双击「值」列，全选复制\n"
            "4. 在下方输入框填入：BDUSS=你复制的值\n\n"
            "【也可以】复制整行 Cookie（从 Network 标签的请求头中复制）"
        )
        guide.setStyleSheet(
            "background: #eff6ff; border: 1px solid #bfdbfe; "
            "border-radius: 6px; padding: 10px; color: #1e40af; "
            "font-size: 12px; line-height: 1.6;"
        )
        guide.setWordWrap(True)
        layout.addWidget(guide)

        # 输入框标签
        input_label = QLabel("粘贴 Cookie 内容（必须包含 BDUSS）：")
        input_label.setStyleSheet("font-weight: bold; color: #374151;")
        layout.addWidget(input_label)

        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText(
            "方式一（推荐，只填BDUSS）：\n"
            "BDUSS=k8zRnFWQmlZMGZ5VE5KeEtHQ3lBR0d4MXA0ODN0...\n\n"
            "方式二（整行Cookie）：\n"
            "BDUSS=k8zRnFW...; STOKEN=109e308...; BAIDUID=C0D8A6...\n\n"
            "（直接从开发者工具复制整行Cookie也可以）"
        )
        self.text_edit.setMinimumHeight(130)
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
