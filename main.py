"""
百度网盘定时下载器 - 程序入口
"""
import sys
import os

# 确保能找到模块（打包成EXE后也能正常找到）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import (
    QApplication, QSplashScreen, QSystemTrayIcon, QMenu, QAction
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QPixmap, QColor, QPainter, QIcon

from core.baidu_api import BaiduPanAPI
from core.download_manager import DownloadManager
from gui.main_window import MainWindow


def create_splash():
    """创建启动画面"""
    pixmap = QPixmap(480, 280)
    pixmap.fill(QColor("#2563eb"))

    painter = QPainter(pixmap)
    painter.setPen(QColor("white"))

    font_title = QFont("Microsoft YaHei", 22, QFont.Bold)
    painter.setFont(font_title)
    painter.drawText(0, 0, 480, 160, Qt.AlignCenter, "百度网盘定时下载器")

    font_sub = QFont("Microsoft YaHei", 11)
    painter.setFont(font_sub)
    painter.setPen(QColor("#bfdbfe"))
    painter.drawText(0, 150, 480, 60, Qt.AlignCenter, "BaiduPan Scheduler  v1.0")
    painter.drawText(0, 200, 480, 40, Qt.AlignCenter, "正在启动，请稍候...")

    painter.end()
    return QSplashScreen(pixmap, Qt.WindowStaysOnTopHint)


def get_app_icon():
    """获取程序图标"""
    # 尝试从打包资源或同目录加载
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "assets", "icon.ico"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.ico"),
        os.path.join(sys._MEIPASS, "assets", "icon.ico") if hasattr(sys, "_MEIPASS") else "",
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return QIcon(path)

    # 如果找不到文件，用代码生成一个简单图标
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor("#2563eb"))
    painter = QPainter(pixmap)
    painter.setPen(QColor("white"))
    painter.setFont(QFont("Arial", 28, QFont.Bold))
    painter.drawText(0, 0, 64, 64, Qt.AlignCenter, "云")
    painter.end()
    return QIcon(pixmap)


def setup_tray(app, window, icon):
    """设置系统托盘"""
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return None

    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip("百度网盘定时下载器")

    # 托盘右键菜单
    menu = QMenu()

    show_action = QAction("显示主窗口", menu)
    show_action.triggered.connect(lambda: (window.show(), window.raise_(), window.activateWindow()))
    menu.addAction(show_action)

    menu.addSeparator()

    quit_action = QAction("退出程序", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)

    tray.setContextMenu(menu)

    # 双击托盘图标显示窗口
    def on_tray_activated(reason):
        if reason == QSystemTrayIcon.DoubleClick:
            window.show()
            window.raise_()
            window.activateWindow()

    tray.activated.connect(on_tray_activated)
    tray.show()

    return tray


def main():
    # 高DPI支持
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("百度网盘定时下载器")
    app.setOrganizationName("BdPanScheduler")
    # 关闭最后一个窗口时不退出（托盘模式）
    app.setQuitOnLastWindowClosed(False)

    # 加载图标
    icon = get_app_icon()
    app.setWindowIcon(icon)

    # 启动画面
    splash = create_splash()
    splash.show()
    app.processEvents()

    # 初始化核心组件
    # 配置文件保存在程序同目录（便携版）
    app_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    session_file = os.path.join(app_dir, "bdpan_session.pkl")
    config_file = os.path.join(app_dir, "bdpan_tasks.json")

    api = BaiduPanAPI(session_file=session_file)
    manager = DownloadManager(api, config_file=config_file)

    # 创建主窗口
    window = MainWindow(api, manager)
    window.setWindowIcon(icon)

    # 设置系统托盘
    tray = setup_tray(app, window, icon)

    # 关闭启动画面，显示主窗口
    def on_start():
        splash.finish(window)
        window.show()

    QTimer.singleShot(1500, on_start)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
