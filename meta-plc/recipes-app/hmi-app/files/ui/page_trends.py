#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trang ĐỒ THỊ — bốn kênh đo, cửa sổ trượt chọn được, kèm đọc số.

Bản cũ nhồi mọi mẫu từ lúc khởi động vào một khung cố định (deque 240 điểm,
trục X là số giây kể từ lúc chạy). Càng chạy lâu, đường càng bị nén cho tới khi
thành một vệt răng cưa không đọc được — đúng cái sai bạn nhìn thấy.

Bản này giữ dữ liệu theo THỜI GIAN THẬT và chỉ vẽ cửa sổ đang chọn:
  • trục X luôn là "bao nhiêu giây trước", 0 ở mép phải;
  • trục Y tự co giãn theo dữ liệu TRONG cửa sổ, có đệm 5%, nên một dao động
    0,5 V vẫn nhìn thấy được thay vì thành đường thẳng;
  • mỗi kênh có bốn số đọc kèm: hiện tại / nhỏ nhất / lớn nhất / trung bình,
    tính trên đúng cửa sổ đang xem.
"""

import time
from collections import deque

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QButtonGroup, QFrame, QGridLayout, QHBoxLayout,
                             QLabel, QPushButton, QVBoxLayout, QWidget)

from ui.theme import C, MONO
from ui.widgets import make_plot

# Các cửa sổ chọn được (nhãn, số giây). 2 phút là mặc định: đủ thấy một chu kỳ
# tải của băng tải mà vẫn còn chi tiết từng mẫu.
WINDOWS = [("1 PHÚT", 60), ("2 PHÚT", 120), ("5 PHÚT", 300), ("15 PHÚT", 900)]
DEFAULT_WINDOW_S = 120
MAX_WINDOW_S = max(w for _, w in WINDOWS)


class TrendsPage(QWidget):
    # (khoá, tên, đơn vị, màu, định dạng, biên độ tối thiểu của trục Y)
    # Biên độ tối thiểu để lúc máy nằm im, trục không co xuống bằng dải nhiễu
    # và phóng một dao động 0,05 V thành đồ thị răng cưa dựng đứng.
    CHANNELS = [
        ("speed",   "Tốc độ",    "rpm", C["speed"], "{:.0f}", 50.0),
        ("voltage", "Điện áp",   "V",   C["volt"],  "{:.1f}", 2.0),
        ("current", "Dòng điện", "A",   C["curr"],  "{:.3f}", 0.02),
        ("power",   "Công suất", "W",   C["power"], "{:.2f}", 0.5),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.window_s = DEFAULT_WINDOW_S

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(10)
        root.addLayout(self._build_toolbar())

        grid = QGridLayout()
        grid.setSpacing(10)
        self.plots, self.curves, self.readouts = {}, {}, {}
        for i, (key, name, unit, color, fmt, span) in enumerate(self.CHANNELS):
            grid.addWidget(self._build_channel(key, name, unit, color, fmt, span),
                           i // 2, i % 2)
        root.addLayout(grid, stretch=1)

        # Bộ đệm theo thời gian thật: giữ dư tới cửa sổ lớn nhất để đổi cửa sổ
        # là thấy ngay lịch sử, không phải chờ gom lại từ đầu.
        self.buf = {key: deque() for key, *_ in self.CHANNELS}
        self.buf_t = deque()

    # ------------------------------------------------------------------
    def _build_toolbar(self):
        bar = QHBoxLayout()
        bar.setSpacing(8)
        lbl = QLabel("CỬA SỔ")
        lbl.setObjectName("CardTitle")
        bar.addWidget(lbl)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for i, (text, secs) in enumerate(WINDOWS):
            b = QPushButton(text)
            b.setObjectName("Chip")
            b.setCheckable(True)
            b.setChecked(secs == DEFAULT_WINDOW_S)
            b.setMinimumHeight(32)
            b.clicked.connect(lambda _, s=secs: self._set_window(s))
            self._group.addButton(b, i)
            bar.addWidget(b)

        bar.addStretch()
        self.lbl_span = QLabel()
        self.lbl_span.setObjectName("CardSub")
        bar.addWidget(self.lbl_span)
        return bar

    def _build_channel(self, key, name, unit, color, fmt, min_span=0.0):
        card = QFrame(); card.setObjectName("Card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(14)
        title = QLabel(f"{name.upper()}  ({unit})")
        title.setObjectName("CardTitle")
        head.addWidget(title)
        head.addStretch()

        # Bốn số đọc: hiện tại nổi bật, ba số thống kê nhỏ hơn bên cạnh.
        cur = QLabel("--")
        cur.setStyleSheet(
            f"font-family: {MONO}; font-size: 21px; font-weight: 800; color: {color};")
        stats = QLabel("min -- · max -- · TB --")
        stats.setObjectName("CardSub")
        head.addWidget(stats, alignment=Qt.AlignBottom)
        head.addWidget(cur)
        lay.addLayout(head)

        plot, curve = make_plot("", color)
        plot.setMinimumHeight(120)
        lay.addWidget(plot, stretch=1)

        self.plots[key] = plot
        self.curves[key] = curve
        self.readouts[key] = (cur, stats, fmt, min_span)
        return card

    # ------------------------------------------------------------------
    def _set_window(self, secs):
        self.window_s = secs
        self._redraw()

    def update_telemetry(self, d):
        ts = d.get("ts", time.time())
        self.buf_t.append(ts)
        for key, *_ in self.CHANNELS:
            self.buf[key].append(float(d[key]))

        cutoff = ts - MAX_WINDOW_S
        while self.buf_t and self.buf_t[0] < cutoff:
            self.buf_t.popleft()
            for key, *_ in self.CHANNELS:
                self.buf[key].popleft()

        if self.isVisible():
            self._redraw()

    def _redraw(self):
        if not self.buf_t:
            return
        now = self.buf_t[-1]
        start = now - self.window_s

        times = list(self.buf_t)
        first = 0
        for i, t in enumerate(times):
            if t >= start:
                first = i
                break
        # Trục X: giây trước hiện tại (âm), 0 ở mép phải — đọc "cách đây bao lâu"
        # trực tiếp, không phải trừ nhẩm từ mốc khởi động.
        xs = [t - now for t in times[first:]]

        for key, *_ in self.CHANNELS:
            ys = list(self.buf[key])[first:]
            self.curves[key].setData(xs, ys)
            plot = self.plots[key]
            plot.setXRange(-self.window_s, 0, padding=0)
            if ys:
                lo, hi = min(ys), max(ys)
                cur, stats, fmt, min_span = self.readouts[key]
                span = max(hi - lo, min_span)
                mid = (hi + lo) / 2.0
                lo_ax, hi_ax = mid - span / 2.0, mid + span / 2.0
                pad = span * 0.05
                plot.setYRange(lo_ax - pad, hi_ax + pad, padding=0)
                cur.setText(fmt.format(ys[-1]))
                stats.setText(f"min {fmt.format(lo)} · max {fmt.format(hi)} · "
                              f"TB {fmt.format(sum(ys) / len(ys))}")

        span = times[-1] - times[first]
        self.lbl_span.setText(
            f"{len(times) - first} mẫu · {span:.0f} s dữ liệu · trục X: giây trước hiện tại")

    def showEvent(self, event):
        super().showEvent(event)
        self._redraw()
