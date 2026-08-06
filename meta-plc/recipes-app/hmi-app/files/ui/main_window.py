#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cửa sổ chính: header mỏng, sáu trang, thanh điều hướng dưới cùng.

Đây cũng là nơi duy nhất giữ AlertEngine. Luồng nền chỉ phát signal; mọi thay
đổi trạng thái cảnh báo đều xảy ra trong luồng giao diện, nên không có khoá,
không có race, và trang nào cũng đọc cùng một nguồn sự thật.
"""

import time

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMainWindow,
                             QStackedWidget, QVBoxLayout, QWidget)

from config import APP_TITLE
from core.data_worker import DataWorker
from core.data_logger import describe as describe_storage
from core.plc_driver import speed_to_raw
from services.alert_engine import AI_SUGGEST, AlertEngine, apply_advisory
from ui.page_alerts import AlertsPage
from ui.page_control import ControlPage
from ui.page_devices import DevicesPage
from ui.page_monitor import MonitorPage
from ui.page_settings import SettingsPage
from ui.page_trends import TrendsPage
from ui.theme import C, QSS
from ui.widgets import NavBar, StatusDot

NAV_ITEMS = [
    ("◉", "GIÁM SÁT"),
    ("∿", "ĐỒ THỊ"),
    ("⇅", "ĐIỀU KHIỂN"),
    ("!", "CẢNH BÁO"),
    ("⚙", "THIẾT BỊ"),
    ("≡", "CÀI ĐẶT"),
]
TAB_ALERTS = 3


class HMIMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setStyleSheet(QSS)
        self.resize(1024, 600)

        self.alerts = AlertEngine(on_event=self._write_event)
        self._links = {}

        self._build_ui()
        self._start_worker()
        # Ghi sau khi có worker: nhật ký JSONL nằm trong worker, và dòng đầu
        # tiên của mỗi phiên phải là mốc khởi động để tra lại được về sau.
        self.alerts.log("info", "Khởi động hệ thống",
                        "HMI bắt đầu thu thập dữ liệu")

        self._clock = QTimer(self)
        self._clock.timeout.connect(self._tick_clock)
        self._clock.start(1000)
        self._tick_clock()

    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QWidget(); root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_header())

        self.stack = QStackedWidget()
        self.page_monitor  = MonitorPage()
        self.page_trends   = TrendsPage()
        self.page_control  = ControlPage()
        self.page_alerts   = AlertsPage()
        self.page_devices  = DevicesPage()
        self.page_settings = SettingsPage()
        for p in (self.page_monitor, self.page_trends, self.page_control,
                  self.page_alerts, self.page_devices, self.page_settings):
            self.stack.addWidget(p)
        outer.addWidget(self.stack, stretch=1)

        statusbar = QFrame(); statusbar.setObjectName("Statusbar")
        statusbar.setFixedHeight(26)
        sl = QHBoxLayout(statusbar)
        sl.setContentsMargins(14, 0, 14, 0)
        self.lbl_status = QLabel("Hệ thống sẵn sàng.")
        self.lbl_status.setObjectName("StatusMsg")
        sl.addWidget(self.lbl_status)
        outer.addWidget(statusbar)

        self.nav = NavBar(NAV_ITEMS)
        self.nav.switched.connect(self.stack.setCurrentIndex)
        outer.addWidget(self.nav)

        self.page_control.write_requested.connect(self._manual_write)
        self.page_alerts.apply_requested.connect(self._apply_ai)
        self.page_alerts.dismiss_requested.connect(self._dismiss_ai)
        self.page_settings.exit_requested.connect(self.close)
        self._refresh_alerts()

    def _build_header(self):
        header = QFrame(); header.setObjectName("Header")
        header.setFixedHeight(50)
        lay = QHBoxLayout(header)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(12)

        mark = QLabel("◉")
        mark.setStyleSheet(f"color: {C['volt']}; font-size: 17px;")
        brand = QVBoxLayout(); brand.setSpacing(0)
        b1 = QLabel("BĂNG TẢI THÔNG MINH"); b1.setObjectName("Brand")
        b2 = QLabel("IHCS · ADVISORY-ONLY"); b2.setObjectName("BrandSub")
        brand.addWidget(b1); brand.addWidget(b2)

        lay.addWidget(mark)
        lay.addLayout(brand)
        lay.addStretch()

        self.dots = {}
        for key, text in (("plc", "PLC"), ("ina219", "INA219"),
                          ("mqtt", "MQTT"), ("ai", "AI")):
            dot = StatusDot(text)
            self.dots[key] = dot
            lay.addWidget(dot)
            lay.addSpacing(4)

        self.lbl_clock = QLabel("--:--:--"); self.lbl_clock.setObjectName("Clock")
        lay.addSpacing(8)
        lay.addWidget(self.lbl_clock)
        return header

    def _start_worker(self):
        self.worker = DataWorker()
        self.worker.telemetry_update.connect(self._on_telemetry)
        self.worker.advisory_ready.connect(self._on_advisory)
        self.worker.data_lost.connect(self._on_data_lost)
        self.worker.command_update.connect(self.page_control.show_command)
        self.worker.ai_ready.connect(self._on_ai_ready)
        self.worker.status_update.connect(self._on_status)
        self.worker.link_update.connect(self._on_links)
        self.worker.start()

    # ------------------------------------------------------------------
    def _tick_clock(self):
        self.lbl_clock.setText(time.strftime("%H:%M:%S"))

    def _on_telemetry(self, d):
        self.page_monitor.update_telemetry(d)
        self.page_trends.update_telemetry(d)
        self.page_control.update_telemetry(d)

    def _on_advisory(self, advisory, view):
        apply_advisory(self.alerts, view)
        self.page_monitor.update_ai(view)
        self._update_storage()
        if view["state"] == "suggest" and view.get("speed") is not None:
            self.page_alerts.show_suggestion(view)
        else:
            self.page_alerts.clear_suggestion(
                view["text"] if view["state"] == "blocked" else None,
                view.get("detail"))
        self._refresh_alerts()

    def _on_data_lost(self, reason):
        self.page_monitor.set_data_lost(reason)
        self.alerts.raise_alert("data_input", "critical",
                                "AI tạm dừng — thiếu dữ liệu đầu vào", reason)
        self._refresh_alerts()

    def _on_ai_ready(self, info):
        self.page_devices.update_ai_mode(info.get("description", "—"))
        self.page_settings.update_model_info(
            info.get("version"), info.get("n_features"),
            info.get("warning_threshold"), info.get("critical_threshold"))
        if info.get("mode") != "full" and info.get("error"):
            self.alerts.raise_alert(
                "ai_mode",
                "critical" if info.get("mode") == "unavailable" else "warning",
                "Trợ lý AI chạy hạn chế", info["error"])
            self._refresh_alerts()

    def _on_status(self, msg):
        self.lbl_status.setText(time.strftime("[%H:%M:%S]  ") + msg)

    def _on_links(self, links):
        self.page_devices.update_links(links)
        for key, dot in self.dots.items():
            dot.set_state("ok" if links.get(key) else "err")

        # Mất/khôi phục kết nối là sự kiện đáng ghi vào nhật ký, không chỉ đổi
        # màu một cái chấm rồi thôi.
        for key, name, sev in (("plc", "PLC", "critical"),
                               ("ina219", "cảm biến dòng/áp INA219", "critical"),
                               ("mqtt", "MQTT CoreIOT", "warning")):
            now, before = bool(links.get(key)), self._links.get(key)
            if before is None:
                continue
            if before and not now:
                self.alerts.raise_alert(f"link_{key}", sev,
                                        f"Mất kết nối {name}",
                                        "kiểm tra cáp và nguồn của khối này")
            elif now and not before:
                self.alerts.clear(f"link_{key}", title=f"Đã kết nối lại {name}")
        self._links = dict(links)
        if links.get("plc") and links.get("ina219"):
            self.alerts.clear("data_input", title="Dữ liệu đầu vào đã trở lại")
        self._refresh_alerts()

    # ------------------------------------------------------------------
    def _write_event(self, kind, alert):
        """Đổ mọi thay đổi cảnh báo xuống nhật ký JSONL trên /data."""
        worker = getattr(self, "worker", None)
        log = getattr(worker, "event_log", None)
        if log is None:
            return
        log.log(kind, alert.severity, alert.title, alert.detail, key=alert.key)

    def _update_storage(self):
        """Trạng thái ghi thẻ + hàng đợi MQTT cho trang Thiết bị."""
        telemetry_log = getattr(self.worker, "telemetry_log", None)
        state, text = describe_storage(telemetry_log,
                                       getattr(self.worker, "event_log", None))
        queued = getattr(self.worker.mqtt, "queued", 0)
        if queued:
            text += f" · {queued} gói MQTT đang chờ gửi bù"
        self.page_devices.update_storage(state, text)

        # Ghi hỏng là mất dữ liệu vận hành — phải báo, không nuốt im.
        if state == "err":
            self.alerts.raise_alert("storage", "warning",
                                    "Không ghi được dữ liệu xuống thẻ",
                                    telemetry_log.error or "")
        else:
            self.alerts.clear("storage", title="Đã ghi dữ liệu trở lại")

    def _refresh_alerts(self):
        self.page_monitor.update_alerts(self.alerts)
        self.page_alerts.update_alerts(self.alerts)
        self.nav.set_badge(TAB_ALERTS, self.alerts.count("warning")
                           + (1 if self.alerts.get(AI_SUGGEST) else 0))

    def _manual_write(self, speed):
        if self.worker.write_speed(speed):
            raw = speed_to_raw(speed)
            self.page_control.show_written(speed, raw)
            self.alerts.log("info", f"Đã ghi setpoint {speed} rpm",
                            f"thủ công · D8116 = {raw}")
            self._on_status(f"Đã ghi thủ công {speed} rpm (D8116 = {raw}).")
            self._refresh_alerts()

    def _apply_ai(self, speed):
        if self.worker.write_speed(speed):
            raw = speed_to_raw(speed)
            self.page_control.show_written(speed, raw, by_ai=True)
            self.page_alerts.clear_suggestion(
                f"Đã áp dụng đề xuất {speed} rpm.", "chờ chu kỳ AI tiếp theo")
            self.alerts.clear(AI_SUGGEST,
                              title=f"Đã phê duyệt đề xuất {speed} rpm",
                              detail=f"người vận hành xác nhận · D8116 = {raw}")
            self._on_status(f"Đã áp dụng đề xuất AI: {speed} rpm (D8116 = {raw}).")
            self._refresh_alerts()

    def _dismiss_ai(self):
        self.page_alerts.clear_suggestion("Đã bỏ qua đề xuất.",
                                          "chờ chu kỳ AI tiếp theo")
        self.alerts.clear(AI_SUGGEST, title="Đã bỏ qua đề xuất của AI")
        self._refresh_alerts()

    # ------------------------------------------------------------------
    def closeEvent(self, event):
        self.worker.stop()
        event.accept()
