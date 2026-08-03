#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Widget dùng chung giữa các trang."""

from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout
from PyQt5.QtCore import Qt
import pyqtgraph as pg

from ui.theme import C


class StatCard(QFrame):
    """Thẻ KPI: tiêu đề nhỏ + giá trị lớn + dòng phụ."""

    def __init__(self, title, unit="", accent=C["blue"], parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.unit = unit
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(4)

        self.lbl_title = QLabel(title.upper())
        self.lbl_title.setObjectName("CardTitle")
        self.lbl_value = QLabel("--")
        self.lbl_value.setStyleSheet(
            f"font-size: 30px; font-weight: 800; color: {accent};")
        self.lbl_sub = QLabel(" ")
        self.lbl_sub.setObjectName("CardSub")

        lay.addWidget(self.lbl_title)
        lay.addWidget(self.lbl_value)
        lay.addWidget(self.lbl_sub)

    def set_value(self, text, sub=None):
        self.lbl_value.setText(f"{text}{(' ' + self.unit) if self.unit else ''}")
        if sub is not None:
            self.lbl_sub.setText(sub)


class StatusPill(QLabel):
    """Nhãn trạng thái nhỏ dạng viên thuốc: OK / LỖI / N/A."""

    STYLES = {
        "ok":   (C["green"],  "#0d2818"),
        "warn": (C["yellow"], "#2b2111"),
        "err":  (C["red"],    "#2d1214"),
        "off":  (C["muted"],  C["border"]),
    }

    def __init__(self, text="--", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.set_state("off", text)

    def set_state(self, state, text=None):
        fg, bg = self.STYLES.get(state, self.STYLES["off"])
        if text is not None:
            self.setText(text)
        self.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border-radius: 11px;"
            f"padding: 4px 12px; font-size: 12px; font-weight: 700;")


def make_plot(title, color):
    """Tạo 1 PlotWidget pyqtgraph theo theme chung."""
    pw = pg.PlotWidget()
    pw.setBackground(C["panel"])
    pw.setTitle(title, color=C["muted"], size="11pt")
    pw.showGrid(x=True, y=True, alpha=0.15)
    pw.getAxis("left").setPen(pg.mkPen(C["border"]))
    pw.getAxis("left").setTextPen(pg.mkPen(C["muted"]))
    pw.getAxis("bottom").setPen(pg.mkPen(C["border"]))
    pw.getAxis("bottom").setTextPen(pg.mkPen(C["muted"]))
    pw.setMouseEnabled(x=False, y=False)
    pw.setMenuEnabled(False)
    pw.hideButtons()
    curve = pw.plot(pen=pg.mkPen(color, width=2))
    return pw, curve
