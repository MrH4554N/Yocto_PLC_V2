#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trang 4 — Trợ lý AI: đề xuất setpoint và luồng phê duyệt của người vận hành.

Chế độ advisory-only: nút ÁP DỤNG chỉ bật khi AI thực sự có đề xuất hợp lệ.
Khi AI chặn (bất thường, hoặc không giải được MPC) thì không có gì để phê
duyệt — nút tắt hẳn, không cho người vận hành áp một giá trị cũ.
"""

from PyQt5.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout, QWidget)
from PyQt5.QtCore import Qt, pyqtSignal

from core.plc_driver import speed_to_raw
from ui.theme import C


class AIPage(QWidget):
    apply_requested = pyqtSignal()

    BANNERS = {
        "collect": (C["muted"],  C["panel"], "ĐANG THU THẬP DỮ LIỆU…"),
        "normal":  (C["green"],  "#0d2818",  "HỆ THỐNG VẬN HÀNH BÌNH THƯỜNG"),
        "suggest": (C["yellow"], "#2b2111",  "AI CÓ ĐỀ XUẤT MỚI — CHỜ PHÊ DUYỆT"),
        "applied": (C["blue"],   "#0d1f33",  "ĐÃ ÁP DỤNG — CHỜ CHU KỲ TIẾP THEO"),
        "blocked": (C["red"],    "#2d1214",  "AI ĐÃ CHẶN ĐỀ XUẤT — CẦN KIỂM TRA"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)

        # --- banner trạng thái ---
        self.banner = QLabel("ĐANG THU THẬP DỮ LIỆU…")
        self.banner.setAlignment(Qt.AlignCenter)
        self.banner.setMinimumHeight(64)
        self._set_banner("collect")
        lay.addWidget(self.banner)

        # --- thẻ đề xuất ---
        card = QFrame(); card.setObjectName("Card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(20, 18, 20, 18)
        cl.setSpacing(14)

        t = QLabel("ĐỀ XUẤT TỐI ƯU HÓA"); t.setObjectName("CardTitle")
        self.lbl_suggestion = QLabel(
            "Hệ thống đang thu thập dữ liệu vận hành.\n"
            "Đề xuất sẽ xuất hiện sau vài chu kỳ AI (~5 giây/chu kỳ).")
        self.lbl_suggestion.setWordWrap(True)
        self.lbl_suggestion.setStyleSheet("font-size: 16px;")

        self.lbl_detail = QLabel(" ")
        self.lbl_detail.setObjectName("CardSub")
        self.lbl_detail.setWordWrap(True)

        arow = QHBoxLayout(); arow.setSpacing(12)
        self.btn_apply = QPushButton("✔ ÁP DỤNG ĐỀ XUẤT (PHÊ DUYỆT)")
        self.btn_apply.setObjectName("Success")
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self.apply_requested.emit)
        self.btn_dismiss = QPushButton("BỎ QUA")
        self.btn_dismiss.setObjectName("Ghost")
        self.btn_dismiss.setEnabled(False)
        self.btn_dismiss.clicked.connect(self.dismiss)
        arow.addWidget(self.btn_apply, stretch=2)
        arow.addWidget(self.btn_dismiss, stretch=1)

        cl.addWidget(t)
        cl.addWidget(self.lbl_suggestion)
        cl.addWidget(self.lbl_detail)
        cl.addLayout(arow)
        lay.addWidget(card)

        note = QLabel(
            "Chế độ advisory-only: AI chỉ đề xuất — mọi thay đổi setpoint đều cần "
            "người vận hành phê duyệt trước khi ghi xuống PLC.")
        note.setObjectName("CardSub")
        note.setWordWrap(True)
        lay.addWidget(note)
        lay.addStretch()

        self.current_speed = 0

    # ------------------------------------------------------------------
    def _set_banner(self, state):
        fg, bg, text = self.BANNERS[state]
        self.banner.setText(text)
        self.banner.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border: 1px solid {C['border']};"
            f"border-radius: 12px; font-size: 17px; font-weight: 800;")

    def _set_buttons(self, enabled):
        self.btn_apply.setEnabled(enabled)
        self.btn_dismiss.setEnabled(enabled)

    # ------------------------------------------------------------------
    def show_suggestion(self, text, speed, detail=None):
        self.current_speed = speed
        self.lbl_suggestion.setText(text)
        raw = speed_to_raw(speed)
        self.lbl_detail.setText(
            f"Tốc độ đề xuất: {speed}   •   Raw D8116: {raw}"
            + (f"\n{detail}" if detail else ""))
        self._set_buttons(True)
        self._set_banner("suggest")

    def show_normal(self, text, detail=None):
        """AI thấy vận hành đã tối ưu — không cần đổi setpoint."""
        self.lbl_suggestion.setText(text)
        self.lbl_detail.setText(detail or " ")
        self._set_buttons(False)
        self._set_banner("normal")

    def show_blocked(self, text, detail=None):
        """AI chặn đề xuất: bất thường vượt ngưỡng hoặc MPC không giải được."""
        self.current_speed = 0
        self.lbl_suggestion.setText(text)
        self.lbl_detail.setText(detail or " ")
        self._set_buttons(False)
        self._set_banner("blocked")

    def show_applied(self):
        self._set_banner("applied")
        self.lbl_suggestion.setText("Đang chờ chu kỳ AI tiếp theo…")
        self.lbl_detail.setText(" ")
        self._set_buttons(False)

    def dismiss(self):
        self._set_banner("normal")
        self.lbl_suggestion.setText("Đề xuất đã được bỏ qua. Chờ chu kỳ AI tiếp theo…")
        self.lbl_detail.setText(" ")
        self._set_buttons(False)
