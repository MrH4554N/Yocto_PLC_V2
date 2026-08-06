#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cửa sổ chính — điều hướng hai tầng.

    Tầng 1  màn CHỌN HỆ THỐNG: không có thanh tab, chỉ có các thẻ hệ thống.
    Tầng 2  không gian làm việc của hệ thống đã chọn: Giám sát / Đồ thị /
            Điều khiển / Cảnh báo / Gateway / Cài đặt, kèm nút ← quay lại.

Chia hai tầng vì các tab kia chỉ có nghĩa khi đã biết đang xem MÁY NÀO. Hiện
sẵn chúng ở màn đầu chỉ dẫn người vận hành tới một trang trống, và tệ hơn: một
trang có số liệu của máy mà họ tưởng mình chưa chọn.

Đây cũng là nơi duy nhất giữ AlertEngine. Luồng nền chỉ phát signal; mọi thay
đổi trạng thái cảnh báo đều xảy ra trong luồng giao diện, nên không có khoá,
không có race, và trang nào cũng đọc cùng một nguồn sự thật.
"""

import time

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMainWindow,
                             QPushButton, QStackedWidget, QVBoxLayout,
                             QWidget)

from config import APP_TITLE, MQTT_BROKER, MQTT_PORT
from core.data_worker import DataWorker
from core.data_logger import describe as describe_storage
from core.plc_driver import speed_to_raw
from services.alert_engine import AI_SUGGEST, AlertEngine, apply_advisory
from ui.page_alerts import AlertsPage
from ui.page_control import ControlPage
from ui.page_gateway import GatewayPage
from ui.page_monitor import MonitorPage
from ui.page_settings import SettingsPage
from ui.page_stations import StationsPage
from ui.page_trends import TrendsPage
from ui.theme import C, QSS
from ui.widgets import NavBar, StatusDot

# Thanh tab của TẦNG 2. Màn chọn hệ thống nằm ngoài danh sách này: nó là
# stack index 0, còn nav index i ứng với stack index i + 1.
NAV_ITEMS = [
    ("◉", "GIÁM SÁT"),
    ("∿", "ĐỒ THỊ"),
    ("⇅", "ĐIỀU KHIỂN"),
    ("!", "CẢNH BÁO"),
    ("↑", "GATEWAY"),
    ("≡", "CÀI ĐẶT"),
]
PAGE_PICKER = 0
NAV_MONITOR = 0
TAB_ALERTS = 3

# Cảnh báo đã xử lý rụng dần khỏi màn hình; quét lại mỗi chừng này giây.
PRUNE_INTERVAL_MS = 3000


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

        # Cảnh báo đã xử lý phải TỰ rụng kể cả khi không có sự kiện mới nào,
        # nếu không thì dòng "đã trở lại bình thường" nằm lại tới sáng.
        self._pruner = QTimer(self)
        self._pruner.timeout.connect(self._prune_alerts)
        self._pruner.start(PRUNE_INTERVAL_MS)

    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QWidget(); root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_header())

        self.stack = QStackedWidget()
        self.page_stations = StationsPage()
        self.page_monitor  = MonitorPage()
        self.page_trends   = TrendsPage()
        self.page_control  = ControlPage()
        self.page_alerts   = AlertsPage()
        self.page_gateway  = GatewayPage()
        self.page_settings = SettingsPage()
        for p in (self.page_stations, self.page_monitor, self.page_trends,
                  self.page_control, self.page_alerts, self.page_gateway,
                  self.page_settings):
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
        self.nav.switched.connect(lambda i: self.stack.setCurrentIndex(i + 1))
        outer.addWidget(self.nav)
        self.statusbar = statusbar
        self._show_picker()

        self.page_stations.station_selected.connect(self._select_station)
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

        # Nút quay lại chỉ hiện khi đang ở trong một hệ thống — ở màn chọn thì
        # không có gì để quay về.
        self.btn_back = QPushButton("←")
        self.btn_back.setObjectName("Chip")
        self.btn_back.setFixedSize(44, 32)
        self.btn_back.clicked.connect(self._show_picker)
        self.btn_back.hide()

        mark = QLabel("◉")
        mark.setStyleSheet(f"color: {C['volt']}; font-size: 17px;")
        brand = QVBoxLayout(); brand.setSpacing(0)
        self.lbl_brand = QLabel("BĂNG TẢI THÔNG MINH")
        self.lbl_brand.setObjectName("Brand")
        self.lbl_brand_sub = QLabel("IHCS · ADVISORY-ONLY")
        self.lbl_brand_sub.setObjectName("BrandSub")
        brand.addWidget(self.lbl_brand); brand.addWidget(self.lbl_brand_sub)

        lay.addWidget(self.btn_back)
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
        self.worker.network_update.connect(self._on_network)
        self.worker.station_changed.connect(self._on_station_changed)
        self.worker.status_update.connect(self._on_status)
        self.worker.link_update.connect(self._on_links)
        self.worker.start()

    # ------------------------------------------------------------------
    def _show_picker(self):
        """Về màn chọn hệ thống: giấu thanh tab để không ai bấm nhầm vào một
        trang đang nói về hệ thống mà họ tưởng chưa chọn."""
        self.stack.setCurrentIndex(PAGE_PICKER)
        self.nav.hide()
        self.btn_back.hide()
        self.lbl_brand.setText("BĂNG TẢI THÔNG MINH")
        self.lbl_brand_sub.setText("IHCS · ADVISORY-ONLY")

    def _enter_workspace(self, station=None):
        """Vào không gian làm việc của hệ thống đang chọn."""
        self.nav.show()
        self.btn_back.show()
        self.nav.select(NAV_MONITOR)
        self.stack.setCurrentIndex(NAV_MONITOR + 1)
        station = station or getattr(self.worker, "station", None)
        if station is not None:
            self.lbl_brand.setText(station.name.upper())
            self.lbl_brand_sub.setText(station.summary)

    def _tick_clock(self):
        self.lbl_clock.setText(time.strftime("%H:%M:%S"))

    def _on_telemetry(self, d):
        self.page_monitor.update_telemetry(d)
        self.page_trends.update_telemetry(d)
        self.page_control.update_telemetry(d)
        self.page_stations.update_telemetry(self.worker.station.id, d)

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
        self.page_settings.update_ai_mode(info.get("description", "—"))
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

    def _on_network(self, info):
        self.page_gateway.update_network(info)
        self.page_gateway.update_uplink(
            MQTT_BROKER, MQTT_PORT, info.get("mqtt_connected"),
            info.get("broker_reachable"), info.get("mqtt_sent", 0),
            info.get("mqtt_queued", 0), info.get("mqtt_dropped", 0))

    def _on_station_changed(self, station_id):
        self.page_stations.update_registry(self.worker.registry, self._links)
        self.page_gateway.update_devices(self.worker.registry, self._links)
        station = self.worker.registry.get(station_id)
        if station:
            self.alerts.log("info", f"Chuyển sang trạm {station.name}",
                            f"{station.summary}")
            self._refresh_alerts()

    def _select_station(self, station_id):
        station = self.worker.registry.get(station_id)
        if station_id == self.worker.station.id:
            self._enter_workspace(station)        # chọn lại chính nó: vào luôn
        elif self.worker.select_station(station_id):
            self._enter_workspace(station)

    def _on_links(self, links):
        self.page_stations.update_registry(self.worker.registry, links)
        self.page_gateway.update_devices(self.worker.registry, links)
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
        self.page_gateway.update_storage(state, text)

        # Ghi hỏng là mất dữ liệu vận hành — phải báo, không nuốt im.
        if state == "err":
            self.alerts.raise_alert("storage", "warning",
                                    "Không ghi được dữ liệu xuống thẻ",
                                    telemetry_log.error or "")
        else:
            self.alerts.clear("storage", title="Đã ghi dữ liệu trở lại")

    def _prune_alerts(self):
        if self.alerts.prune():
            self._refresh_alerts()
        else:
            # Không có gì hết hạn, nhưng độ mờ vẫn tăng theo thời gian.
            self.page_monitor.update_alerts(self.alerts)

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
