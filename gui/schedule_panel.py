"""
定时设置面板 - 配置定时下载时间段
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QSpinBox, QCheckBox, QGroupBox,
    QFrame, QTextEdit, QSizePolicy, QTimeEdit
)
from PyQt5.QtCore import Qt, pyqtSlot, QTime, QTimer
from PyQt5.QtGui import QFont, QColor
import datetime

from ..core.download_manager import ScheduleConfig


class SchedulePanelWidget(QWidget):
    """定时设置面板"""

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._setup_ui()
        self._load_config()
        self._connect_signals()
        self._start_clock()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # ---- 当前时间显示 ----
        clock_frame = QFrame()
        clock_frame.setStyleSheet(
            "QFrame { background: #eff6ff; border: 1px solid #bfdbfe; "
            "border-radius: 8px; padding: 8px; }"
        )
        clock_layout = QHBoxLayout(clock_frame)
        clock_layout.setContentsMargins(12, 8, 12, 8)

        clock_icon = QLabel("🕐")
        clock_icon.setStyleSheet("font-size: 20px;")
        clock_layout.addWidget(clock_icon)

        clock_text_layout = QVBoxLayout()
        self.clock_label = QLabel("00:00:00")
        self.clock_label.setStyleSheet(
            "font-size: 22px; font-weight: bold; color: #1e40af;"
        )
        clock_text_layout.addWidget(self.clock_label)

        self.date_label = QLabel("")
        self.date_label.setStyleSheet("font-size: 11px; color: #6b7280;")
        clock_text_layout.addWidget(self.date_label)
        clock_layout.addLayout(clock_text_layout)
        clock_layout.addStretch()

        self.next_action_label = QLabel("")
        self.next_action_label.setStyleSheet(
            "font-size: 11px; color: #2563eb; text-align: right;"
        )
        self.next_action_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        clock_layout.addWidget(self.next_action_label)

        layout.addWidget(clock_frame)

        # ---- 定时开关 ----
        self.enable_checkbox = QCheckBox("启用定时下载")
        self.enable_checkbox.setStyleSheet(
            "QCheckBox { font-size: 14px; font-weight: bold; color: #1f2937; }"
            "QCheckBox::indicator { width: 18px; height: 18px; }"
        )
        layout.addWidget(self.enable_checkbox)

        # ---- 时间设置 ----
        time_group = QGroupBox("下载时间段")
        time_group.setStyleSheet(
            "QGroupBox { font-weight: bold; color: #374151; "
            "border: 1px solid #e5e7eb; border-radius: 6px; "
            "margin-top: 6px; padding-top: 10px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; "
            "padding: 0 4px; }"
        )
        time_layout = QVBoxLayout(time_group)
        time_layout.setSpacing(12)

        # 开始时间
        start_layout = QHBoxLayout()
        start_label = QLabel("开始时间：")
        start_label.setFixedWidth(80)
        start_label.setStyleSheet("color: #374151;")
        start_layout.addWidget(start_label)

        self.start_time = QTimeEdit()
        self.start_time.setDisplayFormat("HH:mm")
        self.start_time.setFixedWidth(90)
        self.start_time.setStyleSheet(
            "QTimeEdit { border: 1px solid #d1d5db; border-radius: 4px; "
            "padding: 4px 8px; font-size: 16px; font-weight: bold; "
            "color: #1e40af; background: white; }"
        )
        start_layout.addWidget(self.start_time)
        start_layout.addWidget(QLabel("（每天到达此时间开始下载）"))
        start_layout.addStretch()
        time_layout.addLayout(start_layout)

        # 停止时间
        stop_layout = QHBoxLayout()
        stop_label = QLabel("停止时间：")
        stop_label.setFixedWidth(80)
        stop_label.setStyleSheet("color: #374151;")
        stop_layout.addWidget(stop_label)

        self.stop_time = QTimeEdit()
        self.stop_time.setDisplayFormat("HH:mm")
        self.stop_time.setFixedWidth(90)
        self.stop_time.setStyleSheet(
            "QTimeEdit { border: 1px solid #d1d5db; border-radius: 4px; "
            "padding: 4px 8px; font-size: 16px; font-weight: bold; "
            "color: #dc2626; background: white; }"
        )
        stop_layout.addWidget(self.stop_time)
        stop_layout.addWidget(QLabel("（到达此时间自动停止下载）"))
        stop_layout.addStretch()
        time_layout.addLayout(stop_layout)

        # 说明
        tip_label = QLabel(
            "提示：支持跨天时间段，例如 21:00 ~ 06:00 表示晚上9点开始，"
            "次日早上6点停止。"
        )
        tip_label.setStyleSheet(
            "color: #6b7280; font-size: 11px; padding: 4px;"
        )
        tip_label.setWordWrap(True)
        time_layout.addWidget(tip_label)

        layout.addWidget(time_group)

        # ---- 保存按钮 ----
        save_btn_layout = QHBoxLayout()
        save_btn_layout.addStretch()

        self.save_btn = QPushButton("保存定时设置")
        self.save_btn.setObjectName("primaryBtn")
        self.save_btn.setFixedHeight(36)
        self.save_btn.setMinimumWidth(120)
        self.save_btn.clicked.connect(self._save_config)
        save_btn_layout.addWidget(self.save_btn)
        layout.addLayout(save_btn_layout)

        # ---- 当前状态 ----
        status_group = QGroupBox("当前状态")
        status_group.setStyleSheet(
            "QGroupBox { font-weight: bold; color: #374151; "
            "border: 1px solid #e5e7eb; border-radius: 6px; "
            "margin-top: 6px; padding-top: 10px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; "
            "padding: 0 4px; }"
        )
        status_layout = QVBoxLayout(status_group)

        self.status_label = QLabel("定时下载：未启用")
        self.status_label.setStyleSheet(
            "color: #6b7280; font-size: 13px; padding: 4px;"
        )
        status_layout.addWidget(self.status_label)
        layout.addWidget(status_group)

        # ---- 运行日志 ----
        log_group = QGroupBox("运行日志")
        log_group.setStyleSheet(
            "QGroupBox { font-weight: bold; color: #374151; "
            "border: 1px solid #e5e7eb; border-radius: 6px; "
            "margin-top: 6px; padding-top: 10px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; "
            "padding: 0 4px; }"
        )
        log_layout = QVBoxLayout(log_group)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(140)
        self.log_text.setStyleSheet(
            "QTextEdit { border: 1px solid #e5e7eb; border-radius: 4px; "
            "background: #f9fafb; font-family: Consolas, monospace; "
            "font-size: 11px; color: #374151; }"
        )
        log_layout.addWidget(self.log_text)

        clear_log_btn = QPushButton("清空日志")
        clear_log_btn.setFixedHeight(26)
        clear_log_btn.clicked.connect(self.log_text.clear)
        log_layout.addWidget(clear_log_btn)

        layout.addWidget(log_group)
        layout.addStretch()

    def _connect_signals(self):
        self.manager.log_message.connect(self._append_log)
        self.manager.schedule_status_changed.connect(self._on_status_changed)

    def _load_config(self):
        """从manager加载当前配置"""
        cfg = self.manager.schedule_config
        self.enable_checkbox.setChecked(cfg.enabled)
        self.start_time.setTime(QTime(cfg.start_hour, cfg.start_minute))
        self.stop_time.setTime(QTime(cfg.stop_hour, cfg.stop_minute))
        self._update_status_label()

    def _save_config(self):
        """保存定时配置"""
        start = self.start_time.time()
        stop = self.stop_time.time()

        config = ScheduleConfig(
            enabled=self.enable_checkbox.isChecked(),
            start_hour=start.hour(),
            start_minute=start.minute(),
            stop_hour=stop.hour(),
            stop_minute=stop.minute(),
            repeat_daily=True,
        )
        self.manager.update_schedule(config)
        self._update_status_label()

        # 显示保存成功提示
        self.save_btn.setText("已保存 ✓")
        QTimer.singleShot(2000, lambda: self.save_btn.setText("保存定时设置"))

    def _update_status_label(self):
        cfg = self.manager.schedule_config
        if not cfg.enabled:
            self.status_label.setText("定时下载：未启用")
            self.status_label.setStyleSheet(
                "color: #6b7280; font-size: 13px; padding: 4px;"
            )
        else:
            self.status_label.setText(
                f"定时下载：已启用  "
                f"{cfg.start_hour:02d}:{cfg.start_minute:02d} ~ "
                f"{cfg.stop_hour:02d}:{cfg.stop_minute:02d}  每天重复"
            )
            self.status_label.setStyleSheet(
                "color: #16a34a; font-size: 13px; padding: 4px; font-weight: bold;"
            )

    @pyqtSlot(str)
    def _on_status_changed(self, status: str):
        self.status_label.setText(status)

    @pyqtSlot(str)
    def _append_log(self, msg: str):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{now}] {msg}")
        # 滚动到底部
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _start_clock(self):
        """启动时钟更新"""
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

    def _update_clock(self):
        """更新时钟显示"""
        now = datetime.datetime.now()
        self.clock_label.setText(now.strftime("%H:%M:%S"))
        self.date_label.setText(now.strftime("%Y年%m月%d日  %A"))

        # 计算下次动作时间
        cfg = self.manager.schedule_config
        if cfg.enabled:
            current_minutes = now.hour * 60 + now.minute
            start_minutes = cfg.start_hour * 60 + cfg.start_minute
            stop_minutes = cfg.stop_hour * 60 + cfg.stop_minute

            if start_minutes > stop_minutes:
                in_window = (current_minutes >= start_minutes or
                             current_minutes < stop_minutes)
            else:
                in_window = start_minutes <= current_minutes < stop_minutes

            if in_window:
                self.next_action_label.setText(
                    f"下载中\n停止于 {cfg.stop_hour:02d}:{cfg.stop_minute:02d}"
                )
                self.next_action_label.setStyleSheet(
                    "font-size: 11px; color: #16a34a; text-align: right;"
                )
            else:
                self.next_action_label.setText(
                    f"等待中\n开始于 {cfg.start_hour:02d}:{cfg.start_minute:02d}"
                )
                self.next_action_label.setStyleSheet(
                    "font-size: 11px; color: #2563eb; text-align: right;"
                )
        else:
            self.next_action_label.setText("定时未启用")
            self.next_action_label.setStyleSheet(
                "font-size: 11px; color: #9ca3af; text-align: right;"
            )
