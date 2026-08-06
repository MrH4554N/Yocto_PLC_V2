#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trang 1 — Tổng quan: thẻ KPI + sparkline tốc độ + tóm tắt AI."""

import time
from collections import deque

from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from PyQt5.QtCore import Qt

from config import TREND_POINTS
from ui.theme import C
from ui.widgets import StatCard, StatusPill, make_plot


class OverviewPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)

        # --- Hàng thẻ KPI ---
        cards = QHBoxLayout()
        cards.setSpacing(14)
        self.card_speed   = StatCard("Tốc độ thực tế (D120)", "",  C["red"])
        self.card_voltage = StatCard("Điện áp",  "V", C["yellow"])
        self.card_current = StatCard("Dòng điện", "A", C["cyan"])
        self.card_power   = StatCard("Công suất", "W", C["green"])
        for c_ in (self.card_speed, self.card_voltage,
                   self.card_current, self.card_power):
            cards.addWidget(c_)
        lay.addLayout(cards)

        # --- Hàng dưới: sparkline tốc độ + tóm tắt AI ---
        bottom = QHBoxLayout()
        bottom.setSpacing(14)

        spark_card = QFrame(); spark_card.setObjectName("Card")
        sl = QVBoxLayout(spark_card)
        sl.setContentsMargins(16, 14, 16, 14)
        t = QLabel("XU HƯỚNG TỐC ĐỘ (2 PHÚT)"); t.setObjectName("CardTitle")
        sl.addWidget(t)
        self.spark, self.spark_curve = make_plot("", C["red"])
        self.spark.setMinimumHeight(180)
        sl.addWidget(self.spark)
        bottom.addWidget(spark_card, stretch=3)

        ai_card = QFrame(); ai_card.setObjectName("Card")
        al = QVBoxLayout(ai_card)
        al.setContentsMargins(16, 14, 16, 14)
        al.setSpacing(10)
        t2 = QLabel("TRỢ LÝ AI"); t2.setObjectName("CardTitle")
        self.ai_state = StatusPill("ĐANG THU THẬP DỮ LIỆU")
        self.ai_text = QLabel("Chưa có đề xuất.")
        self.ai_text.setWordWrap(True)
        self.ai_text.setStyleSheet("font-size: 14px;")
        # Dòng điểm bất thường + thời điểm chu kỳ AI gần nhất. Không có nó thì
        # trạng thái bình thường trông y hệt lúc AI đã chết.
        self.ai_detail = QLabel(" ")
        self.ai_detail.setObjectName("CardSub")
        self.ai_detail.setWordWrap(True)
        self.lbl_setpoint = QLabel("Setpoint đã ghi: --")
        self.lbl_setpoint.setObjectName("CardSub")
        al.addWidget(t2)
        al.addWidget(self.ai_state, alignment=Qt.AlignLeft)
        al.addWidget(self.ai_text)
        al.addWidget(self.ai_detail)
        al.addStretch()
        al.addWidget(self.lbl_setpoint)
        bottom.addWidget(ai_card, stretch=2)

        lay.addLayout(bottom)

        self._speed_buf = deque(maxlen=TREND_POINTS)

    def update_telemetry(self, d):
        self.card_speed.set_value(f"{d['speed']}")
        self.card_voltage.set_value(f"{d['voltage']:.1f}")
        self.card_current.set_value(f"{d['current']:.2f}")
        self.card_power.set_value(f"{d['power']:.1f}")
        self._speed_buf.append(d["speed"])
        self.spark_curve.setData(list(self._speed_buf))

    def show_suggestion(self, text, detail=None):
        self.ai_state.set_state("warn", "CÓ ĐỀ XUẤT MỚI")
        self.ai_text.setText(text + "\n→ Vào trang Trợ lý AI để áp dụng.")
        self._set_detail(detail)

    def show_advisory(self, state, text, detail=None):
        """Cập nhật khi AI không có đề xuất: bình thường / khởi động / bị chặn."""
        if state == "blocked":
            self.ai_state.set_state("err", "CẢNH BÁO — ĐÃ CHẶN ĐỀ XUẤT")
        elif state == "warmup":
            self.ai_state.set_state("warn", "ĐANG THU THẬP DỮ LIỆU")
        else:
            self.ai_state.set_state("ok", "VẬN HÀNH BÌNH THƯỜNG")
        self.ai_text.setText(text)
        self._set_detail(detail)

    def show_applied(self, speed):
        self.ai_state.set_state("ok", "ĐÃ ÁP DỤNG")
        self.lbl_setpoint.setText(f"Setpoint đã ghi: {speed}")

    def _set_detail(self, detail):
        """Ghi kèm giờ của chu kỳ AI: đó là bằng chứng AI vẫn còn chạy."""
        stamp = time.strftime("%H:%M:%S")
        self.ai_detail.setText(f"[{stamp}]  {detail}" if detail else f"[{stamp}]")
