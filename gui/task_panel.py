"""
下载任务面板 - 显示任务列表、进度、控制按钮、详细日志
"""
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QProgressBar, QFrame, QAbstractItemView, QMessageBox,
    QSizePolicy, QTextEdit, QSplitter, QTabWidget
)
from PyQt5.QtCore import Qt, pyqtSlot, QTimer
from PyQt5.QtGui import QColor, QFont


def format_size(size_bytes):
    if not size_bytes or size_bytes == 0:
        return "-"
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def format_speed(speed_bytes):
    if speed_bytes <= 0:
        return ""
    return format_size(speed_bytes) + "/s"


STATUS_COLORS = {
    "等待中": "#6b7280",
    "下载中": "#2563eb",
    "已暂停": "#d97706",
    "已完成": "#16a34a",
    "失败": "#ef4444",
    "定时等待": "#7c3aed",
    "已停止": "#9ca3af",
}


class TaskPanelWidget(QWidget):
    """任务面板（含日志）"""

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._task_rows = {}  # task_id -> row_index
        self._setup_ui()
        self._connect_signals()
        self._load_existing_tasks()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # ---- 控制按钮 ----
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)

        self.start_btn = QPushButton("开始下载")
        self.start_btn.setObjectName("primaryBtn")
        self.start_btn.setFixedHeight(32)
        self.start_btn.clicked.connect(self._start_download)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("停止下载")
        self.stop_btn.setFixedHeight(32)
        self.stop_btn.clicked.connect(self._stop_download)
        btn_layout.addWidget(self.stop_btn)

        self.retry_btn = QPushButton("重试失败")
        self.retry_btn.setFixedHeight(32)
        self.retry_btn.setToolTip("将所有失败的任务重置为等待中，然后重新下载")
        self.retry_btn.clicked.connect(self._retry_failed)
        btn_layout.addWidget(self.retry_btn)

        btn_layout.addStretch()

        self.clear_btn = QPushButton("清除已完成")
        self.clear_btn.setFixedHeight(32)
        self.clear_btn.clicked.connect(self._clear_completed)
        btn_layout.addWidget(self.clear_btn)

        self.remove_btn = QPushButton("删除选中")
        self.remove_btn.setObjectName("dangerBtn")
        self.remove_btn.setFixedHeight(32)
        self.remove_btn.clicked.connect(self._remove_selected)
        btn_layout.addWidget(self.remove_btn)

        layout.addLayout(btn_layout)

        # ---- 上下分割：任务表格 + 日志面板 ----
        splitter = QSplitter(Qt.Vertical)

        # 任务表格
        table_frame = QWidget()
        table_layout = QVBoxLayout(table_frame)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(4)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["文件名", "大小", "进度", "速度", "状态"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        self.table.setColumnWidth(1, 80)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 80)
        self.table.setColumnWidth(4, 70)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet(
            "QTableWidget { border: 1px solid #e5e7eb; border-radius: 6px; "
            "background: white; gridline-color: #f3f4f6; }"
            "QTableWidget::item { padding: 4px 6px; }"
            "QTableWidget::item:selected { background: #dbeafe; color: #1e40af; }"
            "QHeaderView::section { background: #f9fafb; border: none; "
            "border-bottom: 1px solid #e5e7eb; padding: 6px 8px; "
            "font-weight: bold; color: #374151; }"
        )
        table_layout.addWidget(self.table)

        # 统计信息
        self.stats_label = QLabel("共 0 个任务")
        self.stats_label.setStyleSheet("color: #6b7280; font-size: 12px;")
        table_layout.addWidget(self.stats_label)

        splitter.addWidget(table_frame)

        # 日志面板
        log_frame = QWidget()
        log_layout = QVBoxLayout(log_frame)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(4)

        log_header = QHBoxLayout()
        log_title = QLabel("运行日志")
        log_title.setStyleSheet("color: #374151; font-weight: bold; font-size: 12px;")
        log_header.addWidget(log_title)
        log_header.addStretch()
        clear_log_btn = QPushButton("清空日志")
        clear_log_btn.setFixedHeight(22)
        clear_log_btn.setFixedWidth(70)
        clear_log_btn.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 1px 6px; "
            "border: 1px solid #d1d5db; border-radius: 3px; }"
        )
        clear_log_btn.clicked.connect(self._clear_log)
        log_header.addWidget(clear_log_btn)
        log_layout.addLayout(log_header)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(180)
        self.log_text.setStyleSheet(
            "QTextEdit { background: #1e1e2e; color: #cdd6f4; "
            "font-family: Consolas, 'Courier New', monospace; "
            "font-size: 11px; border: 1px solid #313244; border-radius: 4px; "
            "padding: 4px; }"
        )
        log_layout.addWidget(self.log_text)

        splitter.addWidget(log_frame)
        splitter.setSizes([320, 200])

        layout.addWidget(splitter)

    def _connect_signals(self):
        self.manager.task_added.connect(self._on_task_added)
        self.manager.task_updated.connect(self._on_task_updated)
        self.manager.all_tasks_updated.connect(self._on_all_tasks_updated)
        self.manager.detail_log.connect(self._on_detail_log)

    def _load_existing_tasks(self):
        """加载已有任务"""
        for task in self.manager.tasks:
            self._add_task_row(task.task_id, {
                "task_id": task.task_id,
                "file_name": task.file_name,
                "file_size": task.file_size,
                "progress": task.progress,
                "speed": task.speed,
                "status": task.status,
                "error_msg": task.error_msg,
            })
        self._update_stats()

    @pyqtSlot(str)
    def _on_detail_log(self, msg: str):
        """接收详细日志并追加到日志框"""
        self.log_text.append(msg)
        # 自动滚动到底部
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    @pyqtSlot(str, dict)
    def _on_task_added(self, task_id: str, task_info: dict):
        self._add_task_row(task_id, task_info)
        self._update_stats()

    @pyqtSlot(str, dict)
    def _on_task_updated(self, task_id: str, task_info: dict):
        if task_id in self._task_rows:
            row = self._task_rows[task_id]
            self._update_task_row(row, task_info)
        self._update_stats()

    @pyqtSlot(list)
    def _on_all_tasks_updated(self, tasks: list):
        self.table.setRowCount(0)
        self._task_rows.clear()
        for t in tasks:
            self._add_task_row(t["task_id"], t)
        self._update_stats()

    def _add_task_row(self, task_id: str, task_info: dict):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._task_rows[task_id] = row

        # 文件名
        name_item = QTableWidgetItem(task_info.get("file_name", ""))
        name_item.setData(Qt.UserRole, task_id)
        name_item.setToolTip(task_info.get("file_name", ""))
        self.table.setItem(row, 0, name_item)

        # 大小
        size_item = QTableWidgetItem(
            format_size(task_info.get("file_size", 0))
        )
        size_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 1, size_item)

        # 进度条
        progress = task_info.get("progress", 0.0)
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(int(progress * 100))
        progress_bar.setTextVisible(True)
        progress_bar.setFormat("%p%")
        progress_bar.setStyleSheet(
            "QProgressBar { border: 1px solid #e5e7eb; border-radius: 3px; "
            "background: #f3f4f6; height: 16px; }"
            "QProgressBar::chunk { background: #2563eb; border-radius: 2px; }"
        )
        self.table.setCellWidget(row, 2, progress_bar)

        # 速度
        speed_item = QTableWidgetItem(
            format_speed(task_info.get("speed", 0))
        )
        speed_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 3, speed_item)

        # 状态
        status = task_info.get("status", "等待中")
        status_item = QTableWidgetItem(status)
        status_item.setTextAlignment(Qt.AlignCenter)
        color = STATUS_COLORS.get(status, "#6b7280")
        status_item.setForeground(QColor(color))
        self.table.setItem(row, 4, status_item)

        self.table.setRowHeight(row, 36)

    def _update_task_row(self, row: int, task_info: dict):
        if row >= self.table.rowCount():
            return

        # 进度
        progress = task_info.get("progress", 0.0)
        pb = self.table.cellWidget(row, 2)
        if pb:
            pb.setValue(int(progress * 100))

        # 速度
        speed_item = self.table.item(row, 3)
        if speed_item:
            speed = task_info.get("speed", 0)
            speed_item.setText(
                format_speed(speed) if task_info.get("status") == "下载中" else ""
            )

        # 状态
        status = task_info.get("status", "等待中")
        status_item = self.table.item(row, 4)
        if status_item:
            status_item.setText(status)
            color = STATUS_COLORS.get(status, "#6b7280")
            status_item.setForeground(QColor(color))

    def _update_stats(self):
        total = len(self.manager.tasks)
        completed = sum(
            1 for t in self.manager.tasks if t.status == "已完成"
        )
        running = sum(
            1 for t in self.manager.tasks if t.status == "下载中"
        )
        failed = sum(
            1 for t in self.manager.tasks if t.status == "失败"
        )
        self.stats_label.setText(
            f"共 {total} 个任务  |  已完成 {completed}  |  "
            f"下载中 {running}  |  失败 {failed}"
        )

    def _start_download(self):
        self.manager.start_download()

    def _stop_download(self):
        self.manager.stop_download()

    def _retry_failed(self):
        """重试所有失败的任务"""
        count = self.manager.retry_failed()
        if count > 0:
            self.manager.start_download()
        else:
            QMessageBox.information(self, "提示", "没有失败的任务需要重试。")

    def _clear_completed(self):
        self.manager.clear_completed()

    def _clear_log(self):
        self.log_text.clear()

    def _remove_selected(self):
        selected_rows = set(
            item.row() for item in self.table.selectedItems()
        )
        if not selected_rows:
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除选中的 {len(selected_rows)} 个任务吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        task_ids_to_remove = []
        for row in selected_rows:
            name_item = self.table.item(row, 0)
            if name_item:
                task_id = name_item.data(Qt.UserRole)
                if task_id:
                    task_ids_to_remove.append(task_id)

        for tid in task_ids_to_remove:
            self.manager.remove_task(tid)
