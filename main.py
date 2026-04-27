"""
百度网盘定时下载器 - 程序入口
"""
import sys
import os

# 确保能找到模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication, QSplashScreen, QLabel
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QPixmap, QColor, QPainter

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


def main():
    # 高DPI支持
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("百度网盘定时下载器")
    app.setOrganizationName("BdPanScheduler")

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

    # 关闭启动画面，显示主窗口
    QTimer.singleShot(1500, lambda: (splash.finish(window), window.show()))

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
