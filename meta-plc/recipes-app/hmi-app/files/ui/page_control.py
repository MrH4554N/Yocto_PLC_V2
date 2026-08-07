#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trang ĐIỀU KHIỂN — đặt setpoint thủ công và dừng băng tải.

Ô "giá trị thanh ghi" hiện raw D8116 tương ứng, tra qua bảng hiệu chuẩn thật
(command_map.py) chứ không phải hệ số tuyến tính: thanh ghi điều khiển điện áp
và bão hoà ở rail nguồn, nên người vận hành cần thấy con số sẽ thực sự được ghi.
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QSlider,
                             QSpinBox, QVBoxLayout, QWidget)

from config import SPEED_MAX
from core.plc_driver import raw_to_speed, speed_to_raw
from ui.theme import C, MONO
from ui.widgets import StatusPill


class ControlPage(QWidget):
    write_requested = pyqtSignal(int)

    PRESETS = [0, 200, 400, 600, 800, 950]

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(12)

        root.addWidget(self._build_setpoint(), stretch=3)
        root.addWidget(self._build_status(), stretch=2)

        self.spin.valueChanged.connect(self._sync_from_spin)
        self.slider.valueChanged.connect(self._sync_from_slider)
        self.btn_write.clicked.connect(
            lambda: self.write_requested.emit(self.spin.value()))
        self.btn_stop.clicked.connect(lambda: self.write_requested.emit(0))
        self._sync_from_spin(0)

    # ------------------------------------------------------------------
    def _build_setpoint(self):
        card = QFrame(); card.setObjectName("Card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 13, 16, 13)
        lay.setSpacing(10)

        t = QLabel("ĐẶT TỐC ĐỘ THỦ CÔNG"); t.setObjectName("CardTitle")
        lay.addWidget(t)

        row = QHBoxLayout(); row.setSpacing(14)
        self.spin = QSpinBox()
        self.spin.setRange(0, SPEED_MAX)
        self.spin.setSingleStep(10)
        self.spin.setFixedWidth(160)
        self.spin.setAlignment(Qt.AlignRight)
        unit = QLabel("rpm")
        unit.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {C['muted']};")
        self.lbl_raw = QLabel()
        self.lbl_raw.setObjectName("Mono")
        row.addWidget(self.spin)
        row.addWidget(unit, alignment=Qt.AlignBottom)
        row.addSpacing(16)
        row.addWidget(self.lbl_raw, alignment=Qt.AlignBottom)
        row.addStretch()
        lay.addLayout(row)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, SPEED_MAX)
        lay.addWidget(self.slider)

        prow = QHBoxLayout(); prow.setSpacing(8)
        for v in self.PRESETS:
            b = QPushButton(str(v)); b.setObjectName("Chip")
            b.setMinimumHeight(34)
            b.clicked.connect(lambda _, val=v: self.spin.setValue(val))
            prow.addWidget(b)
        prow.addStretch()
        lay.addLayout(prow)

        arow = QHBoxLayout(); arow.setSpacing(10)
        self.btn_write = QPushButton("GHI XUỐNG PLC")
        self.btn_write.setObjectName("Primary")
        self.btn_stop = QPushButton("DỪNG BĂNG TẢI")
        self.btn_stop.setObjectName("Danger")
        arow.addWidget(self.btn_write, stretch=2)
        arow.addWidget(self.btn_stop, stretch=1)
        lay.addLayout(arow)
        return card

    def _build_status(self):
        card = QFrame(); card.setObjectName("Card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 13, 16, 13)
        lay.setSpacing(8)

        head = QHBoxLayout()
        t = QLabel("TRẠNG THÁI LỆNH"); t.setObjectName("CardTitle")
        self.pill = StatusPill("CHƯA GHI")
        head.addWidget(t); head.addStretch(); head.addWidget(self.pill)
        lay.addLayout(head)

        grid = QHBoxLayout(); grid.setSpacing(26)
        self.val_actual = self._readout(grid, "Tốc độ thực tế", "rpm", C["speed"])
        self.val_cmd = self._readout(grid, "Lệnh đang giữ", "rpm", C["volt"])
        self.val_reg = self._readout(grid, "Thanh ghi D8116", "", C["muted"])
        grid.addStretch()
        lay.addLayout(grid)
        lay.addStretch()
        return card

    @staticmethod
    def _readout(parent_layout, title, unit, color):
        box = QVBoxLayout(); box.setSpacing(2)
        lbl = QLabel(title.upper()); lbl.setObjectName("CardTitle")
        val = QLabel("--")
        val.setStyleSheet(
            f"font-family: {MONO}; font-size: 26px; font-weight: 800; color: {color};")
        sub = QLabel(unit); sub.setObjectName("CardSub")
        box.addWidget(lbl); box.addWidget(val); box.addWidget(sub)
        parent_layout.addLayout(box)
        return val

    # ------------------------------------------------------------------
    def _raw_text(self, speed):
        raw = speed_to_raw(speed)
        return f"D8116 = {raw}   (~{raw_to_speed(raw):.0f} rpm thực tế)"

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

    # ------------------------------------------------------------------
    def update_telemetry(self, d):
        self.val_actual.setText(f"{d['speed']:.0f}")

    def show_written(self, speed, raw, by_ai=False):
        self.val_cmd.setText(f"{speed:.0f}")
        self.val_reg.setText(str(raw))
        self.pill.set_state("ok", "ĐÃ GHI (AI)" if by_ai else "ĐÃ GHI")

    def show_command(self, raw):
        """Lệnh đọc được từ PLC (có thể do người khác đặt ngoài HMI này)."""
        if raw is None:
            return
        self.val_cmd.setText(f"{raw_to_speed(raw):.0f}")
        self.val_reg.setText(str(raw))
