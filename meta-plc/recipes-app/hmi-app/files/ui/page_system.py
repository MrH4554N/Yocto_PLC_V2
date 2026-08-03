#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trang 5 — Hệ thống: trạng thái kết nối PLC / MQTT / cảm biến / AI."""

from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from config import (AI_EVERY_N, APP_TITLE, APP_VERSION, MQTT_BROKER, MQTT_PORT,
                    PLC_PORT, POLL_INTERVAL)
from ui.theme import C
from ui.widgets import StatusPill


class SystemPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)

        card = QFrame(); card.setObjectName("Card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(20, 18, 20, 18)
        cl.setSpacing(12)
        t = QLabel("TRẠNG THÁI KẾT NỐI"); t.setObjectName("CardTitle")
        cl.addWidget(t)

        self.pills = {}
        rows = [
            ("plc",    "PLC Mitsubishi FX (Modbus RTU — " + PLC_PORT + ")"),
            ("ina219", "Cảm biến INA219 (I2C 0x40)"),
            ("mqtt",   f"MQTT Broker ({MQTT_BROKER}:{MQTT_PORT})"),
            ("ai",     "Trợ lý AI (artifact IHCS)"),
        ]
        for key, label in rows:
            r = QHBoxLayout()
            l = QLabel(label)
            l.setStyleSheet("font-size: 15px;")
            pill = StatusPill("KHÔNG RÕ")
            self.pills[key] = pill
            r.addWidget(l)
            r.addStretch()
            r.addWidget(pill)
            cl.addLayout(r)

        # Dòng mô tả chế độ AI đang chạy (đầy đủ / rút gọn / không nạp được)
        self.lbl_ai_mode = QLabel("Chế độ AI: đang nạp artifact…")
        self.lbl_ai_mode.setObjectName("CardSub")
        self.lbl_ai_mode.setWordWrap(True)
        cl.addWidget(self.lbl_ai_mode)
        lay.addWidget(card)

        info = QFrame(); info.setObjectName("Card")
        il = QVBoxLayout(info)
        il.setContentsMargins(20, 18, 20, 18)
        il.setSpacing(6)
        t2 = QLabel("THÔNG TIN"); t2.setObjectName("CardTitle")
        il.addWidget(t2)
        for txt in (f"Ứng dụng: {APP_TITLE}  v{APP_VERSION}",
                    "Nền tảng: Raspberry Pi 4 — Yocto/Poky — Weston kiosk",
                    "OTA: RAUC A/B (u-boot)",
                    f"Chu kỳ đọc: {POLL_INTERVAL}s   •   "
                    f"Chu kỳ AI: ~{int(POLL_INTERVAL * AI_EVERY_N)}s"):
            l = QLabel(txt)
            l.setStyleSheet(f"font-size: 14px; color: {C['muted']};")
            il.addWidget(l)
        lay.addWidget(info)
        lay.addStretch()

    def update_links(self, links):
        mapping = {True: ("ok", "KẾT NỐI"), False: ("err", "MẤT KẾT NỐI")}
        for key, pill in self.pills.items():
            state, text = mapping[bool(links.get(key))]
            pill.set_state(state, text)

    def update_ai_mode(self, description):
        self.lbl_ai_mode.setText(f"Chế độ AI: {description}")
