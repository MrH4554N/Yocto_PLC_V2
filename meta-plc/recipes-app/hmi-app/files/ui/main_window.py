#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cửa sổ chính: khung điều hướng và nối tín hiệu giữa worker và các trang."""

import time

from PyQt5.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel,
                             QMainWindow, QPushButton, QStackedWidget,
                             QVBoxLayout, QWidget)
from PyQt5.QtCore import Qt, QTimer

from config import APP_TITLE
from core.data_worker import DataWorker
from core.plc_driver import speed_to_raw
from ui.page_ai import AIPage
from ui.page_control import ControlPage
from ui.page_overview import OverviewPage
from ui.page_system import SystemPage
from ui.page_trends import TrendsPage
from ui.theme import QSS
from ui.widgets import StatusPill


class HMIMainWindow(QMainWindow):
    # Icon dùng glyph có sẵn trong DejaVu Sans (font mặc định trên image Yocto,
    # không có emoji màu)
    NAV_ITEMS = [
        ("◉  Tổng quan",   "TỔNG QUAN"),
        ("↗  Đồ thị",      "ĐỒ THỊ THỜI GIAN THỰC"),
        ("⇅  Điều khiển",  "ĐIỀU KHIỂN BĂNG TẢI"),
        ("★  Trợ lý AI",   "TRỢ LÝ AI TỐI ƯU HÓA"),
        ("⚙  Hệ thống",    "HỆ THỐNG & KẾT NỐI"),
    ]

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setWindowFlags(Qt.FramelessWindowHint)   # kiosk mode
        self.setStyleSheet(QSS)

        self._build_ui()

        # --- luồng thu thập dữ liệu ---
        self.worker = DataWorker()
        self.worker.telemetry_update.connect(self._on_telemetry)
        self.worker.suggestion_ready.connect(self._on_suggestion)
        self.worker.advisory_status.connect(self._on_advisory_status)
        self.worker.status_update.connect(self._on_status)
        self.worker.link_update.connect(self._on_links)
        self.worker.start()

        # --- đồng hồ ---
        self._clock = QTimer(self)
        self._clock.timeout.connect(self._tick_clock)
        self._clock.start(1000)
        self._tick_clock()

    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QWidget(); root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ================= SIDEBAR =================
        sidebar = QFrame(); sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(210)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(14, 18, 14, 14)
        sl.setSpacing(6)

        logo = QLabel("⚡ AI PLC HMI"); logo.setObjectName("Logo")
        logo_sub = QLabel("Băng chuyền thông minh"); logo_sub.setObjectName("LogoSub")
        sl.addWidget(logo)
        sl.addWidget(logo_sub)
        sl.addSpacing(16)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        for i, (label, _) in enumerate(self.NAV_ITEMS):
            b = QPushButton(label)
            b.setObjectName("NavBtn")
            b.setCheckable(True)
            if i == 0:
                b.setChecked(True)
            self.nav_group.addButton(b, i)
            sl.addWidget(b)
        self.nav_group.idClicked.connect(self._switch_page)

        sl.addStretch()
        btn_exit = QPushButton("✖  Thoát ứng dụng")
        btn_exit.setObjectName("ExitBtn")
        btn_exit.clicked.connect(self.close)
        sl.addWidget(btn_exit)
        outer.addWidget(sidebar)

        # ================= KHU VỰC PHẢI =================
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)

        # --- topbar ---
        topbar = QFrame(); topbar.setObjectName("Topbar")
        topbar.setFixedHeight(58)
        tl = QHBoxLayout(topbar)
        tl.setContentsMargins(18, 0, 18, 0)
        self.lbl_page = QLabel(self.NAV_ITEMS[0][1]); self.lbl_page.setObjectName("PageTitle")
        tl.addWidget(self.lbl_page)
        tl.addStretch()
        self.pill_plc  = StatusPill("PLC")
        self.pill_mqtt = StatusPill("MQTT")
        self.pill_ai   = StatusPill("AI")
        for p in (self.pill_plc, self.pill_mqtt, self.pill_ai):
            tl.addWidget(p)
            tl.addSpacing(6)
        self.lbl_clock = QLabel("--:--"); self.lbl_clock.setObjectName("Clock")
        tl.addWidget(self.lbl_clock)
        right.addWidget(topbar)

        # --- các trang ---
        self.stack = QStackedWidget()
        self.page_overview = OverviewPage()
        self.page_trends   = TrendsPage()
        self.page_control  = ControlPage()
        self.page_ai       = AIPage()
        self.page_system   = SystemPage()
        for p in (self.page_overview, self.page_trends, self.page_control,
                  self.page_ai, self.page_system):
            self.stack.addWidget(p)
        right.addWidget(self.stack, stretch=1)

        # --- statusbar ---
        statusbar = QFrame(); statusbar.setObjectName("Statusbar")
        statusbar.setFixedHeight(34)
        bl = QHBoxLayout(statusbar)
        bl.setContentsMargins(18, 0, 18, 0)
        self.lbl_status = QLabel("Hệ thống sẵn sàng."); self.lbl_status.setObjectName("StatusMsg")
        bl.addWidget(self.lbl_status)
        bl.addStretch()
        right.addWidget(statusbar)

        outer.addLayout(right, stretch=1)

        # --- nối tín hiệu điều khiển ---
        self.page_control.write_requested.connect(self._manual_write)
        self.page_ai.apply_requested.connect(self._apply_ai)

        # cập nhật pill topbar theo link_update
        self._link_state = {}

    # ------------------------------------------------------------------
    def _switch_page(self, idx):
        self.stack.setCurrentIndex(idx)
        self.lbl_page.setText(self.NAV_ITEMS[idx][1])
        btn = self.nav_group.button(idx)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)

    def _tick_clock(self):
        self.lbl_clock.setText(time.strftime("%H:%M:%S  %d/%m/%Y"))

    # ------------------------------------------------------------------
    def _on_telemetry(self, d):
        self.page_overview.update_telemetry(d)
        self.page_trends.update_telemetry(d)
        self.page_control.update_telemetry(d)

    def _on_suggestion(self, text, speed):
        self.page_ai.show_suggestion(text, speed)
        self.page_overview.show_suggestion(text)
        self._on_status(f"AI đề xuất tốc độ {speed} — chờ phê duyệt.")

    def _on_advisory_status(self, state, text, detail):
        """AI có kết quả nhưng không phải đề xuất cần phê duyệt."""
        if state == "blocked":
            self.page_ai.show_blocked(text, detail)
            self._on_status("AI chặn đề xuất — xem trang Trợ lý AI.")
        else:
            self.page_ai.show_normal(text, detail)
        self.page_overview.show_advisory(state, text)

    def _on_status(self, msg):
        self.lbl_status.setText(time.strftime("[%H:%M:%S] ") + msg)

    def _on_links(self, links):
        self.page_system.update_links(links)
        self.page_system.update_ai_mode(self.worker.ai.describe())
        pill_map = {"plc": self.pill_plc, "mqtt": self.pill_mqtt, "ai": self.pill_ai}
        for key, pill in pill_map.items():
            pill.set_state("ok" if links.get(key) else "err", pill.text())

    # ------------------------------------------------------------------
    def _manual_write(self, speed):
        if self.worker.write_speed(speed):
            raw = speed_to_raw(speed)
            self.page_control.show_written(speed, raw)
            self.page_overview.show_applied(speed)
            self._on_status(f"Đã ghi thủ công: {speed} (Raw: {raw})")

    def _apply_ai(self):
        speed = self.page_ai.current_speed
        if self.worker.write_speed(speed):
            raw = speed_to_raw(speed)
            self.page_ai.show_applied()
            self.page_control.show_written(speed, raw)
            self.page_overview.show_applied(speed)
            self._on_status(f"Đã áp dụng đề xuất AI: {speed} (Raw: {raw})")

    # ------------------------------------------------------------------
    def closeEvent(self, event):
        self.worker.stop()
        event.accept()
