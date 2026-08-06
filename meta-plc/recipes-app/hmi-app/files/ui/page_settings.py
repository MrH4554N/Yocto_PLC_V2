#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trang CÀI ĐẶT — thông tin hệ thống, tham số mô hình, thoát ứng dụng.

Chỉ đọc: mọi thứ ở đây đến từ config.py và từ artifact đã ký checksum. Sửa
ngưỡng bất thường ngay trên máy sẽ làm ngưỡng lệch khỏi bộ dữ liệu đã học ra
nó, nên chỗ sửa đúng là train lại rồi đóng gói artifact mới.
"""

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QPushButton, QVBoxLayout, QWidget)

from config import (AI_EVERY_N, APP_TITLE, APP_VERSION, ARTIFACT_DIR,
                    POLL_INTERVAL, SPEED_MAX)
from ui.theme import C, MONO


class SettingsPage(QWidget):
    exit_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(12)

        root.addWidget(self._info_card("HỆ THỐNG", [
            ("Ứng dụng", f"{APP_TITLE}  v{APP_VERSION}"),
            ("Nền tảng", "Raspberry Pi 4 · Yocto/Poky · Weston kiosk"),
            ("Cập nhật OTA", "RAUC A/B (u-boot)"),
            ("Chu kỳ đọc cảm biến", f"{POLL_INTERVAL:g} s"),
            ("Chu kỳ chạy AI", f"~{POLL_INTERVAL * AI_EVERY_N:g} s"),
            ("Giới hạn tốc độ", f"{SPEED_MAX} rpm"),
        ]))

        self.model_card = self._info_card("MÔ HÌNH AI", [
            ("Artifact", ARTIFACT_DIR),
            ("Phiên bản", "—"),
            ("Đặc trưng đầu vào", "—"),
            ("Ngưỡng cảnh báo", "—"),
            ("Ngưỡng nguy hiểm", "—"),
        ])
        root.addWidget(self.model_card)
        root.addStretch()

        btn = QPushButton("✖  THOÁT ỨNG DỤNG")
        btn.setObjectName("Ghost")
        btn.setStyleSheet(f"color: {C['err']};")
        btn.setMinimumHeight(44)
        btn.clicked.connect(self.exit_requested.emit)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(btn, stretch=1)
        row.addStretch()
        root.addLayout(row)

    # ------------------------------------------------------------------
    def _info_card(self, title, rows):
        card = QFrame(); card.setObjectName("Card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 13, 16, 13)
        lay.setSpacing(8)
        t = QLabel(title); t.setObjectName("CardTitle")
        lay.addWidget(t)

        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)
        card._values = []
        for r, (name, value) in enumerate(rows):
            lbl = QLabel(name)
            lbl.setStyleSheet(f"font-size: 13px; color: {C['muted']};")
            val = QLabel(str(value))
            val.setStyleSheet(f"font-family: {MONO}; font-size: 13px;")
            val.setWordWrap(True)
            grid.addWidget(lbl, r, 0)
            grid.addWidget(val, r, 1)
            card._values.append(val)
        lay.addLayout(grid)
        return card

    def update_model_info(self, version, n_features, warning, critical):
        vals = self.model_card._values
        vals[1].setText(str(version or "—"))
        vals[2].setText(f"{n_features} đặc trưng" if n_features else "—")
        vals[3].setText(f"{warning:.4f}" if warning is not None else "—")
        vals[4].setText(f"{critical:.4f}" if critical is not None else "—")
