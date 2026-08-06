#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trang GIÁM SÁT — bốn thẻ số + envelope tải + cảnh báo gần nhất.

Đây là trang mặc định, cũng là trang người vận hành nhìn nhiều nhất, nên nó
phải trả lời được ba câu hỏi trong một cái liếc: đang chạy bao nhiêu, còn cách
giới hạn bao xa, và AI có đang thấy gì bất thường không.
"""

import time

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QVBoxLayout, QWidget)

from config import SPEED_MAX
from ui.theme import C
from ui.widgets import AlertRow, BarMeter, MetricCard, StatusPill, clear_layout

# Giới hạn dòng điện an toàn của rig (system_parameters.json: max_safe_current_a)
CURRENT_LIMIT_A = 0.15
SUPPLY_VOLTAGE_V = 24.8


class MonitorPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(12)

        # ---------------- hàng thẻ số ----------------
        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.card_speed = MetricCard("Tốc độ", "rpm", C["speed"], "{:.0f}")
        self.card_volt  = MetricCard("Điện áp", "V",  C["volt"],  "{:.1f}")
        self.card_curr  = MetricCard("Dòng điện", "A", C["curr"], "{:.3f}")
        self.card_power = MetricCard("Công suất", "W", C["power"], "{:.2f}")
        for c in (self.card_speed, self.card_volt, self.card_curr, self.card_power):
            c.setMinimumHeight(168)
            cards.addWidget(c)
        root.addLayout(cards, stretch=3)

        # ---------------- hàng dưới ----------------
        bottom = QHBoxLayout()
        bottom.setSpacing(12)
        bottom.addWidget(self._build_envelope(), stretch=3)
        bottom.addWidget(self._build_alerts(), stretch=4)
        root.addLayout(bottom, stretch=2)

        # min/max tích luỹ để dòng phụ của thẻ có nội dung
        self._stats = {}

    # ------------------------------------------------------------------
    def _build_envelope(self):
        card = QFrame(); card.setObjectName("Card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(6)

        head = QHBoxLayout()
        t = QLabel("ENVELOPE TẢI"); t.setObjectName("CardTitle")
        self.pill_sampling = StatusPill("ĐANG LẤY MẪU")
        head.addWidget(t)
        head.addStretch()
        head.addWidget(self.pill_sampling)
        lay.addLayout(head)

        heading = QLabel("Dư địa vận hành"); heading.setObjectName("CardHeading")
        lay.addWidget(heading)
        lay.addSpacing(2)

        # Không đặt ngưỡng cảnh báo cho tốc độ: rig chạy hết tầm ở ~980 rpm là
        # trạng thái vận hành BÌNH THƯỜNG, tô đỏ nó chỉ dạy người vận hành bỏ
        # qua màu đỏ. Chỉ dòng điện mới có giới hạn an toàn thật.
        self.bar_speed = BarMeter("rpm", "rpm", C["speed"], 0, SPEED_MAX, fmt="{:.0f}")
        self.bar_curr = BarMeter("A", "A", C["curr"], 0, CURRENT_LIMIT_A,
                                 warn_at=CURRENT_LIMIT_A * 0.8, fmt="{:.3f}")
        self.bar_volt = BarMeter("V", "V", C["volt"], 0, SUPPLY_VOLTAGE_V, fmt="{:.1f}")
        for b in (self.bar_speed, self.bar_curr, self.bar_volt):
            lay.addWidget(b)
        lay.addStretch()
        return card

    def _build_alerts(self):
        card = QFrame(); card.setObjectName("Card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(6)

        head = QHBoxLayout()
        t = QLabel("TRỢ LÝ AI"); t.setObjectName("CardTitle")
        self.pill_ai = StatusPill("ĐANG KHỞI ĐỘNG")
        head.addWidget(t)
        head.addStretch()
        head.addWidget(self.pill_ai)
        lay.addLayout(head)

        self.lbl_ai = QLabel("Đang nạp mô hình…")
        self.lbl_ai.setObjectName("CardHeading")
        self.lbl_ai.setWordWrap(True)
        lay.addWidget(self.lbl_ai)

        # Một dòng duy nhất, không xuống dòng: dòng chi tiết dài (điểm bất
        # thường + lý do chặn) mà tự xuống dòng sẽ đẩy cả trang cao lên và tràn
        # khỏi màn 1024×600.
        self.lbl_ai_sub = QLabel(" ")
        self.lbl_ai_sub.setObjectName("CardSub")
        lay.addWidget(self.lbl_ai_sub)
        lay.addSpacing(4)

        self.alert_box = QVBoxLayout()
        self.alert_box.setSpacing(6)
        lay.addLayout(self.alert_box)
        lay.addStretch()
        return card

    # ------------------------------------------------------------------
    def update_telemetry(self, d):
        ts = d.get("ts", time.time())
        for key, card, value in (
                ("speed", self.card_speed, d["speed"]),
                ("voltage", self.card_volt, d["voltage"]),
                ("current", self.card_curr, d["current"]),
                ("power", self.card_power, d["power"])):
            lo, hi = self._stats.get(key, (value, value))
            lo, hi = min(lo, value), max(hi, value)
            self._stats[key] = (lo, hi)
            card.set_value(value, sub=self._sub_text(key, lo, hi), ts=ts)

        self.bar_speed.set_value(d["speed"])
        self.bar_curr.set_value(d["current"])
        self.bar_volt.set_value(d["voltage"])
        self.pill_sampling.set_state("ok", "ĐANG LẤY MẪU")

    @staticmethod
    def _sub_text(key, lo, hi):
        if key == "speed":
            return f"min {lo:.0f} · max {hi:.0f} rpm"
        if key == "voltage":
            return f"min {lo:.1f} · max {hi:.1f} V"
        if key == "current":
            return f"giới hạn {CURRENT_LIMIT_A:.2f} A · max {hi:.3f}"
        return f"min {lo:.2f} · max {hi:.2f} W"

    def set_data_lost(self, reason):
        for c in (self.card_speed, self.card_volt, self.card_curr, self.card_power):
            c.set_stale()
        for b in (self.bar_speed, self.bar_curr, self.bar_volt):
            b.set_value(None)
        self.pill_sampling.set_state("err", "MẤT DỮ LIỆU")
        self.lbl_ai.setText("AI tạm dừng — thiếu dữ liệu đầu vào")
        self.lbl_ai_sub.setText(reason)
        self.pill_ai.set_state("err", "TẠM DỪNG")

    # ------------------------------------------------------------------
    def update_ai(self, view):
        """Cập nhật ô trợ lý AI từ một chu kỳ advisory."""
        level = view.get("level")
        pill = {"normal": ("ok", "BÌNH THƯỜNG"),
                "warning": ("warn", "CHỚM BẤT THƯỜNG"),
                "critical": ("err", "BẤT THƯỜNG"),
                "warmup": ("info", "ĐANG THU THẬP"),
                "unknown": ("off", "CHƯA CHẤM ĐIỂM")}.get(level, ("off", "—"))
        self.pill_ai.set_state(*pill)

        if view["state"] == "suggest":
            self.lbl_ai.setText(f"Đề xuất setpoint {view['speed']} rpm")
        elif level == "normal":
            # Câu khẳng định, có mốc giờ: đây là bằng chứng AI còn sống chứ
            # không phải một ô trống im lặng.
            self.lbl_ai.setText("Vận hành bình thường")
        else:
            self.lbl_ai.setText(view["text"].split("\n")[0])
        self.lbl_ai_sub.setText(f"[{time.strftime('%H:%M:%S')}]  {view.get('detail', '')}")

    def update_alerts(self, engine):
        """Vẽ lại 3 dòng cảnh báo gần nhất."""
        clear_layout(self.alert_box)
        for alert in engine.recent(3):
            self.alert_box.addWidget(AlertRow(alert, compact=True))
