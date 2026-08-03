#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trang 2 — Đồ thị thời gian thực: tốc độ / điện áp / dòng điện / công suất."""

import time
from collections import deque

from PyQt5.QtWidgets import QGridLayout, QWidget

from config import TREND_POINTS
from ui.theme import C
from ui.widgets import make_plot


class TrendsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QGridLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)

        self.p_speed, self.c_speed = make_plot("Tốc độ thực tế (D120)", C["red"])
        self.p_volt,  self.c_volt  = make_plot("Điện áp (V)",           C["yellow"])
        self.p_curr,  self.c_curr  = make_plot("Dòng điện (A)",         C["cyan"])
        self.p_power, self.c_power = make_plot("Công suất (W)",         C["green"])

        # Tốc độ chiếm cả hàng trên; 3 đồ thị điện chia hàng dưới
        lay.addWidget(self.p_speed, 0, 0, 1, 3)
        lay.addWidget(self.p_volt,  1, 0)
        lay.addWidget(self.p_curr,  1, 1)
        lay.addWidget(self.p_power, 1, 2)
        lay.setRowStretch(0, 3)
        lay.setRowStretch(1, 2)

        self.t0 = time.time()
        self.buf_t     = deque(maxlen=TREND_POINTS)
        self.buf_speed = deque(maxlen=TREND_POINTS)
        self.buf_volt  = deque(maxlen=TREND_POINTS)
        self.buf_curr  = deque(maxlen=TREND_POINTS)
        self.buf_power = deque(maxlen=TREND_POINTS)

    def update_telemetry(self, d):
        self.buf_t.append(d.get("ts", time.time()) - self.t0)
        self.buf_speed.append(d["speed"])
        self.buf_volt.append(d["voltage"])
        self.buf_curr.append(d["current"])
        self.buf_power.append(d["power"])

        # Chỉ vẽ lại khi trang đang hiển thị (tiết kiệm CPU cho RPi)
        if self.isVisible():
            self._redraw()

    def _redraw(self):
        t = list(self.buf_t)
        self.c_speed.setData(t, list(self.buf_speed))
        self.c_volt.setData(t, list(self.buf_volt))
        self.c_curr.setData(t, list(self.buf_curr))
        self.c_power.setData(t, list(self.buf_power))

    def showEvent(self, event):
        # Vẽ ngay dữ liệu đã tích lũy khi người dùng mở trang
        super().showEvent(event)
        self._redraw()
