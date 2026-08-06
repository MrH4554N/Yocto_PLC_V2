#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trang 3 — Điều khiển băng tải: setpoint thủ công, preset, dừng khẩn."""

from PyQt5.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QSlider,
                             QSpinBox, QVBoxLayout, QWidget)
from PyQt5.QtCore import Qt, pyqtSignal

from config import SPEED_MAX
from core.plc_driver import speed_to_raw
from ui.theme import C
from ui.widgets import StatCard


class ControlPage(QWidget):
    write_requested = pyqtSignal(int)   # tốc độ mục tiêu

    PRESETS = [0, 200, 400, 600, 800, 950]

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)

        card = QFrame(); card.setObjectName("Card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(20, 18, 20, 18)
        cl.setSpacing(16)

        title = QLabel("ĐIỀU KHIỂN THỦ CÔNG"); title.setObjectName("CardTitle")
        cl.addWidget(title)

        # --- chọn tốc độ: spinbox + slider đồng bộ ---
        row = QHBoxLayout(); row.setSpacing(16)
        lbl = QLabel("Tốc độ mục tiêu:")
        lbl.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.spin = QSpinBox()
        self.spin.setRange(0, SPEED_MAX)
        self.spin.setFixedWidth(140)
        row.addWidget(lbl)
        row.addWidget(self.spin)
        self.lbl_raw = QLabel(self._raw_text(0))
        self.lbl_raw.setObjectName("CardSub")
        row.addWidget(self.lbl_raw)
        row.addStretch()
        cl.addLayout(row)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, SPEED_MAX)
        cl.addWidget(self.slider)

        # --- preset ---
        prow = QHBoxLayout(); prow.setSpacing(10)
        for v in self.PRESETS:
            b = QPushButton(str(v)); b.setObjectName("Ghost")
            b.clicked.connect(lambda _, val=v: self._set_target(val))
            prow.addWidget(b)
        prow.addStretch()
        cl.addLayout(prow)

        # --- nút hành động ---
        arow = QHBoxLayout(); arow.setSpacing(12)
        self.btn_write = QPushButton("GHI TỐC ĐỘ XUỐNG PLC")
        self.btn_write.setObjectName("Primary")
        self.btn_stop = QPushButton("■ DỪNG BĂNG TẢI")
        self.btn_stop.setObjectName("Danger")
        arow.addWidget(self.btn_write, stretch=2)
        arow.addWidget(self.btn_stop, stretch=1)
        cl.addLayout(arow)

        lay.addWidget(card)

        # --- thẻ trạng thái hiện hành ---
        info = QFrame(); info.setObjectName("Card")
        il = QHBoxLayout(info)
        il.setContentsMargins(20, 14, 20, 14)
        self.card_actual = StatCard("Tốc độ thực tế", "", C["red"])
        self.card_last   = StatCard("Setpoint gần nhất", "", C["blue"])
        il.addWidget(self.card_actual)
        il.addWidget(self.card_last)
        lay.addWidget(info)
        lay.addStretch()

        # sync spinbox <-> slider
        self.spin.valueChanged.connect(self._sync_from_spin)
        self.slider.valueChanged.connect(self._sync_from_slider)
        self.btn_write.clicked.connect(
            lambda: self.write_requested.emit(self.spin.value()))
        self.btn_stop.clicked.connect(lambda: self.write_requested.emit(0))

    # ------------------------------------------------------------------
    def _raw_text(self, speed):
        return f"Raw D8116: {speed_to_raw(speed)}"

    def _set_target(self, v):
        self.spin.setValue(v)

    def _sync_from_spin(self, v):
        self.slider.blockSignals(True)
        self.slider.setValue(v)
        self.slider.blockSignals(False)
        self.lbl_raw.setText(self._raw_text(v))

    def _sync_from_slider(self, v):
        self.spin.blockSignals(True)
        self.spin.setValue(v)
        self.spin.blockSignals(False)
        self.lbl_raw.setText(self._raw_text(v))

    def update_telemetry(self, d):
        self.card_actual.set_value(f"{d['speed']}")

    def show_written(self, speed, raw):
        self.card_last.set_value(f"{speed}", f"Raw D8116 = {raw}")
