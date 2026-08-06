#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trang THIẾT BỊ — tình trạng từng khối phần cứng và trợ lý AI.

Mỗi dòng nói rõ khối đó nối vào đâu, để khi mất kết nối người sửa biết đi cắm
lại cáp nào chứ không phải đoán.
"""

from PyQt5.QtWidgets import (QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget)

from config import (INA_ADDRESS, MQTT_BROKER, MQTT_PORT, PLC_BAUDRATE,
                    PLC_PORT)
from ui.theme import C
from ui.widgets import StatusPill


class DevicesPage(QWidget):
    ROWS = [
        ("plc",    "PLC Mitsubishi FX", f"Computer Link · {PLC_PORT} · {PLC_BAUDRATE} bps"),
        ("ina219", "Cảm biến dòng/áp INA219", f"I²C · địa chỉ 0x{INA_ADDRESS:02X}"),
        ("mqtt",   "MQTT CoreIOT", f"{MQTT_BROKER}:{MQTT_PORT}"),
        ("ai",     "Trợ lý AI (artifact IHCS)", "LSTM bất thường + MPC đề xuất setpoint"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(12)

        card = QFrame(); card.setObjectName("Card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 13, 16, 13)
        lay.setSpacing(10)
        t = QLabel("KẾT NỐI"); t.setObjectName("CardTitle")
        lay.addWidget(t)

        self.pills = {}
        for key, name, sub in self.ROWS:
            row = QFrame(); row.setObjectName("Sunken")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(13, 10, 13, 10)
            box = QVBoxLayout(); box.setSpacing(1)
            lbl = QLabel(name)
            lbl.setStyleSheet("font-size: 14px; font-weight: 700;")
            sub_lbl = QLabel(sub); sub_lbl.setObjectName("CardSub")
            box.addWidget(lbl); box.addWidget(sub_lbl)
            pill = StatusPill("KHÔNG RÕ")
            self.pills[key] = pill
            rl.addLayout(box, stretch=1)
            rl.addWidget(pill)
            lay.addWidget(row)
        root.addWidget(card)

        ai_card = QFrame(); ai_card.setObjectName("Card")
        al = QVBoxLayout(ai_card)
        al.setContentsMargins(16, 13, 16, 13)
        al.setSpacing(6)
        t2 = QLabel("CHẾ ĐỘ TRỢ LÝ AI"); t2.setObjectName("CardTitle")
        self.lbl_mode = QLabel("đang nạp artifact…")
        self.lbl_mode.setWordWrap(True)
        self.lbl_mode.setStyleSheet("font-size: 14px;")
        al.addWidget(t2)
        al.addWidget(self.lbl_mode)
        root.addWidget(ai_card)
        root.addStretch()

    def update_links(self, links):
        for key, pill in self.pills.items():
            ok = bool(links.get(key))
            pill.set_state("ok" if ok else "err",
                           "KẾT NỐI" if ok else "MẤT KẾT NỐI")

    def update_ai_mode(self, description):
        self.lbl_mode.setText(description)
